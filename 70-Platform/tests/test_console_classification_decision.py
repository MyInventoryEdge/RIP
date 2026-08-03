from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rip.console.app import format_classification_readiness, submit_console_classification_decision
from rip.onboarding import (
    ClassificationReadiness,
    ClassificationScope,
    EvidenceClass,
    IntegrityTreatment,
    create_classification_request,
)


class ConsoleClassificationDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = create_classification_request(
            request_id="request-001", organization_id="acme", onboarding_run_id="run-001",
            source_manifest_fingerprint="a" * 64, target="state/report.json",
            scope=ClassificationScope.EXACT_PATH,
            proposed_evidence_class=EvidenceClass.OPERATIONAL_STATE,
            proposed_integrity_treatment=IntegrityTreatment.NON_BLOCKING_REPORTED,
            requester_identity="rip", requester_role="system", authority_claim="needs review",
            rationale="Classify retained report.", created_at=None,
        )

    def test_submission_orchestrates_only_promoted_services_and_presents_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest_path = root / "onboarding-runs" / "run-001" / "final-source-manifest.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps({"manifest_fingerprint": "a" * 64, "entries": [{"path": "state/report.json", "kind": "file", "value": "", "size": 1}]}), encoding="utf-8")
            decision = SimpleNamespace(decision_id="decision-001")
            record = SimpleNamespace(classification_id="record-001")
            integration = SimpleNamespace(readiness=ClassificationReadiness.AWAITING_CLASSIFICATION, unresolved_request_ids=("request-other",))
            with patch("rip.console.app.load_persisted_classification_request", return_value=self.request) as load, patch("rip.console.app.preview_scope", return_value=SimpleNamespace()) as preview, patch("rip.console.app.accept_decision", return_value=(decision, record)) as accept, patch("rip.console.app.integrate_persisted_classifications", return_value=integration) as integrate:
                result = submit_console_classification_decision(
                    workspace=str(root), onboarding_run_id="run-001", request_id="request-001",
                    evidence_class=EvidenceClass.OPERATIONAL_STATE,
                    integrity_treatment=IntegrityTreatment.NON_BLOCKING_REPORTED,
                    reviewer_identity="Pat", reviewer_role="Gatekeeper", authority_claim="classification authority", rationale="Reviewed.",
                )
            load.assert_called_once_with(str(root), "run-001", "request-001")
            self.assertEqual("a" * 64, accept.call_args.kwargs["manifest"]["manifest_fingerprint"])
            self.assertIs(preview.return_value, accept.call_args.kwargs["preview"])
            integrate.assert_called_once_with(workspace=root, onboarding_run_id="run-001")
            self.assertEqual(ClassificationReadiness.AWAITING_CLASSIFICATION, result.readiness)
            self.assertEqual(("Unresolved classification requests remain.",), result.blocking_conditions)
            rendered = format_classification_readiness(result)
            self.assertIn("Readiness: awaiting-classification", rendered)
            self.assertIn("No customer source was modified.", rendered)
            self.assertIn("Onboarding was not resumed.", rendered)

    def test_blocking_readiness_is_presented_without_local_evaluation(self) -> None:
        result = SimpleNamespace(
            decision_id="decision-001", classification_id="record-001",
            readiness=ClassificationReadiness.BLOCKED_BY_CONFLICT,
            blocking_conditions=("Effective classifications conflict.",),
        )
        rendered = format_classification_readiness(result)  # type: ignore[arg-type]
        self.assertIn("blocked-by-conflict", rendered)
        self.assertIn("Effective classifications conflict.", rendered)

    def test_console_source_uses_promoted_services_and_not_lifecycle_actions(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "rip" / "console" / "app.py").read_text(encoding="utf-8")
        section = source[source.index("def submit_console_classification_decision"):source.index("def repository_relative_evidence")]
        self.assertIn("accept_decision(", section)
        self.assertIn("integrate_persisted_classifications(", section)
        self.assertIn("preview_scope(", section)
        self.assertNotIn("resume_after_classification(", section)
        self.assertNotIn("evaluate_classification_readiness(", section)
        self.assertNotIn("restart_onboarding_run(", section)


if __name__ == "__main__":
    unittest.main()
