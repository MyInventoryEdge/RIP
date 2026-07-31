"""Immutable, deterministic contracts for future evidence chunking and retrieval."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import Enum

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _validate_repository_relative_path(value: str) -> None:
    normalized = value.replace("\\", "/")
    if not value or value.startswith(("/", "\\")) or ":" in value or ".." in normalized.split("/"):
        raise ValueError("repository_relative_path must be a nonempty repository-relative path")


def _validate_sha256(value: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError("SHA-256 values must be 64 lowercase hexadecimal characters")


def _canonical_json(value: object) -> str:
    return json.dumps(asdict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """Canonical, already-discovered artifact provenance supplied to a chunker."""

    repository_relative_path: str
    source_observation_id: str | None
    artifact_type: str
    media_type: str
    encoding: str
    byte_size: int
    sha256: str
    estimated_token_count: int
    preferred_chunker: str | None
    chunkable: bool

    def __post_init__(self) -> None:
        _validate_repository_relative_path(self.repository_relative_path)
        _validate_sha256(self.sha256)
        if self.source_observation_id == "" or not all((self.artifact_type, self.media_type, self.encoding)):
            raise ValueError("artifact provenance fields must be nonempty when provided")
        if self.byte_size < 0 or self.estimated_token_count < 0:
            raise ValueError("byte and token counts must be nonnegative")


@dataclass(frozen=True, slots=True)
class VersionMetadata:
    """Governed version inputs that determine chunk identity and interpretation."""

    chunk_contract_version: str
    chunker_name: str
    chunker_version: str
    serialization_version: str
    size_policy_version: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.chunk_contract_version,
                self.chunker_name,
                self.chunker_version,
                self.serialization_version,
                self.size_policy_version,
            )
        ):
            raise ValueError("all chunk version metadata fields are required")


@dataclass(frozen=True, slots=True)
class SourceRange:
    """Inclusive range of complete logical source units in source order."""

    logical_unit_type: str
    start_index: int
    end_index: int

    def __post_init__(self) -> None:
        if not self.logical_unit_type or self.start_index < 0 or self.end_index < self.start_index:
            raise ValueError("source range must have a type and valid inclusive indexes")

    @property
    def unit_count(self) -> int:
        return self.end_index - self.start_index + 1


@dataclass(frozen=True, slots=True)
class MessageRange(SourceRange):
    """Source range for complete canonical-session message objects."""

    start_message_id: str
    end_message_id: str

    def __post_init__(self) -> None:
        SourceRange.__post_init__(self)
        if self.logical_unit_type != "message" or not self.start_message_id or not self.end_message_id:
            raise ValueError("message ranges require message type and nonempty boundary message IDs")


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    """Self-describing, lossless evidence unit traceable without its catalog."""

    repository_relative_path: str
    source_observation_id: str | None
    artifact_type: str
    media_type: str
    encoding: str
    artifact_sha256: str
    chunk_sha256: str
    chunk_id: str
    chunk_index: int
    content: str
    source_range: SourceRange
    versions: VersionMetadata

    def __post_init__(self) -> None:
        _validate_repository_relative_path(self.repository_relative_path)
        _validate_sha256(self.artifact_sha256)
        _validate_sha256(self.chunk_sha256)
        if self.source_observation_id == "" or not all((self.artifact_type, self.media_type, self.encoding)):
            raise ValueError("chunk provenance fields must be nonempty when provided")
        if not self.chunk_id or self.chunk_index < 0:
            raise ValueError("chunk identity and index must be valid")

    def to_json(self) -> str:
        return _canonical_json(self)


@dataclass(frozen=True, slots=True)
class ChunkCatalog:
    """Deterministically ordered chunks and coverage accounting for one artifact."""

    descriptor: ArtifactDescriptor
    chunks: tuple[EvidenceChunk, ...]
    total_logical_units: int
    overlap_logical_units: int = 0

    def __post_init__(self) -> None:
        if self.total_logical_units < 0 or self.overlap_logical_units < 0:
            raise ValueError("catalog logical-unit totals must be nonnegative")
        if not self.descriptor.chunkable and self.chunks:
            raise ValueError("an unchunkable artifact cannot have catalog chunks")
        indexes = [chunk.chunk_index for chunk in self.chunks]
        if indexes != list(range(len(self.chunks))):
            raise ValueError("chunk indexes must be stable, contiguous, and zero-based")
        if len({chunk.chunk_id for chunk in self.chunks}) != len(self.chunks):
            raise ValueError("chunk IDs must be unique")
        if any(not self._matches_descriptor(chunk) for chunk in self.chunks):
            raise ValueError("chunk provenance does not match catalog descriptor")
        if self.chunks and len({chunk.versions for chunk in self.chunks}) != 1:
            raise ValueError("catalog chunks must have consistent version metadata")
        if self.chunks and len({chunk.source_range.logical_unit_type for chunk in self.chunks}) != 1:
            raise ValueError("catalog chunks must have one logical-unit type")
        if self.chunks and any(
            later.source_range.start_index < earlier.source_range.start_index
            for earlier, later in zip(self.chunks, self.chunks[1:])
        ):
            raise ValueError("catalog chunks must preserve source-range order")
        represented = {
            index
            for chunk in self.chunks
            for index in range(chunk.source_range.start_index, chunk.source_range.end_index + 1)
        }
        raw_units = sum(chunk.source_range.unit_count for chunk in self.chunks)
        if any(index >= self.total_logical_units for index in represented):
            raise ValueError("chunk source range exceeds catalog logical-unit total")
        if raw_units - len(represented) != self.overlap_logical_units:
            raise ValueError("catalog overlap accounting does not match source ranges")

    def _matches_descriptor(self, chunk: EvidenceChunk) -> bool:
        return (
            chunk.repository_relative_path == self.descriptor.repository_relative_path
            and chunk.source_observation_id == self.descriptor.source_observation_id
            and chunk.artifact_type == self.descriptor.artifact_type
            and chunk.media_type == self.descriptor.media_type
            and chunk.encoding == self.descriptor.encoding
            and chunk.artifact_sha256 == self.descriptor.sha256
        )

    @property
    def chunked_logical_units(self) -> int:
        return len(
            {
                index
                for chunk in self.chunks
                for index in range(chunk.source_range.start_index, chunk.source_range.end_index + 1)
            }
        )

    @property
    def omitted_logical_units(self) -> int:
        return self.total_logical_units - self.chunked_logical_units


class CoverageStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """Deterministic retrieval coverage for one governed artifact."""

    repository_relative_path: str
    artifact_sha256: str
    total_logical_units: int
    retrieved_logical_units: int
    omitted_logical_units: int
    overlap_logical_units: int
    status: CoverageStatus

    def __post_init__(self) -> None:
        _validate_repository_relative_path(self.repository_relative_path)
        _validate_sha256(self.artifact_sha256)
        if min(
            self.total_logical_units,
            self.retrieved_logical_units,
            self.omitted_logical_units,
            self.overlap_logical_units,
        ) < 0:
            raise ValueError("coverage totals must be nonnegative")
        if self.retrieved_logical_units + self.omitted_logical_units != self.total_logical_units:
            raise ValueError("retrieved and omitted units must account for the total")
        expected = (
            CoverageStatus.COMPLETE
            if self.total_logical_units > 0 and self.retrieved_logical_units == self.total_logical_units
            else CoverageStatus.PARTIAL
            if self.retrieved_logical_units > 0
            else CoverageStatus.EMPTY
        )
        if self.status is not expected:
            raise ValueError("coverage status does not match coverage totals")

    @property
    def retrieved_percentage(self) -> float:
        return 0.0 if self.total_logical_units == 0 else self.retrieved_logical_units * 100 / self.total_logical_units


@dataclass(frozen=True, slots=True)
class ChunkReference:
    """Serializable reference to a self-describing chunk without duplicating content."""

    repository_relative_path: str
    artifact_sha256: str
    chunk_sha256: str
    chunk_id: str
    chunk_index: int

    def __post_init__(self) -> None:
        _validate_repository_relative_path(self.repository_relative_path)
        _validate_sha256(self.artifact_sha256)
        _validate_sha256(self.chunk_sha256)
        if not self.chunk_id or self.chunk_index < 0:
            raise ValueError("chunk reference identity and index must be valid")

    @classmethod
    def from_chunk(cls, chunk: EvidenceChunk) -> "ChunkReference":
        return cls(chunk.repository_relative_path, chunk.artifact_sha256, chunk.chunk_sha256, chunk.chunk_id, chunk.chunk_index)


@dataclass(frozen=True, slots=True)
class RankingEntry:
    """Structured, deterministic ranking metadata."""

    chunk: ChunkReference
    rank: int
    score: int
    reason: str

    def __post_init__(self) -> None:
        if self.rank < 0 or not self.reason:
            raise ValueError("ranking metadata is invalid")


@dataclass(frozen=True, slots=True)
class RetrievalDiagnostics:
    """Deterministic engineering counts; these are not confidence measurements."""

    chunks_considered: int
    chunks_ranked: int
    chunks_selected: int
    searchable_terms_present: bool

    def __post_init__(self) -> None:
        if min(self.chunks_considered, self.chunks_ranked, self.chunks_selected) < 0:
            raise ValueError("retrieval diagnostic counts must be nonnegative")
        if self.chunks_ranked > self.chunks_considered or self.chunks_selected > self.chunks_ranked:
            raise ValueError("retrieval diagnostic counts are inconsistent")


@dataclass(frozen=True, slots=True)
class RetrievalReport:
    """Deterministic audit record for a future retrieval operation."""

    retrieval_version: str
    strategy: str
    query: str
    coverage: tuple[CoverageSummary, ...]
    selected_chunks: tuple[ChunkReference, ...]
    excluded_chunks: tuple[ChunkReference, ...]
    rankings: tuple[RankingEntry, ...]
    token_budget: int
    estimated_token_usage: int
    retrieval_fingerprint: str
    diagnostics: RetrievalDiagnostics

    def __post_init__(self) -> None:
        if not self.retrieval_version or not self.strategy:
            raise ValueError("retrieval version and strategy are required")
        if self.token_budget < 0 or self.estimated_token_usage < 0:
            raise ValueError("retrieval token counts must be nonnegative")
        _validate_sha256(self.retrieval_fingerprint)
        selected = {self._reference_identity(reference) for reference in self.selected_chunks}
        excluded = {self._reference_identity(reference) for reference in self.excluded_chunks}
        if selected & excluded:
            raise ValueError("selected and excluded chunks must not overlap")
        if len(selected) != len(self.selected_chunks) or len(excluded) != len(self.excluded_chunks):
            raise ValueError("chunk references must be unique")
        ranking_ids = {self._reference_identity(entry.chunk) for entry in self.rankings}
        ranks = [entry.rank for entry in self.rankings]
        if len(ranking_ids) != len(self.rankings) or ranks != list(range(len(ranks))):
            raise ValueError("ranking entries must have unique, contiguous ranks")
        if not selected.union(excluded).issubset(ranking_ids):
            raise ValueError("selected and excluded chunks must have ranking metadata")
        coverage_ids = {(item.repository_relative_path, item.artifact_sha256) for item in self.coverage}
        if len(coverage_ids) != len(self.coverage):
            raise ValueError("coverage summaries must be unique per artifact")
        if any((ref.repository_relative_path, ref.artifact_sha256) not in coverage_ids for ref in (*self.selected_chunks, *self.excluded_chunks)):
            raise ValueError("chunk references must have matching coverage")
        if self.diagnostics.chunks_considered != len(self.selected_chunks) + len(self.excluded_chunks):
            raise ValueError("retrieval diagnostics must account for every considered chunk")
        if self.diagnostics.chunks_ranked != len(self.rankings) or self.diagnostics.chunks_selected != len(self.selected_chunks):
            raise ValueError("retrieval diagnostics must match report contents")

    @staticmethod
    def _reference_identity(reference: ChunkReference) -> tuple[str, str, str, str, int]:
        return (
            reference.repository_relative_path,
            reference.artifact_sha256,
            reference.chunk_sha256,
            reference.chunk_id,
            reference.chunk_index,
        )

    def to_json(self) -> str:
        return _canonical_json(self)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Future engine result whose chunks and report selection agree exactly."""

    selected_chunks: tuple[EvidenceChunk, ...]
    report: RetrievalReport

    def __post_init__(self) -> None:
        if tuple(ChunkReference.from_chunk(chunk) for chunk in self.selected_chunks) != self.report.selected_chunks:
            raise ValueError("result chunks must match report selection")
