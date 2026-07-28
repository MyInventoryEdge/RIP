from __future__ import annotations

import re
from pathlib import Path

from .models import Foundation, FoundationArtifact, freeze_mapping
from .parser import parse_artifact

REQUIRED_FILES = {
    "constitution": "RIP-000-Constitution.md",
    "lexicon": "RIP-001-Lexicon.md",
    "conceptual_model": "RIP-002-Conceptual-Model.md",
    "governance": "RIP-003-Governance.md",
    "learning": "RIP-004-Organizational-Learning.md",
}

PRIMARY_OBJECT_RE = re.compile(
    r"The\s+(?P<object>[A-Z][A-Za-z0-9 _-]+?)\s+SHALL\s+be\s+RIP['’]s\s+primary\s+object",
    re.IGNORECASE,
)


def find_foundation_root(start: str | Path | None = None) -> Path:
    """Find 00-Constitution from the current directory or one of its parents."""
    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent

    candidates = [current, *current.parents]
    for base in candidates:
        direct = base / "00-Constitution"
        if direct.is_dir():
            return direct

    raise FileNotFoundError(
        "Could not locate 00-Constitution from the current directory or its parents. "
        "Run from C:\\RIP or C:\\RIP\\70-Platform, or pass --root explicitly."
    )


def load_foundation(root: str | Path | None = None) -> Foundation:
    root_path = find_foundation_root() if root is None else Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(f"Foundation directory not found: {root_path}")

    artifacts: dict[str, FoundationArtifact] = {}
    missing: list[str] = []

    for key, filename in REQUIRED_FILES.items():
        path = root_path / filename
        if not path.is_file():
            missing.append(filename)
        else:
            artifacts[key] = parse_artifact(path)

    if missing:
        joined = "\n  - ".join(missing)
        raise FileNotFoundError(
            f"Foundation is incomplete. Missing files in {root_path}:\n  - {joined}"
        )

    lexicon = {
        section.heading.strip(): section.body.strip()
        for section in artifacts["lexicon"].sections
        if section.body.strip()
    }

    return Foundation(
        root=root_path,
        constitution=artifacts["constitution"],
        lexicon_artifact=artifacts["lexicon"],
        conceptual_model=artifacts["conceptual_model"],
        governance=artifacts["governance"],
        learning=artifacts["learning"],
        lexicon=freeze_mapping(lexicon),
        primary_object=_extract_primary_object(artifacts["constitution"]),
    )


def _extract_primary_object(constitution: FoundationArtifact) -> str:
    try:
        body = constitution.section("Primary Object").body
    except KeyError as exc:
        raise ValueError("Constitution does not contain a Primary Object section") from exc

    match = PRIMARY_OBJECT_RE.search(body)
    if not match:
        raise ValueError("Could not determine RIP's primary object from the Constitution")
    return match.group("object").strip().title()
