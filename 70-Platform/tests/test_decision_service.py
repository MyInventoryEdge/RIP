from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from rip.onboarding import (
    ClassificationRequestStatus,
    ClassificationScope,
    EvidenceClass,
    IntegrityTreatment,
    create_classification_decision,
    create_classification_request,
    create_organization_workspace,
    observe_organization,
    persist_contract,
    recommend_reasoning_capability,
    request_evidence_classification,
    restart_onboarding_run,
)
from rip.onboarding.decision_service import accept_decision, load_persisted_contracts
from rip.onboarding.scope_preview import preview_scope


class DecisionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repository = base / "customer"
        (self.repository / "src").mkdir(parents=True)
        (self.repository / "src" / "app.py").write_text("print('customer')\n", encoding="utf-8")
        self.before_source = (self.repository / "src" / "app.py").read_bytes()
        self.workspace = create_organization_workspace(base / "workspaces", organization_id="acme-org", display_name="Acme", repository_path=self.repository)
        capability = recommend_reasoning_capability(environment={"OPENAI_API_KEY": "test"})
        self.context = restart_onboarding_run(self.workspace, repository_path=self.repository, reasoning_capability=capability, environment={"OPENAI_API_KEY": "test"})
        observe_organization(self.context)
        self.root = Path(self.workspace.workspace_path)
        self.run_root = self.root / "onboarding-runs" / self.context.onboarding_run_id
        self.manifest = json.loads((self.run_root / "final-source-manifest.json").read_text(encoding="utf-8"))
        self.request = request_evidence_classification(
            self.context, target="src/app.py", scope=ClassificationScope.EXACT_PATH,
            proposed_evidence_class=EvidenceClass.OPERATIONAL_STATE,
            proposed_integrity_treatment=IntegrityTreatment.BLOCKING,
            requester_identity="requester", requester_role="operator",
            authority_claim="request authority", rationale="Review source state.",
        )
        self.preview = preview_scope(self.manifest, target=self.request.target, scope=self.request.scope)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def accept(self, **changes: object):
        values = dict(
            workspace=str(self.root), manifest=self.manifest, request=self.request, preview=self.preview,
            evidence_class=EvidenceClass.OPERATIONAL_STATE, integrity_treatment=IntegrityTreatment.BLOCKING,
            reviewer_identity="gatekeeper", reviewer_role="reviewer", authority_claim="classification authority",
            rationale="Approved after review.",
        )
        values.update(changes)
        return accept_decision(**values)  # type: ignore[arg-type]

    def test_persisted_unresolved_request_is_loaded_and_acceptance_preserves_authority_scope_and_sources(self) -> None:
        loaded = load_persisted_contracts(str(self.root), self.request.onboarding_run_id, "requests")
        self.assertEqual(loaded[0]["fingerprint"], self.request.fingerprint)
        decision, record = self.accept()
        self.assertEqual(decision.reviewer_identity, "gatekeeper")
        self.assertEqual(decision.reviewer_role, "reviewer")
        self.assertEqual(decision.authority_claim, "classification authority")
        self.assertEqual((record.target, record.scope), (self.request.target, self.request.scope))
        self.assertEqual(self.before_source, (self.repository / "src" / "app.py").read_bytes())
        self.assertTrue((self.run_root / "classifications" / "decisions" / f"{decision.decision_id}.json").is_file())
        self.assertTrue((self.run_root / "classifications" / "records" / f"{record.classification_id}.json").is_file())

    def test_missing_fingerprinted_and_resolved_requests_are_rejected(self) -> None:
        missing = replace(self.request, request_id="missing-request")
        with self.assertRaisesRegex(ValueError, "missing or not persisted"):
            self.accept(request=missing)
        fingerprint_mismatch = replace(self.request, fingerprint="b" * 64)
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.accept(request=fingerprint_mismatch)
        approved, _ = self.accept()
        with self.assertRaisesRegex(ValueError, "already resolved"):
            self.accept()
        self.assertEqual(approved.status, ClassificationRequestStatus.APPROVED)

    def test_other_resolved_status_is_rejected(self) -> None:
        decision = create_classification_decision(
            decision_id="declined-001", request_id=self.request.request_id, request_fingerprint=self.request.fingerprint,
            organization_id=self.request.organization_id, onboarding_run_id=self.request.onboarding_run_id,
            status=ClassificationRequestStatus.DECLINED, decided_evidence_class=None, decided_integrity_treatment=None,
            reviewer_identity="reviewer", reviewer_role="reviewer", authority_claim="authority", rationale="Declined.",
            supersedes_decision_id=None, decided_at=None,
        )
        persist_contract(self.root, decision)
        with self.assertRaisesRegex(ValueError, "already resolved"):
            self.accept()

    def test_workspace_run_retained_manifest_and_preview_mismatches_are_rejected(self) -> None:
        foreign_request = create_classification_request(
            request_id="foreign-request", organization_id="other-org", onboarding_run_id=self.request.onboarding_run_id,
            source_manifest_fingerprint=self.request.source_manifest_fingerprint, target=self.request.target,
            scope=self.request.scope, proposed_evidence_class=self.request.proposed_evidence_class,
            proposed_integrity_treatment=self.request.proposed_integrity_treatment, requester_identity="requester",
            requester_role="operator", authority_claim="authority", rationale="Review.", created_at=None,
        )
        persist_contract(self.root, foreign_request)
        with self.assertRaisesRegex(ValueError, "organization"):
            self.accept(request=foreign_request)
        wrong_run = replace(self.request, onboarding_run_id="other-run")
        with self.assertRaisesRegex(ValueError, "onboarding run"):
            self.accept(request=wrong_run)
        stale_request = replace(self.request, source_manifest_fingerprint="c" * 64)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.accept(request=stale_request)
        with self.assertRaisesRegex(ValueError, "actual retained manifest"):
            self.accept(manifest=dict(self.manifest, changed=True))
        wrong_source_preview = replace(self.preview, manifest_fingerprint="d" * 64)
        with self.assertRaisesRegex(ValueError, "approved source"):
            self.accept(preview=wrong_source_preview)
        wrong_scope_preview = replace(self.preview, target="src/other.py")
        with self.assertRaisesRegex(ValueError, "request and preview"):
            self.accept(preview=wrong_scope_preview)
        stale_preview = replace(self.preview, matched_set_fingerprint="e" * 64)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.accept(preview=stale_preview)

    def test_authority_claim_is_required_and_immutable_append_only_persistence_rejects_conflict(self) -> None:
        with self.assertRaisesRegex(ValueError, "identity, role, and authority"):
            self.accept(authority_claim="")
        decision, record = self.accept()
        decision_path = self.run_root / "classifications" / "decisions" / f"{decision.decision_id}.json"
        record_path = self.run_root / "classifications" / "records" / f"{record.classification_id}.json"
        before = (decision_path.read_bytes(), record_path.read_bytes())
        with self.assertRaisesRegex(ValueError, "already resolved"):
            self.accept()
        self.assertEqual(before, (decision_path.read_bytes(), record_path.read_bytes()))
        conflicting = replace(decision, rationale="conflicting immutable content")
        with self.assertRaisesRegex(ValueError, "immutable"):
            persist_contract(self.root, conflicting)
        conflicting_record = replace(record, supersedes_classification_id="other-record")
        with self.assertRaisesRegex(ValueError, "immutable"):
            persist_contract(self.root, conflicting_record)

    def test_service_does_not_reconstruct_policy_reevaluate_readiness_or_mutate_lifecycle(self) -> None:
        state_before = (self.run_root / "state.json").read_bytes()
        with patch("rip.onboarding.policy_history.reconstruct_policy_history", side_effect=AssertionError("policy reconstruction")), patch(
            "rip.onboarding.classification_lifecycle.evaluate_classification_readiness", side_effect=AssertionError("readiness")
        ), patch("rip.onboarding.classification_lifecycle.resume_after_classification", side_effect=AssertionError("resume")):
            self.accept()
        self.assertEqual(state_before, (self.run_root / "state.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
