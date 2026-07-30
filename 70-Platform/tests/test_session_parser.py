from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rip.session.parser import normalize_chatgpt_export, parse_session


class SessionParserTests(unittest.TestCase):
    def test_extracts_markdown_derivatives_deterministically(self) -> None:
        source = {
            "source_url": "https://chatgpt.com/c/example",
            "exported_at": "2026-07-30T00:00:00Z",
            "messages": [{
                "index": 7,
                "role": "assistant",
                "markdown": "# Heading\n\n[guide](https://example.com/guide) ![diagram](https://example.com/image.png)\n\n```python\nprint('hello')\n```\n\n[file](sandbox:/mnt/data/report.pdf)",
                "future_field": {"retained": True},
            }],
        }

        session = normalize_chatgpt_export(source)
        message = session.messages[0]

        self.assertTrue(session.validation.passed)
        self.assertEqual(message.source_message_id, "7")
        self.assertEqual(message.searchable_text, "Heading\n\nguide diagram\n\nprint('hello')\n\nfile")
        self.assertEqual(message.code_blocks[0].language, "python")
        self.assertEqual(message.links[0].url, "https://example.com/guide")
        self.assertEqual(message.images[0].alt_text, "diagram")
        self.assertEqual(message.attachments[0].name, "file")
        self.assertEqual(message.source_metadata["future_field"], {"retained": True})
        self.assertIn("no upstream ChatGPT turn IDs", session.validation.warnings[0])

    def test_rejects_duplicate_source_identifiers(self) -> None:
        source = {"messages": [{"id": "same", "index": 1, "role": "user", "markdown": "one"}, {"id": "same", "index": 2, "role": "assistant", "markdown": "two"}]}
        with self.assertRaisesRegex(ValueError, "Duplicate source message identifier"):
            normalize_chatgpt_export(source)

    def test_production_export_normalizes_all_messages(self) -> None:
        fixture = Path(__file__).resolve().parents[2] / "tools" / "chatgpt-exporter" / "validation-export-complete" / "conversation.json"
        self.assertTrue(fixture.exists(), "Production fixture is required for this parser test.")
        with tempfile.TemporaryDirectory() as directory:
            session = parse_session(fixture, Path(directory))
            self.assertTrue(session.validation.passed)
            self.assertEqual(session.statistics.message_count, 1334)
            self.assertEqual(session.validation.input_message_count, session.validation.output_message_count)
            self.assertTrue((Path(directory) / "canonical-session.json").exists())
            self.assertTrue((Path(directory) / "canonical-session.md").exists())
            manifest = json.loads((Path(directory) / "parser-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["validation"]["passed"])


if __name__ == "__main__":
    unittest.main()
