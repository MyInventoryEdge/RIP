from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

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

CONSTITUTIONAL_NAMES = frozenset({
    "RIP-000-Constitution.md",
    "RIP-001-Lexicon.md",
    "RIP-002-Conceptual-Model.md",
    "RIP-003-Governance.md",
    "RIP-004-Organizational-Learning.md",
})


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


def _is_test_fixture(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    return any(
        parts[index] == "tests" and parts[index + 1] == "fixtures"
        for index in range(len(parts) - 1)
    )


def _file_kind(path: Path) -> str:
    if path.name in CONSTITUTIONAL_NAMES and _is_test_fixture(path):
        return "test_fixture_artifact"
    if path.name in CONSTITUTIONAL_NAMES:
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
    if path.name in CONSTITUTIONAL_NAMES and _is_test_fixture(path):
        evidence.append("filename matches an approved RIP foundation artifact")
        evidence.append("path is beneath a tests/fixtures boundary")
    elif path.name in CONSTITUTIONAL_NAMES:
        evidence.append("filename matches an approved RIP foundation artifact")
    elif path.name == "pyproject.toml":
        evidence.append("filename is pyproject.toml")
    elif path.suffix:
        evidence.append(f"file extension is {path.suffix.lower()}")
    return tuple(evidence)
