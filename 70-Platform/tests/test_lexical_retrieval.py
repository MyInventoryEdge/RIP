from __future__ import annotations

import hashlib
import json
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

from rip.retrieval.canonical_session import CanonicalSessionChunker
from rip.retrieval.lexical import DeterministicLexicalRetrievalEngine, EXACT_PHRASE_WEIGHT, IDENTIFIER_WEIGHT, TERM_WEIGHT
from rip.retrieval.models import ArtifactDescriptor, ChunkCatalog, CoverageStatus


def message(index: int, markdown: str, *, message_id: str | None = None) -> dict[str, object]:
    return {
        "source_message_id": message_id or f"message-{index}", "source_order": index,
        "participant_id": "role:user", "role": "user", "markdown": markdown,
        "searchable_text": markdown, "code_blocks": [], "links": [], "images": [], "attachments": [], "source_metadata": {"ignored": "metadata-only-term"},
    }


def catalog(messages: list[dict[str, object]], *, soft_target_tokens: int = 90):
    document = {"session_id": "session", "source_format": "test", "messages": messages, "validation": {"passed": True}}
    content = json.dumps(document, ensure_ascii=False, indent=2)
    raw = content.encode("utf-8")
    descriptor = ArtifactDescriptor("fixtures/session.json", "obs-session", "canonical-session", "application/json", "utf-8", len(raw), hashlib.sha256(raw).hexdigest(), (len(raw) + 2) // 3, "canonical-session", True)
    return CanonicalSessionChunker(soft_target_tokens=soft_target_tokens, hard_ceiling_tokens=1_000).chunk(descriptor, content)


class LexicalRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DeterministicLexicalRetrievalEngine()

    def test_repeated_ranking_report_and_fingerprint_are_identical(self) -> None:
        source = catalog([message(0, "primary evidence"), message(1, "other primary evidence")])
        first = self.engine.retrieve("primary evidence", source, token_budget=1_000)
        second = self.engine.retrieve("primary evidence", source, token_budget=1_000)
        self.assertEqual(first, second)
        self.assertEqual(first.report.to_json(), second.report.to_json())
        self.assertEqual(first.report.retrieval_fingerprint, second.report.retrieval_fingerprint)

    def test_exact_phrase_and_term_frequency_scoring(self) -> None:
        source = catalog([message(0, "primary evidence primary evidence"), message(1, "primary only")])
        result = self.engine.retrieve('"primary evidence" primary', source, token_budget=1_000)
        self.assertGreaterEqual(result.report.rankings[0].score, EXACT_PHRASE_WEIGHT + 2 * TERM_WEIGHT)
        self.assertEqual(result.report.rankings[0].chunk.chunk_index, 0)

    def test_ties_break_by_chunk_index_and_metadata_is_not_scored(self) -> None:
        source = catalog([message(0, "same"), message(1, "same")])
        tied = self.engine.retrieve("same", source, token_budget=1_000)
        self.assertEqual([item.chunk.chunk_index for item in tied.report.rankings], [0, 1])
        metadata_only = self.engine.retrieve("metadata-only-term", source, token_budget=1_000)
        self.assertEqual(metadata_only.selected_chunks, ())

    def test_identifier_scoring_and_repeated_query_term_deduplication(self) -> None:
        source = catalog([message(0, "unrelated", message_id="provider-serialization")])
        identifier = self.engine.retrieve("provider", source, token_budget=1_000)
        self.assertEqual(identifier.report.rankings[0].score, IDENTIFIER_WEIGHT)
        repeated = self.engine.retrieve("provider provider provider", source, token_budget=1_000)
        self.assertEqual(repeated.report.rankings[0].score, identifier.report.rankings[0].score)

    def test_budget_selects_only_complete_chunks_and_reports_partial_coverage(self) -> None:
        source = catalog([message(0, "needle " + "x" * 80), message(1, "needle " + "y" * 80)], soft_target_tokens=90)
        first_chunk_tokens = self.engine._estimate_tokens(source.chunks[0].content)
        result = self.engine.retrieve("needle", source, token_budget=first_chunk_tokens)
        self.assertEqual(len(result.selected_chunks), 1)
        self.assertLessEqual(result.report.estimated_token_usage, first_chunk_tokens)
        self.assertEqual(result.report.coverage[0].status, CoverageStatus.PARTIAL)
        self.assertEqual(result.selected_chunks[0].content, source.chunks[0].content)

    def test_maximum_selection_and_unfittable_higher_ranked_chunk(self) -> None:
        source = catalog([message(0, "needle " * 10 + "x" * 100), message(1, "needle")], soft_target_tokens=90)
        smaller_tokens = self.engine._estimate_tokens(source.chunks[1].content)
        selected = self.engine.retrieve("needle", source, token_budget=smaller_tokens, max_selected_chunks=1)
        self.assertEqual([chunk.chunk_index for chunk in selected.selected_chunks], [1])
        unrestricted = self.engine.retrieve("needle", source, token_budget=1_000, max_selected_chunks=1)
        self.assertEqual(len(unrestricted.selected_chunks), 1)

    def test_complete_coverage_zero_budget_and_empty_catalog(self) -> None:
        source = catalog([message(0, "needle")])
        complete = self.engine.retrieve("needle", source, token_budget=1_000)
        self.assertEqual(complete.report.coverage[0].status, CoverageStatus.COMPLETE)
        zero = self.engine.retrieve("needle", source, token_budget=0)
        self.assertEqual(zero.selected_chunks, ())
        self.assertEqual(zero.report.coverage[0].status, CoverageStatus.EMPTY)
        empty = self.engine.retrieve("needle", catalog([]), token_budget=0)
        self.assertEqual(empty.report.coverage[0].status, CoverageStatus.EMPTY)
        self.assertEqual(empty.report.rankings, ())

    def test_empty_and_punctuation_queries_are_empty_and_explicit(self) -> None:
        source = catalog([message(0, "needle")])
        for query in ("", "   ", "!!!"):
            with self.subTest(query=query):
                result = self.engine.retrieve(query, source, token_budget=1_000)
                self.assertEqual(result.selected_chunks, ())
                self.assertFalse(result.report.diagnostics.searchable_terms_present)
                self.assertEqual(result.report.coverage[0].status, CoverageStatus.EMPTY)
                self.assertIn("no searchable lexical terms", result.report.rankings[0].reason)

    def test_rejects_unsupported_context_and_noncanonical_catalog(self) -> None:
        source = catalog([message(0, "needle")])
        with self.assertRaisesRegex(ValueError, "surrounding_context"):
            self.engine.retrieve("needle", source, token_budget=1_000, surrounding_context="neighbor")  # type: ignore[arg-type]
        other_descriptor = replace(source.descriptor, artifact_type="other")
        other_chunks = tuple(replace(chunk, artifact_type="other") for chunk in source.chunks)
        other_catalog = ChunkCatalog(other_descriptor, other_chunks, source.total_logical_units)
        with self.assertRaisesRegex(ValueError, "canonical-session"):
            self.engine.retrieve("needle", other_catalog, token_budget=1_000)

    def test_rejects_content_that_disagrees_with_declared_message_range(self) -> None:
        source = catalog([message(0, "needle"), message(1, "needle")], soft_target_tokens=90)
        original = source.chunks[0]
        cases = []
        messages = json.loads(original.content)
        cases.append((messages[:-1], original.source_range, "message count"))
        cases.append((messages, replace(original.source_range, start_message_id="wrong-start"), "starting message ID"))
        cases.append((messages, replace(original.source_range, end_message_id="wrong-end"), "ending message ID"))
        wrong_order = json.loads(original.content)
        wrong_order[0]["source_order"] = 99
        cases.append((wrong_order, original.source_range, "source_order sequence"))
        for parsed, source_range, expected in cases:
            with self.subTest(expected=expected):
                content = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                bad_chunk = replace(original, content=content, chunk_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(), source_range=source_range)
                bad_catalog = replace(source, chunks=(bad_chunk, *source.chunks[1:]))
                with self.assertRaisesRegex(ValueError, expected):
                    self.engine.retrieve("needle", bad_catalog, token_budget=1_000)

    def test_provenance_and_content_remain_unchanged_and_no_runtime_integration_is_used(self) -> None:
        source = catalog([message(0, "needle")])
        original = source.chunks[0]
        with patch.dict(sys.modules, {"rip.reasoning": None, "rip.cli": None, "rip.console": None}):
            result = self.engine.retrieve("needle", source, token_budget=1_000)
        self.assertIs(result.selected_chunks[0], original)
        self.assertEqual(result.selected_chunks[0].to_json(), original.to_json())
        self.assertEqual(result.selected_chunks[0].source_observation_id, "obs-session")
