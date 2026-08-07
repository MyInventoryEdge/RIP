from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rip.onboarding import (
    ClassificationReadiness,
    ClassificationRequestStatus,
    ClassificationScope,
    EvidenceClass,
    IntegrityTreatment,
    create_classification_policy,
    create_classification_decision,
    create_evidence_classification,
    create_organization_workspace,
    observe_organization,
    recommend_reasoning_capability,
    request_evidence_classification,
    restart_onboarding_run,
    resume_after_classification,
)
from tests.trust_test_context import trust_context


class EvidenceClassificationLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repository = self.base / "customer"
        (self.repository / "src").mkdir(parents=True)
        (self.repository / "src" / "app.py").write_text("print('customer')\n", encoding="utf-8")
        self.workspace = create_organization_workspace(self.base / "workspaces", organization_id="acme-org", display_name="Acme", repository_path=self.repository)
        self.context = restart_onboarding_run(self.workspace, repository_path=self.repository, reasoning_capability=recommend_reasoning_capability(environment={"OPENAI_API_KEY": "test"}), environment={"OPENAI_API_KEY": "test"})
        self.journal_context = trust_context(self.base)
        observe_organization(self.context)
        self.run_root = Path(self.workspace.workspace_path) / "onboarding-runs" / self.context.onboarding_run_id

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_request_pauses_without_discarding_completed_observation_and_emits_attention(self) -> None:
        before = {name: (self.run_root / name).read_bytes() for name in ("initial-source-manifest.json", "final-source-manifest.json", "observation.json")}
        request = request_evidence_classification(
            self.context, target="src/app.py", scope=ClassificationScope.EXACT_PATH,
            proposed_evidence_class=EvidenceClass.OPERATIONAL_STATE,
            proposed_integrity_treatment=IntegrityTreatment.BLOCKING, requester_identity="operator",
            requester_role="owner", authority_claim="claimed authority", rationale="Needs review.",
        )
        self.assertTrue((self.run_root / "classifications" / "requests" / f"{request.request_id}.json").is_file())
        self.assertEqual("awaiting-classification", json.loads((self.run_root / "state.json").read_text(encoding="utf-8"))["state"])
        self.assertEqual(before, {name: (self.run_root / name).read_bytes() for name in before})
        events = json.loads((Path(self.workspace.workspace_path) / "attention-events.json").read_text(encoding="utf-8"))
        self.assertEqual("classification-required", events[0]["event_type"])
        with self.assertRaisesRegex(ValueError, "not ready"):
            observe_organization(self.context)

    def test_resume_requires_fresh_safe_boundary_and_approved_policy(self) -> None:
        request = request_evidence_classification(
            self.context, target="src/app.py", scope=ClassificationScope.EXACT_PATH,
            proposed_evidence_class=EvidenceClass.OPERATIONAL_STATE,
            proposed_integrity_treatment=IntegrityTreatment.BLOCKING, requester_identity="operator",
            requester_role="owner", authority_claim="claimed authority", rationale="Needs review.",
        )
        manifest = json.loads((self.run_root / "final-source-manifest.json").read_text(encoding="utf-8"))
        decision = create_classification_decision(
            decision_id="decision-001", request_id=request.request_id, request_fingerprint=request.fingerprint,
            organization_id=self.context.organization_id, onboarding_run_id=self.context.onboarding_run_id,
            status=ClassificationRequestStatus.APPROVED, decided_evidence_class=EvidenceClass.ORGANIZATIONAL_EVIDENCE,
            decided_integrity_treatment=IntegrityTreatment.BLOCKING, reviewer_identity="reviewer", reviewer_role="owner",
            authority_claim="approved authority", rationale="Approved.", supersedes_decision_id=None, decided_at=None,
        )
        record = create_evidence_classification(
            classification_id="classification-all", organization_id=self.context.organization_id,
            onboarding_run_id=self.context.onboarding_run_id, target="**", scope=ClassificationScope.PATH_GLOB,
            evidence_class=EvidenceClass.ORGANIZATIONAL_EVIDENCE, integrity_treatment=IntegrityTreatment.BLOCKING,
            source_manifest_fingerprint=manifest["manifest_fingerprint"], decision_id=decision.decision_id,
            decision_fingerprint=decision.fingerprint, supersedes_classification_id=None,
        )
        policy = create_classification_policy(policy_id="policy-001", organization_id=self.context.organization_id, onboarding_run_id=self.context.onboarding_run_id, source_manifest_fingerprint=manifest["manifest_fingerprint"], classifications=(record,))
        recovery = resume_after_classification(self.context, policy, decisions=(decision,), journal_context=self.journal_context)
        self.assertEqual(ClassificationReadiness.READY, recovery.readiness)
        self.assertEqual("observed", json.loads((self.run_root / "state.json").read_text(encoding="utf-8"))["state"])
        self.assertTrue((self.run_root / "classification-evaluation.json").is_file())

    def test_classification_does_not_own_source_reverification(self) -> None:
        request_evidence_classification(
            self.context, target="src/app.py", scope=ClassificationScope.EXACT_PATH,
            proposed_evidence_class=EvidenceClass.OPERATIONAL_STATE,
            proposed_integrity_treatment=IntegrityTreatment.BLOCKING, requester_identity="operator",
            requester_role="owner", authority_claim="claimed authority", rationale="Needs review.",
        )
        manifest = json.loads((self.run_root / "final-source-manifest.json").read_text(encoding="utf-8"))
        policy = create_classification_policy(policy_id="policy-001", organization_id=self.context.organization_id, onboarding_run_id=self.context.onboarding_run_id, source_manifest_fingerprint=manifest["manifest_fingerprint"], classifications=())
        observation = (self.run_root / "observation.json").read_bytes()
        (self.repository / "src" / "app.py").write_text("changed\n", encoding="utf-8")
        recovery = resume_after_classification(self.context, policy, decisions=())
        self.assertEqual(observation, (self.run_root / "observation.json").read_bytes())
        self.assertFalse((self.run_root / "resume-integrity-difference.json").is_file())
        self.assertNotEqual(ClassificationReadiness.READY, recovery.readiness)


if __name__ == "__main__":
    unittest.main()
