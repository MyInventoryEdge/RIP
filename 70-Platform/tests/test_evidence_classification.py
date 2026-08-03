from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rip.onboarding import (
    ClassificationRequestStatus,
    ClassificationScope,
    EvidenceClass,
    IntegrityTreatment,
    create_classification_decision,
    create_classification_policy,
    create_classification_request,
    create_evidence_classification,
    load_contract_payload,
    persist_contract,
    serialize_contract,
)


class EvidenceClassificationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.values = {
            "request_id": "request-001",
            "organization_id": "inventory-edge",
            "onboarding_run_id": "run-002",
            "source_manifest_fingerprint": "a" * 64,
            "target": "operations/cloud-worker/state/cloud-worker-status.json",
            "scope": ClassificationScope.EXACT_PATH,
            "proposed_evidence_class": EvidenceClass.OPERATIONAL_STATE,
            "proposed_integrity_treatment": IntegrityTreatment.BLOCKING,
            "requester_identity": "customer-zero",
            "requester_role": "operator",
            "authority_claim": "claimed operational authority",
            "rationale": "The status file records current operational state.",
            "created_at": "2026-08-03T00:00:00Z",
        }

    def test_request_fingerprint_and_serialization_are_deterministic(self) -> None:
        first = create_classification_request(**self.values)
        second = create_classification_request(**self.values)
        self.assertEqual(first, second)
        payload = serialize_contract(first)
        self.assertEqual("rip.evidence-classification.v1", payload["schema"])
        self.assertEqual(first.fingerprint, payload["contract"]["fingerprint"])
        self.assertEqual("exact-path", payload["contract"]["scope"])

    def test_approved_decision_and_append_only_record_preserve_provenance(self) -> None:
        request = create_classification_request(**self.values)
        decision = create_classification_decision(
            decision_id="decision-001", request_id=request.request_id, request_fingerprint=request.fingerprint,
            organization_id=request.organization_id, onboarding_run_id=request.onboarding_run_id,
            status=ClassificationRequestStatus.APPROVED, decided_evidence_class=EvidenceClass.GENERATED_ARTIFACT,
            decided_integrity_treatment=IntegrityTreatment.NON_BLOCKING_REPORTED,
            reviewer_identity="gatekeeper", reviewer_role="reviewer", authority_claim="approved classification authority",
            rationale="Explicit reviewed generated-artifact treatment.", supersedes_decision_id=None,
            decided_at="2026-08-03T01:00:00Z",
        )
        record = create_evidence_classification(
            classification_id="classification-001", organization_id=request.organization_id,
            onboarding_run_id=request.onboarding_run_id, target=request.target, scope=request.scope,
            evidence_class=decision.decided_evidence_class, integrity_treatment=decision.decided_integrity_treatment,
            source_manifest_fingerprint=request.source_manifest_fingerprint, decision_id=decision.decision_id,
            decision_fingerprint=decision.fingerprint, supersedes_classification_id=None,
        )
        self.assertEqual(decision.fingerprint, record.decision_fingerprint)
        self.assertEqual(IntegrityTreatment.NON_BLOCKING_REPORTED, record.integrity_treatment)
        policy = create_classification_policy(
            policy_id="policy-001", organization_id=request.organization_id, onboarding_run_id=request.onboarding_run_id,
            source_manifest_fingerprint=request.source_manifest_fingerprint, classifications=(record,),
        )
        self.assertEqual(record.fingerprint, policy.classifications[0].fingerprint)
        self.assertEqual(policy, create_classification_policy(
            policy_id="policy-001", organization_id=request.organization_id, onboarding_run_id=request.onboarding_run_id,
            source_manifest_fingerprint=request.source_manifest_fingerprint, classifications=(record,),
        ))

    def test_unknown_remains_conservative_and_invalid_targets_are_rejected(self) -> None:
        unknown = dict(self.values, proposed_evidence_class=EvidenceClass.UNKNOWN, proposed_integrity_treatment=IntegrityTreatment.NON_BLOCKING_REPORTED)
        with self.assertRaisesRegex(ValueError, "unknown"):
            create_classification_request(**unknown)
        for target in ("../outside.txt", "C:/outside.txt", "/absolute.txt", "folder\\item.txt", "folder//item.txt"):
            with self.assertRaisesRegex(ValueError, "normalized relative POSIX|empty"):
                create_classification_request(**dict(self.values, target=target))
        with self.assertRaisesRegex(ValueError, "glob"):
            create_classification_request(**dict(self.values, target="operations/*.json"))
        path_glob = create_classification_request(**dict(self.values, scope=ClassificationScope.PATH_GLOB, target="operations/**/state-?.json"))
        self.assertEqual(ClassificationScope.PATH_GLOB, path_glob.scope)
        for target in ("operations/[a-z].json", "operations/**state.json", "operations/plain.json"):
            with self.assertRaisesRegex(ValueError, "support only|complete path segment|require"):
                create_classification_request(**dict(self.values, scope=ClassificationScope.PATH_GLOB, target=target))

    def test_policy_is_scoped_and_contracts_persist_immutably(self) -> None:
        request = create_classification_request(**self.values)
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "inventory-edge"
            stored = persist_contract(workspace, request)
            self.assertEqual(
                workspace / "onboarding-runs" / "run-002" / "classifications" / "requests" / "request-001.json",
                stored,
            )
            self.assertEqual(serialize_contract(request), load_contract_payload(stored))
            self.assertEqual(stored, persist_contract(workspace, request))
            changed = create_classification_request(**dict(self.values, rationale="different rationale"))
            with self.assertRaisesRegex(ValueError, "immutable"):
                persist_contract(workspace, changed)

    def test_policy_rejects_cross_organization_classifications(self) -> None:
        request = create_classification_request(**self.values)
        decision = create_classification_decision(
            decision_id="decision-001", request_id=request.request_id, request_fingerprint=request.fingerprint,
            organization_id=request.organization_id, onboarding_run_id=request.onboarding_run_id,
            status=ClassificationRequestStatus.APPROVED, decided_evidence_class=EvidenceClass.OPERATIONAL_STATE,
            decided_integrity_treatment=IntegrityTreatment.BLOCKING, reviewer_identity="gatekeeper", reviewer_role="reviewer",
            authority_claim="approved classification authority", rationale="Approved.", supersedes_decision_id=None, decided_at=None,
        )
        record = create_evidence_classification(
            classification_id="classification-001", organization_id="other-org", onboarding_run_id=request.onboarding_run_id,
            target=request.target, scope=request.scope, evidence_class=EvidenceClass.OPERATIONAL_STATE,
            integrity_treatment=IntegrityTreatment.BLOCKING, source_manifest_fingerprint=request.source_manifest_fingerprint,
            decision_id=decision.decision_id, decision_fingerprint=decision.fingerprint, supersedes_classification_id=None,
        )
        with self.assertRaisesRegex(ValueError, "organization and run scoped"):
            create_classification_policy(
                policy_id="policy-001", organization_id=request.organization_id, onboarding_run_id=request.onboarding_run_id,
                source_manifest_fingerprint=request.source_manifest_fingerprint, classifications=(record,),
            )


if __name__ == "__main__":
    unittest.main()
