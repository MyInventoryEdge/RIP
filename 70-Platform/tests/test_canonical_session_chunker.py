from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from rip.retrieval.canonical_session import (
    CanonicalSessionChunker,
    OversizedLogicalUnitError,
    reassemble_messages,
)
from rip.retrieval.models import ArtifactDescriptor


def message(index: int, markdown: str = "text") -> dict[str, object]:
    return {"source_message_id": f"message-{index}", "source_order": index, "participant_id": "role:user", "role": "user", "markdown": markdown, "searchable_text": markdown, "code_blocks": [], "links": [], "images": [], "attachments": [], "source_metadata": {}}


def session(messages: list[dict[str, object]]) -> dict[str, object]:
    return {"session_id": "session-1", "source_format": "chatgpt-conversation-json", "source_metadata": {}, "participants": [], "messages": messages, "statistics": {}, "validation": {"passed": True, "errors": [], "warnings": [], "input_message_count": len(messages), "output_message_count": len(messages)}}


def content(messages: list[dict[str, object]]) -> str:
    return json.dumps(session(messages), ensure_ascii=False, indent=2)


def descriptor(text: str) -> ArtifactDescriptor:
    raw = text.encode("utf-8")
    return ArtifactDescriptor("fixtures/canonical-session.json", "obs-canonical", "canonical-session", "application/json", "utf-8", len(raw), hashlib.sha256(raw).hexdigest(), (len(raw) + 2) // 3, "canonical-session", True)


class CanonicalSessionChunkerTests(unittest.TestCase):
    def chunk(self, messages: list[dict[str, object]], **kwargs: int):
        text = content(messages)
        return CanonicalSessionChunker(**kwargs).chunk(descriptor(text), text)

    def test_empty_session(self) -> None:
        catalog = self.chunk([])
        self.assertEqual(catalog.chunks, ())
        self.assertEqual(catalog.total_logical_units, 0)
        self.assertEqual(reassemble_messages(catalog), ())

    def test_single_message_and_reassembly(self) -> None:
        messages = [message(0, "# Markdown\n\n```python\nprint('exact')\n```")]
        catalog = self.chunk(messages)
        self.assertEqual(len(catalog.chunks), 1)
        self.assertEqual(reassemble_messages(catalog), tuple(messages))
        self.assertEqual(catalog.chunks[0].versions, CanonicalSessionChunker.versions)
        self.assertEqual(catalog.chunks[0].source_observation_id, "obs-canonical")

    def test_multiple_chunks_respect_soft_target_without_splitting_messages(self) -> None:
        messages = [message(index, "x" * 40) for index in range(3)]
        catalog = self.chunk(messages, soft_target_tokens=50, hard_ceiling_tokens=100)
        self.assertEqual([chunk.source_range.unit_count for chunk in catalog.chunks], [1, 1, 1])
        self.assertEqual(reassemble_messages(catalog), tuple(messages))

    def test_exact_and_just_over_soft_target_boundaries(self) -> None:
        one = message(0, "x" * 20)
        exact_tokens = CanonicalSessionChunker._estimate_tokens(json.dumps([one], ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        exact = self.chunk([one], soft_target_tokens=exact_tokens, hard_ceiling_tokens=exact_tokens + 1)
        self.assertEqual(len(exact.chunks), 1)
        messages = [message(0, "x" * 20), message(1, "x" * 20)]
        over = self.chunk(messages, soft_target_tokens=exact_tokens, hard_ceiling_tokens=exact_tokens * 3)
        self.assertEqual(len(over.chunks), 2)

    def test_oversized_message_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(OversizedLogicalUnitError, "message 0.*hard ceiling"):
            self.chunk([message(0, "x" * 1000)], soft_target_tokens=10, hard_ceiling_tokens=100)

    def test_repeated_execution_has_identical_catalog_ids_and_hashes(self) -> None:
        messages = [message(0), message(1)]
        first = self.chunk(messages)
        second = self.chunk(messages)
        self.assertEqual(first, second)
        self.assertEqual([item.chunk_id for item in first.chunks], [item.chunk_id for item in second.chunks])
        self.assertEqual([item.chunk_sha256 for item in first.chunks], [item.chunk_sha256 for item in second.chunks])

    def test_malformed_duplicate_and_invalid_order_are_rejected(self) -> None:
        malformed = "{}"
        with self.assertRaisesRegex(ValueError, "messages array"):
            CanonicalSessionChunker().chunk(descriptor(malformed), malformed)
        duplicate = [message(0), message(1)]
        duplicate[1]["source_message_id"] = "message-0"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.chunk(duplicate)
        invalid_order = [message(0), message(1)]
        invalid_order[1]["source_order"] = 4
        with self.assertRaisesRegex(ValueError, "source_order"):
            self.chunk(invalid_order)

    def test_file_entry_point_builds_repository_relative_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "sessions" / "canonical-session.json"
            target.parent.mkdir()
            target.write_text(content([message(0)]), encoding="utf-8")
            catalog = CanonicalSessionChunker().chunk_file(target, repository_root=root, source_observation_id="obs-file")
        self.assertEqual(catalog.descriptor.repository_relative_path, "sessions/canonical-session.json")
        self.assertEqual(catalog.chunks[0].source_observation_id, "obs-file")
