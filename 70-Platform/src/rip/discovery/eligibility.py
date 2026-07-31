"""Deterministic artifact eligibility using observation and Foundation metadata only."""

from __future__ import annotations

from pathlib import PurePosixPath

from ..foundation.models import Foundation
from ..observation.models import Observation
from .models import ArtifactCandidate, CompatibilityStatus

TEXT_EXTENSIONS = frozenset({".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"})
RUNTIME_PARTS = frozenset({".rip-state", ".rip-voice"})
GENERATED_FILENAMES = frozenset({"candidate-review.html", "candidate-review.md", "interpretation-report.md"})
TEMPORARY_SUFFIXES = frozenset({".tmp", ".temp", ".bak", ".swp"})


def candidate_from_observation(observation: Observation, foundation: Foundation) -> ArtifactCandidate:
    path = observation.relative_path.replace("\\", "/")
    parts = tuple(part.casefold() for part in PurePosixPath(path).parts)
    suffix = str(observation.metadata.get("suffix", "")).casefold()
    size = int(observation.metadata.get("size_bytes", 0))
    observation_identity = str(observation.path).replace("\\", "/").casefold()
    governed = next((artifact for artifact in foundation.artifacts if str(artifact.path).replace("\\", "/").casefold() == observation_identity), None)
    aliases = _aliases(path, observation.kind)
    base = dict(
        repository_relative_path=path,
        observation_id=observation.observation_id,
        observed_kind=observation.kind,
        extension=suffix,
        byte_size=size,
        governed_document_id=governed.artifact_id if governed else None,
        governed_title=governed.title if governed else None,
        aliases=aliases,
    )
    if observation.kind == "constitutional_artifact" or governed is not None:
        return ArtifactCandidate(**base, compatibility=CompatibilityStatus.INELIGIBLE, eligibility_reason="already-supplied-by-foundation")
    if "tests" in parts:
        return ArtifactCandidate(**base, compatibility=CompatibilityStatus.INELIGIBLE, eligibility_reason="test-artifact")
    if any(part in RUNTIME_PARTS for part in parts):
        return ArtifactCandidate(**base, compatibility=CompatibilityStatus.INELIGIBLE, eligibility_reason="runtime-state")
    if suffix in TEMPORARY_SUFFIXES or PurePosixPath(path).name.startswith("~$"):
        return ArtifactCandidate(**base, compatibility=CompatibilityStatus.INELIGIBLE, eligibility_reason="temporary-artifact")
    if PurePosixPath(path).name.casefold() in GENERATED_FILENAMES:
        return ArtifactCandidate(**base, compatibility=CompatibilityStatus.INELIGIBLE, eligibility_reason="generated-artifact")
    if observation.kind != "file" and observation.kind not in {"markdown_file", "python_source_file", "python_project_manifest"}:
        return ArtifactCandidate(**base, compatibility=CompatibilityStatus.INELIGIBLE, eligibility_reason="non-discoverable-observation-kind")
    if suffix not in TEXT_EXTENSIONS:
        return ArtifactCandidate(**base, compatibility=CompatibilityStatus.INELIGIBLE, eligibility_reason="binary-or-unsupported-extension")
    compatibility = CompatibilityStatus.CHUNK_RETRIEVAL_COMPATIBLE if PurePosixPath(path).name == "canonical-session.json" else CompatibilityStatus.PRIMARY_LOAD_COMPATIBLE
    return ArtifactCandidate(**base, compatibility=compatibility, eligibility_reason="metadata-eligible")


def _aliases(path: str, observed_kind: str) -> tuple[str, ...]:
    lower = path.casefold()
    values: list[str] = []
    if "canonical-session.json" in lower:
        values.extend(("canonical-session", "session", "conversation"))
    if "parser-manifest.json" in lower:
        values.extend(("parser-manifest", "parser", "manifest"))
    if "primary_evidence" in lower:
        values.extend(("primary-evidence", "evidence"))
    if "/voice/" in f"/{lower}" or "voice" in lower:
        values.append("voice")
    if observed_kind == "python_project_manifest":
        values.extend(("python", "project", "manifest"))
    return tuple(dict.fromkeys(values))
