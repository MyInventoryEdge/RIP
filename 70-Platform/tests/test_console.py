from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rip.console.app import format_details, format_discovery_details, format_voice_status, repository_relative_evidence
from rip.reasoning.service import DiscoveryDecision, DiscoveryMode
from rip.reasoning.models import ReasoningResult


class ConsoleFormattingTests(unittest.TestCase):
    def test_primary_evidence_becomes_repository_relative_and_rejects_outside(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "RIP"; root.mkdir(); (root / ".git").mkdir()
            inside = root / "artifact.txt"; inside.write_text("evidence")
            outside = Path(temp) / "outside.txt"; outside.write_text("outside")
            self.assertEqual("artifact.txt", repository_relative_evidence(inside, root))
            with self.assertRaises(ValueError): repository_relative_evidence(outside, root)
    def test_format_details_contains_reasoning_metadata(self) -> None:
        result = ReasoningResult(
            answer="Grounded answer",
            provider="openai",
            model="gpt-test",
            response_id="resp-123",
            input_tokens=100,
            output_tokens=25,
            cited_observation_ids=("obs-1", "obs-2"),
        )

        details = format_details(result, 1.25)

        self.assertIn("Provider: openai", details)
        self.assertIn("Model: gpt-test", details)
        self.assertIn("Elapsed: 1.2 seconds", details)
        self.assertIn("Input tokens: 100", details)
        self.assertIn("Output tokens: 25", details)
        self.assertIn("Cited observations: 2", details)
        self.assertIn("Response ID: resp-123", details)

    def test_format_voice_status_uses_public_manager_values(self) -> None:
        details = format_voice_status(
            {
                "enabled": True,
                "voice": "alloy",
                "microphone": 3,
                "microphone_name": "USB Microphone",
                "transcription_model": "gpt-4o-mini-transcribe",
            }
        )

        self.assertIn("Configured microphone: 3", details)
        self.assertIn("Resolved microphone: USB Microphone", details)
        self.assertIn("Configured voice: alloy", details)
        self.assertIn("Speech enabled: Yes", details)
        self.assertIn("Transcription model: gpt-4o-mini-transcribe", details)

    def test_discovery_details_exposes_mode_foundation_and_diagnostics(self) -> None:
        details = format_discovery_details(
            DiscoveryDecision(
                DiscoveryMode.AUTOMATIC,
                True,
                True,
                (),
                reason="Foundation-only",
            )
        )
        self.assertIn("Mode: automatic", details)
        self.assertIn("Foundation-only: Yes", details)
        self.assertIn("Reason: Foundation-only", details)


if __name__ == "__main__":
    unittest.main()
