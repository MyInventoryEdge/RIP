from __future__ import annotations

import unittest

from rip.retrieval.models import (
    ArtifactDescriptor,
    ChunkCatalog,
    ChunkReference,
    CoverageStatus,
    CoverageSummary,
    EvidenceChunk,
    MessageRange,
    RankingEntry,
    RetrievalReport,
    RetrievalResult,
    SourceRange,
    VersionMetadata,
)

ARTIFACT_HASH = "a" * 64
CHUNK_HASH = "b" * 64


def descriptor(**changes: object) -> ArtifactDescriptor:
    values = dict(repository_relative_path="evidence/artifact.json", source_observation_id="obs-0001", artifact_type="canonical-session", media_type="application/json", encoding="utf-8", byte_size=1, sha256=ARTIFACT_HASH, estimated_token_count=1, preferred_chunker="canonical-session", chunkable=True)
    values.update(changes)
    return ArtifactDescriptor(**values)  # type: ignore[arg-type]


def versions(**changes: object) -> VersionMetadata:
    values = dict(chunk_contract_version="1.0", chunker_name="canonical-session", chunker_version="1.0", serialization_version="1.0", size_policy_version="1.0")
    values.update(changes)
    return VersionMetadata(**values)  # type: ignore[arg-type]


def source_range(start: int = 0, end: int = 0) -> MessageRange:
    return MessageRange("message", start, end, f"message-{start}", f"message-{end}")


def chunk(index: int = 0, chunk_id: str = "chunk-0", **changes: object) -> EvidenceChunk:
    values = dict(repository_relative_path="evidence/artifact.json", source_observation_id="obs-0001", artifact_type="canonical-session", media_type="application/json", encoding="utf-8", artifact_sha256=ARTIFACT_HASH, chunk_sha256=CHUNK_HASH, chunk_id=chunk_id, chunk_index=index, content="original content", source_range=source_range(index, index), versions=versions())
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def coverage(**changes: object) -> CoverageSummary:
    values = dict(repository_relative_path="evidence/artifact.json", artifact_sha256=ARTIFACT_HASH, total_logical_units=4, retrieved_logical_units=1, omitted_logical_units=3, overlap_logical_units=0, status=CoverageStatus.PARTIAL)
    values.update(changes)
    return CoverageSummary(**values)  # type: ignore[arg-type]


def report(selected_chunks=(), excluded_chunks=(), rankings=()) -> RetrievalReport:
    return RetrievalReport("1.0", "lexical", "question", (coverage(),), selected_chunks, excluded_chunks, rankings, 100, 25)


class RetrievalModelTests(unittest.TestCase):
    def test_descriptor_validation_and_immutability(self) -> None:
        artifact = descriptor()
        with self.assertRaises(AttributeError): artifact.byte_size = 2  # type: ignore[misc]
        for changes in ({"repository_relative_path": "../outside.json"}, {"repository_relative_path": "C:/outside.json"}, {"byte_size": -1}, {"estimated_token_count": -1}, {"sha256": "bad"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): descriptor(**changes)

    def test_source_ranges_and_versions_are_typed_and_validated(self) -> None:
        self.assertEqual(source_range(2, 4).unit_count, 3)
        with self.assertRaises(ValueError): SourceRange("", 0, 0)
        with self.assertRaises(ValueError): SourceRange("row", 3, 2)
        with self.assertRaises(ValueError): MessageRange("row", 0, 0, "a", "b")
        with self.assertRaises(ValueError): versions(chunker_version="")

    def test_chunk_is_self_describing_and_serializes_deterministically(self) -> None:
        evidence_chunk = chunk()
        encoded = evidence_chunk.to_json()
        self.assertEqual(encoded, evidence_chunk.to_json())
        for text in ("repository_relative_path", "source_observation_id", "artifact_sha256", "chunk_sha256", "chunk_contract_version", "start_message_id"):
            self.assertIn(text, encoded)

    def test_catalog_validates_provenance_versions_indexes_and_overlap(self) -> None:
        first, second = chunk(), chunk(1, "chunk-1", chunk_sha256="c" * 64)
        catalog = ChunkCatalog(descriptor(), (first, second), 2)
        self.assertEqual(catalog.chunked_logical_units, 2)
        self.assertEqual(catalog.omitted_logical_units, 0)
        with self.assertRaises(ValueError): ChunkCatalog(descriptor(), (chunk(1),), 2)
        with self.assertRaises(ValueError): ChunkCatalog(descriptor(), (chunk(), chunk(1, "chunk-0")), 2)
        with self.assertRaises(ValueError): ChunkCatalog(descriptor(), (chunk(artifact_sha256="c" * 64),), 1)
        with self.assertRaises(ValueError): ChunkCatalog(descriptor(), (chunk(), chunk(1, "chunk-1", versions=versions(chunker_version="2.0"))), 2)
        with self.assertRaises(ValueError): ChunkCatalog(descriptor(), (chunk(source_range=source_range(0, 1)),), 2, 1)
        overlapping = ChunkCatalog(descriptor(), (chunk(source_range=source_range(0, 1)), chunk(1, "chunk-1", chunk_sha256="c" * 64, source_range=source_range(1, 1))), 2, 1)
        self.assertEqual(overlapping.overlap_logical_units, 1)

    def test_coverage_status_and_percentages_are_derived_from_totals(self) -> None:
        self.assertEqual(coverage().retrieved_percentage, 25.0)
        self.assertEqual(coverage(total_logical_units=0, retrieved_logical_units=0, omitted_logical_units=0, status=CoverageStatus.EMPTY).retrieved_percentage, 0.0)
        complete = coverage(retrieved_logical_units=4, omitted_logical_units=0, status=CoverageStatus.COMPLETE)
        self.assertEqual(complete.retrieved_percentage, 100.0)
        with self.assertRaises(ValueError): coverage(status=CoverageStatus.COMPLETE)
        with self.assertRaises(ValueError): coverage(overlap_logical_units=-1)

    def test_report_and_result_validate_structured_references_deterministically(self) -> None:
        evidence_chunk = chunk()
        reference = ChunkReference.from_chunk(evidence_chunk)
        entry = RankingEntry(reference, 0, 10, "term match")
        validated = report((reference,), (), (entry,))
        self.assertEqual(validated.to_json(), validated.to_json())
        self.assertEqual(RetrievalResult((evidence_chunk,), validated).report, validated)
        with self.assertRaises(ValueError): report((reference,), (reference,), (entry,))
        with self.assertRaises(ValueError): report((), (), (RankingEntry(reference, 1, 1, "x"),))
        foreign = ChunkReference("other.json", ARTIFACT_HASH, CHUNK_HASH, "foreign", 0)
        with self.assertRaises(ValueError): report((foreign,), (), (RankingEntry(foreign, 0, 1, "x"),))
