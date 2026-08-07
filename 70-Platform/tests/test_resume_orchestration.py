from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rip.onboarding import ClassificationReadiness, ClassificationScope, EvidenceClass, IntegrityTreatment, accept_decision, create_organization_workspace, observe_organization, preview_scope, recommend_reasoning_capability, request_evidence_classification, restart_onboarding_run, resume_governed_onboarding
from tests.trust_test_context import trust_context


class ResumeOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repository = base / "customer"; (self.repository / "src").mkdir(parents=True)
        self.source = self.repository / "src" / "app.py"; self.source.write_text("print('customer')\n", encoding="utf-8")
        self.workspace = create_organization_workspace(base / "workspaces", organization_id="acme-org", display_name="Acme", repository_path=self.repository)
        capability = recommend_reasoning_capability(environment={"OPENAI_API_KEY": "test"})
        self.context = restart_onboarding_run(self.workspace, repository_path=self.repository, reasoning_capability=capability, environment={"OPENAI_API_KEY": "test"})
        self.journal_context = trust_context(base)
        observe_organization(self.context)
        self.root = Path(self.workspace.workspace_path); self.run = self.root / "onboarding-runs" / self.context.onboarding_run_id
        self.manifest = json.loads((self.run / "final-source-manifest.json").read_text(encoding="utf-8"))
        self.request = request_evidence_classification(self.context, target="**", scope=ClassificationScope.PATH_GLOB, proposed_evidence_class=EvidenceClass.OPERATIONAL_STATE, proposed_integrity_treatment=IntegrityTreatment.BLOCKING, requester_identity="requester", requester_role="operator", authority_claim="request authority", rationale="Review.")
        preview = preview_scope(self.manifest, target=self.request.target, scope=self.request.scope)
        accept_decision(workspace=str(self.root), manifest=self.manifest, request=self.request, preview=preview, evidence_class=EvidenceClass.OPERATIONAL_STATE, integrity_treatment=IntegrityTreatment.BLOCKING, reviewer_identity="gatekeeper", reviewer_role="reviewer", authority_claim="authority", rationale="Approved.")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ready_run_performs_fresh_verification_and_advances_only_through_lifecycle(self) -> None:
        result = resume_governed_onboarding(workspace=self.root, organization_id=self.context.organization_id, onboarding_run_id=self.context.onboarding_run_id, journal_context=self.journal_context)
        self.assertTrue(result.continued)
        self.assertEqual(ClassificationReadiness.READY, result.readiness)
        self.assertIn("Fresh source verification succeeded", result.message)
        self.assertEqual("observed", json.loads((self.run / "state.json").read_text(encoding="utf-8"))["state"])
        self.assertTrue((self.run / "classification-evaluation.json").is_file())

    def test_changed_source_does_not_trigger_classification_owned_verification(self) -> None:
        immutable = {path.name: path.read_bytes() for directory in ("requests", "decisions", "records") for path in (self.run / "classifications" / directory).glob("*.json")}
        self.source.write_text("print('changed')\n", encoding="utf-8")
        result = resume_governed_onboarding(workspace=self.root, organization_id=self.context.organization_id, onboarding_run_id=self.context.onboarding_run_id, journal_context=self.journal_context)
        self.assertTrue(result.continued)
        self.assertEqual(ClassificationReadiness.READY, result.readiness)
        self.assertFalse((self.run / "resume-integrity-difference.json").is_file())
        for directory in ("requests", "decisions", "records"):
            for path in (self.run / "classifications" / directory).glob("*.json"):
                self.assertEqual(immutable[path.name], path.read_bytes())

    def test_nonready_result_does_not_execute_resume_or_customer_verification(self) -> None:
        for directory in ("decisions", "records"):
            for path in (self.run / "classifications" / directory).glob("*.json"):
                path.unlink()
        result = resume_governed_onboarding(workspace=self.root, organization_id=self.context.organization_id, onboarding_run_id=self.context.onboarding_run_id, journal_context=self.journal_context)
        self.assertFalse(result.continued)
        self.assertEqual(ClassificationReadiness.AWAITING_CLASSIFICATION, result.readiness)
        self.assertEqual("awaiting-classification", json.loads((self.run / "state.json").read_text(encoding="utf-8"))["state"])


if __name__ == "__main__":
    unittest.main()
