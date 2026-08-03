from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from rip.onboarding import (
    ClassificationReadiness,
    ClassificationRequestStatus,
    ClassificationScope,
    EvidenceClass,
    IntegrityTreatment,
    create_classification_decision,
    create_classification_request,
    create_evidence_classification,
    create_classification_policy,
    create_organization_workspace,
    observe_organization,
    persist_contract,
    recommend_reasoning_capability,
    request_evidence_classification,
    restart_onboarding_run,
)
from rip.onboarding.classification_integration import integrate_persisted_classifications
from rip.onboarding.decision_service import accept_decision
from rip.onboarding.scope_preview import preview_scope


class ClassificationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repository = base / "customer"
        (self.repository / "src").mkdir(parents=True)
        (self.repository / "src" / "app.py").write_text("print('customer')\n", encoding="utf-8")
        self.source_before = (self.repository / "src" / "app.py").read_bytes()
        self.workspace = create_organization_workspace(base / "workspaces", organization_id="acme-org", display_name="Acme", repository_path=self.repository)
        capability = recommend_reasoning_capability(environment={"OPENAI_API_KEY": "test"})
        self.context = restart_onboarding_run(self.workspace, repository_path=self.repository, reasoning_capability=capability, environment={"OPENAI_API_KEY": "test"})
        observe_organization(self.context)
        self.root = Path(self.workspace.workspace_path)
        self.run = self.root / "onboarding-runs" / self.context.onboarding_run_id
        self.manifest = json.loads((self.run / "final-source-manifest.json").read_text(encoding="utf-8"))
        self.request = request_evidence_classification(
            self.context, target="src/app.py", scope=ClassificationScope.EXACT_PATH,
            proposed_evidence_class=EvidenceClass.OPERATIONAL_STATE,
            proposed_integrity_treatment=IntegrityTreatment.BLOCKING,
            requester_identity="requester", requester_role="operator", authority_claim="request authority", rationale="Review.",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def accept(self):
        preview = preview_scope(self.manifest, target=self.request.target, scope=self.request.scope)
        return accept_decision(
            workspace=str(self.root), manifest=self.manifest, request=self.request, preview=preview,
            evidence_class=EvidenceClass.OPERATIONAL_STATE, integrity_treatment=IntegrityTreatment.BLOCKING,
            reviewer_identity="gatekeeper", reviewer_role="reviewer", authority_claim="authority", rationale="Approved.",
        )

    def test_unresolved_request_is_awaiting_and_summary_is_deterministic(self) -> None:
        first = integrate_persisted_classifications(workspace=self.root, onboarding_run_id=self.context.onboarding_run_id)
        second = integrate_persisted_classifications(workspace=self.root, onboarding_run_id=self.context.onboarding_run_id)
        self.assertEqual(first, second)
        self.assertEqual(first.readiness, ClassificationReadiness.AWAITING_CLASSIFICATION)
        self.assertEqual(first.unresolved_request_ids, (self.request.request_id,))
        self.assertTrue((self.run / "classification-integration.json").is_file())
        self.assertEqual(self.source_before, (self.repository / "src" / "app.py").read_bytes())

    def test_approved_records_reconstruct_policy_and_persist_effective_snapshot(self) -> None:
        decision, record = self.accept()
        result = integrate_persisted_classifications(workspace=self.root, onboarding_run_id=self.context.onboarding_run_id)
        self.assertIn(decision.decision_id, result.decision_ids)
        self.assertIn(record.classification_id, result.record_ids)
        self.assertIsNotNone(result.policy_history.policy)
        self.assertTrue((self.run / "classifications" / "policies" / f"{result.policy_history.policy.policy_id}.json").is_file())
        self.assertEqual((), result.unresolved_request_ids)

    def test_malformed_foreign_and_stale_persisted_records_are_rejected(self) -> None:
        request_path = self.run / "classifications" / "requests" / f"{self.request.request_id}.json"
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        payload["schema"] = "wrong"
        request_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported schema"):
            integrate_persisted_classifications(workspace=self.root, onboarding_run_id=self.context.onboarding_run_id)

        persist_contract(self.root, create_classification_request(
            request_id="foreign-request", organization_id="other-org", onboarding_run_id=self.context.onboarding_run_id,
            source_manifest_fingerprint=self.request.source_manifest_fingerprint, target=self.request.target, scope=self.request.scope,
            proposed_evidence_class=EvidenceClass.OPERATIONAL_STATE, proposed_integrity_treatment=IntegrityTreatment.BLOCKING,
            requester_identity="x", requester_role="x", authority_claim="x", rationale="x", created_at=None,
        ))
        request_path.write_text(json.dumps({"schema": "rip.evidence-classification.v1", "contract": {**json.loads(request_path.read_text(encoding="utf-8"))["contract"], "fingerprint": self.request.fingerprint}}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "foreign"):
            integrate_persisted_classifications(workspace=self.root, onboarding_run_id=self.context.onboarding_run_id)

    def test_stale_policy_and_retained_source_have_explicit_readiness(self) -> None:
        stale_policy = create_classification_policy(
            policy_id="stale-policy", organization_id=self.request.organization_id, onboarding_run_id=self.request.onboarding_run_id,
            source_manifest_fingerprint="f" * 64, classifications=(),
        )
        persist_contract(self.root, stale_policy)
        result = integrate_persisted_classifications(workspace=self.root, onboarding_run_id=self.context.onboarding_run_id)
        self.assertEqual(result.readiness, ClassificationReadiness.STALE_POLICY)
        (self.run / "classification-integration.json").unlink()
        recovery_path = self.run / "classification-recovery.json"
        recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
        recovery["source_manifest_fingerprint"] = "e" * 64
        recovery_path.write_text(json.dumps(recovery), encoding="utf-8")
        result = integrate_persisted_classifications(workspace=self.root, onboarding_run_id=self.context.onboarding_run_id)
        self.assertEqual(result.readiness, ClassificationReadiness.STALE_SOURCE)

    def test_conflict_blocks_without_lifecycle_mutation(self) -> None:
        first_decision, first_record = self.accept()
        second_request = create_classification_request(
            request_id="request-second", organization_id=self.request.organization_id, onboarding_run_id=self.request.onboarding_run_id,
            source_manifest_fingerprint=self.request.source_manifest_fingerprint, target=self.request.target, scope=self.request.scope,
            proposed_evidence_class=EvidenceClass.INVENTORY_ONLY, proposed_integrity_treatment=IntegrityTreatment.BLOCKING,
            requester_identity="requester", requester_role="operator", authority_claim="authority", rationale="Second.", created_at=None,
        )
        persist_contract(self.root, second_request)
        second_decision = create_classification_decision(
            decision_id="decision-second", request_id=second_request.request_id, request_fingerprint=second_request.fingerprint,
            organization_id=second_request.organization_id, onboarding_run_id=second_request.onboarding_run_id,
            status=ClassificationRequestStatus.APPROVED, decided_evidence_class=EvidenceClass.INVENTORY_ONLY,
            decided_integrity_treatment=IntegrityTreatment.BLOCKING, reviewer_identity="gatekeeper", reviewer_role="reviewer",
            authority_claim="authority", rationale="Approved.", supersedes_decision_id=None, decided_at=None,
        )
        second_record = create_evidence_classification(
            classification_id="record-second", organization_id=second_request.organization_id, onboarding_run_id=second_request.onboarding_run_id,
            target=second_request.target, scope=second_request.scope, evidence_class=EvidenceClass.INVENTORY_ONLY,
            integrity_treatment=IntegrityTreatment.BLOCKING, source_manifest_fingerprint=second_request.source_manifest_fingerprint,
            decision_id=second_decision.decision_id, decision_fingerprint=second_decision.fingerprint, supersedes_classification_id=None,
        )
        persist_contract(self.root, second_decision)
        persist_contract(self.root, second_record)
        state_before = (self.run / "state.json").read_bytes()
        result = integrate_persisted_classifications(workspace=self.root, onboarding_run_id=self.context.onboarding_run_id)
        self.assertEqual(result.readiness, ClassificationReadiness.BLOCKED_BY_CONFLICT)
        self.assertEqual(state_before, (self.run / "state.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
