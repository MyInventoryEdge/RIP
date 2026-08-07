from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from .models import Observation, ObservationSet

DEFAULT_EXCLUSIONS = frozenset({
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vs",
    "__pycache__",
    "bin",
    "node_modules",
    "obj",
})

CONSTITUTIONAL_NAME_RE = re.compile(r"RIP-\d{3}-.+\.md$", re.IGNORECASE)


def find_repository_root(start: str | Path | None = None) -> Path:
    """Find the nearest ancestor that visibly represents a RIP repository."""
    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
        if (candidate / "00-Constitution").is_dir() and (candidate / "70-Platform").is_dir():
            return candidate
    return current


def observe_filesystem(
    root: str | Path | None = None,
    *,
    include_hidden: bool = False,
    exclusions: frozenset[str] = DEFAULT_EXCLUSIONS,
) -> ObservationSet:
    root_path = find_repository_root(root)
    if not root_path.is_dir():
        raise FileNotFoundError(f"Observation root is not a directory: {root_path}")

    observed_at = datetime.now(timezone.utc)
    observations: list[Observation] = []

    # The root itself is evidence and therefore receives an observation.
    observations.append(
        _make_observation(
            root=root_path,
            path=root_path,
            kind="repository_root",
            observed_at=observed_at,
            evidence=_root_evidence(root_path),
            metadata={"name": root_path.name},
        )
    )

    def walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        except PermissionError as exc:
            observations.append(
                _make_observation(
                    root=root_path,
                    path=directory,
                    kind="access_error",
                    observed_at=observed_at,
                    evidence=(str(exc),),
                )
            )
            return

        for path in entries:
            if _is_excluded(path, exclusions):
                continue
            if not include_hidden and path.name.startswith("."):
                continue

            if path.is_symlink():
                observations.append(
                    _make_observation(
                        root=root_path,
                        path=path,
                        kind="symbolic_link",
                        observed_at=observed_at,
                        evidence=("filesystem entry is a symbolic link",),
                        metadata={"target": str(path.resolve(strict=False))},
                    )
                )
                continue

            if path.is_dir():
                observations.append(
                    _make_observation(
                        root=root_path,
                        path=path,
                        kind="directory",
                        observed_at=observed_at,
                        evidence=("filesystem entry is a directory",),
                    )
                )
                walk(path)
                continue

            if path.is_file():
                stat = path.stat()
                observations.append(
                    _make_observation(
                        root=root_path,
                        path=path,
                        kind=_file_kind(path),
                        observed_at=observed_at,
                        evidence=_file_evidence(path),
                        metadata={"size_bytes": stat.st_size, "suffix": path.suffix.lower()},
                    )
                )

    walk(root_path)
    observations.sort(key=lambda item: (item.relative_path.casefold(), item.kind))
    return ObservationSet(
        root=root_path,
        observed_at=observed_at,
        observations=tuple(observations),
        excluded_names=tuple(sorted(exclusions)),
    )


def observe_source_manifest(
    root: str | Path,
    entries: Sequence[Mapping[str, object]],
    *,
    include_hidden: bool = False,
    exclusions: frozenset[str] = DEFAULT_EXCLUSIONS,
) -> ObservationSet:
    """Project filesystem observations from an exact source-manifest pass.

    This avoids a redundant third repository walk. It does not infer content or
    authority; it produces the same path/type evidence as ``observe_filesystem``
    from entries already read during the governed source baseline.
    """
    # A governed manifest is already anchored to the operator-approved root;
    # never rediscover and promote an ancestor repository here.
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(f"Observation root is not a directory: {root_path}")
    observed_at = datetime.now(timezone.utc)
    observations = [
        _make_observation(
            root=root_path,
            path=root_path,
            kind="repository_root",
            observed_at=observed_at,
            evidence=_root_evidence(root_path),
            metadata={"name": root_path.name},
        )
    ]
    for entry in entries:
        relative = entry.get("path")
        source_kind = entry.get("kind")
        if not isinstance(relative, str) or not relative or not isinstance(source_kind, str):
            raise ValueError("source manifest entries require path and kind")
        if _manifest_path_is_excluded(relative, include_hidden=include_hidden, exclusions=exclusions):
            continue
        path = root_path.joinpath(*PurePosixPath(relative).parts)
        if source_kind == "directory":
            observations.append(
                _make_observation(
                    root=root_path,
                    path=path,
                    kind="directory",
                    observed_at=observed_at,
                    evidence=("filesystem entry is a directory",),
                )
            )
        elif source_kind == "symlink":
            observations.append(
                _make_observation(
                    root=root_path,
                    path=path,
                    kind="symbolic_link",
                    observed_at=observed_at,
                    evidence=("filesystem entry is a symbolic link",),
                    metadata={"target": str(path.resolve(strict=False))},
                )
            )
        elif source_kind == "file":
            size = entry.get("size")
            if not isinstance(size, int) or size < 0:
                raise ValueError(f"source manifest file has invalid size: {relative}")
            observations.append(
                _make_observation(
                    root=root_path,
                    path=path,
                    kind=_file_kind(path),
                    observed_at=observed_at,
                    evidence=_file_evidence(path),
                    metadata={"size_bytes": size, "suffix": path.suffix.lower()},
                )
            )
        elif source_kind == "access-error":
            observations.append(
                _make_observation(
                    root=root_path,
                    path=path,
                    kind="access_error",
                    observed_at=observed_at,
                    evidence=(str(entry.get("value") or "filesystem entry could not be read"),),
                )
            )
        else:
            raise ValueError(f"source manifest entry has unsupported kind: {source_kind}")
    observations.sort(key=lambda item: (item.relative_path.casefold(), item.kind))
    return ObservationSet(
        root=root_path,
        observed_at=observed_at,
        observations=tuple(observations),
        excluded_names=tuple(sorted(exclusions)),
    )


