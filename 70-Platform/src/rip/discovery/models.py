"""Immutable, metadata-only contracts for governed artifact discovery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum


class CompatibilityStatus(str, Enum):
    PRIMARY_LOAD_COMPATIBLE = "primary-load-compatible"
    CHUNK_RETRIEVAL_COMPATIBLE = "chunk-retrieval-compatible"
    INELIGIBLE = "ineligible"


@dataclass(frozen=True, slots=True)
class ArtifactCandidate:
    repository_relative_path: str
    observation_id: str
    observed_kind: str
    extension: str
    byte_size: int
    compatibility: CompatibilityStatus
    eligibility_reason: str
    governed_document_id: str | None = None
    governed_title: str | None = None
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.repository_relative_path or self.repository_relative_path.startswith(("/", "\\")) or ".." in self.repository_relative_path.replace("\\", "/").split("/"):
            raise ValueError("candidate path must be a nonempty repository-relative path")
        if not self.observation_id or not self.observed_kind or self.byte_size < 0 or not self.eligibility_reason:
            raise ValueError("candidate provenance and eligibility must be valid")


@dataclass(frozen=True, slots=True)
class ArtifactDiscoveryExclusion:
    candidate: ArtifactCandidate
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("exclusion reason is required")


@dataclass(frozen=True, slots=True)
class DiscoveryReason:
    signal: str
    matched_values: tuple[str, ...]
    weight: int
    contribution: int

    def __post_init__(self) -> None:
        if not self.signal or self.weight < 0 or self.contribution < 0:
            raise ValueError("discovery reason is invalid")
        if self.contribution != self.weight * len(self.matched_values):
            raise ValueError("reason contribution must equal weight times matches")


@dataclass(frozen=True, slots=True)
class ArtifactDiscoveryRanking:
    candidate: ArtifactCandidate
    rank: int
    score: int
    reason_vector: tuple[DiscoveryReason, ...]

    def __post_init__(self) -> None:
        if self.rank < 0 or self.score < 0:
            raise ValueError("ranking values must be nonnegative")
        if self.score != sum(reason.contribution for reason in self.reason_vector):
            raise ValueError("ranking score must equal its reason vector")


@dataclass(frozen=True, slots=True)
class ArtifactDiscoveryDiagnostics:
    artifacts_observed: int
    artifacts_eligible: int
    artifacts_excluded: int
    artifacts_ranked: int
    artifacts_selected: int
    searchable_terms_present: bool

    def __post_init__(self) -> None:
        if min(self.artifacts_observed, self.artifacts_eligible, self.artifacts_excluded, self.artifacts_ranked, self.artifacts_selected) < 0:
            raise ValueError("discovery diagnostics must be nonnegative")
        if self.artifacts_eligible + self.artifacts_excluded != self.artifacts_observed or self.artifacts_ranked != self.artifacts_eligible:
            raise ValueError("discovery diagnostics are inconsistent")


@dataclass(frozen=True, slots=True)
class ArtifactDiscoveryReport:
    discovery_version: str
    strategy: str
    question: str
    candidate_limit: int
    manual_inclusions: tuple[str, ...]
    manual_exclusions: tuple[str, ...]
    considered_artifacts: tuple[ArtifactCandidate, ...]
    excluded_artifacts: tuple[ArtifactDiscoveryExclusion, ...]
    rankings: tuple[ArtifactDiscoveryRanking, ...]
    selected_candidates: tuple[ArtifactCandidate, ...]
    discovery_fingerprint: str
    diagnostics: ArtifactDiscoveryDiagnostics

    def __post_init__(self) -> None:
        if not self.discovery_version or not self.strategy or self.candidate_limit <= 0:
            raise ValueError("discovery report identity and candidate limit are required")
        if len(self.discovery_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in self.discovery_fingerprint):
            raise ValueError("discovery fingerprint must be SHA-256")
        if [item.rank for item in self.rankings] != list(range(len(self.rankings))):
            raise ValueError("ranking positions must be contiguous")
        if self.diagnostics.artifacts_selected != len(self.selected_candidates):
            raise ValueError("diagnostics must match selected candidates")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ArtifactDiscoveryResult:
    selected_candidates: tuple[ArtifactCandidate, ...]
    report: ArtifactDiscoveryReport

    def __post_init__(self) -> None:
        if self.selected_candidates != self.report.selected_candidates:
            raise ValueError("result selection must match discovery report")


def fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
