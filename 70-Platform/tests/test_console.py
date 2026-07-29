from __future__ import annotations

import unittest

from rip.console.app import format_details
from rip.reasoning.models import ReasoningResult


class ConsoleFormattingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
