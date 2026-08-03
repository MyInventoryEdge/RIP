from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rip.console.app import format_details, format_discovery_details, format_observation_summary, format_understanding_meter, format_understanding_proposal, format_voice_status, repository_relative_evidence
from rip.onboarding import (
    ObservationMode,
    ObservationRun,
    ObservationSummary,
    ObservationSummaryItem,
    OnboardingRunState,
    OrganizationContext,
    ReasoningCapability,
    UnderstandingDimension,
    UnderstandingMeter,
    UnderstandingState,
)
from rip.reasoning.service import DiscoveryDecision, DiscoveryMode
from rip.reasoning.models import ReasoningResult


class ConsoleFormattingTests(unittest.TestCase):

    def test_classification_review_console_is_read_only_and_uses_shared_review_model(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "rip" / "console" / "app.py").read_text(encoding="utf-8")
        self.assertIn("class ClassificationReviewWindow", source)
        self.assertIn("load_classification_review", source)
        self.assertIn("format_classification_review", source)
        self.assertIn("Review Classification", source)
        self.assertIn("Show Complete Diagnostics", source)
        self.assertIn("Onboarding paused safely. Completed work was preserved.", source)
        self.assertNotIn("resume_after_classification(", source)
        self.assertNotIn("create_classification_decision(", source)
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

    def test_onboarding_formats_observation_summary_and_understanding_without_time_estimates(self) -> None:
        capability = ReasoningCapability("test", "model", "Test", True, True, True)
        context = OrganizationContext("acme-org", "run-001", "C:/repo", "C:/workspace", ObservationMode.READ_ONLY, capability)
        item = ObservationSummaryItem(UnderstandingState.OBSERVED, "Repository observed.", ("obs-123",), (".",))
        meter = UnderstandingMeter((UnderstandingDimension("Repositories", UnderstandingState.OBSERVED, ("obs-123",), (".",), "Repository scope established."),), "0" * 64)
        summary = ObservationSummary((item,), (), (), (), "1" * 64)
        run = ObservationRun(context, OnboardingRunState.OBSERVED, (), meter, summary, "2" * 64, "3" * 64)
        self.assertIn("Repositories: Observed", format_understanding_meter(run))
        self.assertIn("Observed", format_observation_summary(run))
        self.assertIn("Repository observed.", format_observation_summary(run))

    def test_observation_banner_is_scoped_to_onboarding_not_the_reasoning_console(self) -> None:
        source = Path(__import__("rip.console.app", fromlist=["__file__"]).__file__).read_text(encoding="utf-8")
        onboarding = source[source.index("class OnboardingWindow"):source.index("class RipConsole")]
        console = source[source.index("class RipConsole"):]
        self.assertIn("Customer Sources — Read Only", onboarding)
        self.assertIn("Onboarding records are written only to the isolated RIP workspace.", onboarding)
        self.assertNotIn("Observation Mode — Read Only", console)


    def test_proposal_experience_layer_uses_human_language_and_non_authority_disclosure(self) -> None:
        source = Path(__import__("rip.console.app", fromlist=["__file__"]).__file__).read_text(encoding="utf-8")
        presentation = source[source.index("def format_understanding_proposal"):source.index("class OnboardingWindow")]
        self.assertIn("Customer-supplied knowledge", presentation)
        self.assertIn("This proposal is not governance, Organizational Memory, approval, or activation.", presentation)
        self.assertNotIn("{statement.epistemic_label.value}", presentation)


if __name__ == "__main__":
    unittest.main()