def _make_observation(
    *,
    root: Path,
    path: Path,
    kind: str,
    observed_at: datetime,
    evidence: tuple[str, ...],
    metadata: dict | None = None,
) -> Observation:
    relative = "." if path == root else path.relative_to(root).as_posix()
    identity = f"filesystem\0{kind}\0{relative}".encode("utf-8")
    observation_id = "obs-" + hashlib.sha256(identity).hexdigest()[:16]
    return Observation(
        observation_id=observation_id,
        observed_at=observed_at,
        source="filesystem",
        subject=path.name or str(path),
        kind=kind,
        path=path.resolve(),
        relative_path=relative,
        evidence=evidence,
        metadata=metadata or {},
    )


def _root_evidence(root: Path) -> tuple[str, ...]:
    evidence = ["observation target is a directory"]
    if (root / ".git").exists():
        evidence.append(".git exists at observation root")
    if (root / "00-Constitution").is_dir():
        evidence.append("00-Constitution exists at observation root")
    if (root / "70-Platform").is_dir():
        evidence.append("70-Platform exists at observation root")
    return tuple(evidence)


def _is_excluded(path: Path, exclusions: frozenset[str]) -> bool:
    """Return True for generated or explicitly excluded filesystem entries."""
    if path.name in exclusions:
        return True
    if path.is_dir() and path.name.casefold().endswith(".egg-info"):
        return True
    return False


def _manifest_path_is_excluded(
    relative: str,
    *,
    include_hidden: bool,
    exclusions: frozenset[str],
) -> bool:
    parts = PurePosixPath(relative).parts
    for part in parts:
        if part in exclusions or part.casefold().endswith(".egg-info"):
            return True
        if not include_hidden and part.startswith("."):
            return True
    return False


def _is_test_fixture(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    return any(
        parts[index] == "tests" and parts[index + 1] == "fixtures"
        for index in range(len(parts) - 1)
    )


def _file_kind(path: Path) -> str:
    if CONSTITUTIONAL_NAME_RE.fullmatch(path.name) and _is_test_fixture(path):
        return "test_fixture_artifact"
    if CONSTITUTIONAL_NAME_RE.fullmatch(path.name):
        return "constitutional_artifact"
    if path.name == "pyproject.toml":
        return "python_project_manifest"
    if path.name.casefold() in {"dockerfile", "containerfile"}:
        return "container_build_file"
    if path.suffix.lower() == ".md":
        return "markdown_file"
    if path.suffix.lower() == ".py":
        return "python_source_file"
    if path.suffix.lower() in {".sln", ".slnx"}:
        return "solution_manifest"
    if path.suffix.lower() in {".csproj", ".fsproj", ".vbproj"}:
        return "project_manifest"
    return "file"


def _file_evidence(path: Path) -> tuple[str, ...]:
    evidence = ["filesystem entry is a file"]
    if CONSTITUTIONAL_NAME_RE.fullmatch(path.name) and _is_test_fixture(path):
        evidence.append("filename matches an approved RIP foundation artifact")
        evidence.append("path is beneath a tests/fixtures boundary")
    elif CONSTITUTIONAL_NAME_RE.fullmatch(path.name):
        evidence.append("filename matches an approved RIP foundation artifact")
    elif path.name == "pyproject.toml":
        evidence.append("filename is pyproject.toml")
    elif path.suffix:
        evidence.append(f"file extension is {path.suffix.lower()}")
    return tuple(evidence)
