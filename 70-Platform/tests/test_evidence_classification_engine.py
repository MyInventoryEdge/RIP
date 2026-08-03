from __future__ import annotations

import unittest

from rip.onboarding import (
    ClassificationScope,
    EvidenceClass,
    IntegrityTreatment,
    create_classification_policy,
    create_evidence_classification,
    evaluate_classification_policy,
)


class EvidenceClassificationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = {
            "manifest_fingerprint": "a" * 64,
            "entries": [
                {"path": "docs/charter.md", "kind": "file", "value": "1" * 64, "size": 10},
                {"path": "generated/build.json", "kind": "file", "value": "2" * 64, "size": 20},
                {"path": "operations/cloud-worker/state/status.json", "kind": "file", "value": "3" * 64, "size": 30},
                {"path": "src", "kind": "directory", "value": None, "size": None},
            ],
        }

    def _record(self, identifier: str, target: str, scope: ClassificationScope, evidence_class: EvidenceClass, treatment: IntegrityTreatment):
        return create_evidence_classification(
            classification_id=identifier, organization_id="inventory-edge", onboarding_run_id="run-001",
            target=target, scope=scope, evidence_class=evidence_class, integrity_treatment=treatment,
            source_manifest_fingerprint="a" * 64, decision_id=f"decision-{identifier}",
            decision_fingerprint="b" * 64, supersedes_classification_id=None,
        )

    def _policy(self, *records):
        return create_classification_policy(
            policy_id="policy-001", organization_id="inventory-edge", onboarding_run_id="run-001",
            source_manifest_fingerprint="a" * 64, classifications=records,
        )

    def test_evaluation_is_repeatable_and_complete_fingerprint_preserves_every_entry(self) -> None:
        policy = self._policy(self._record("op-001", "operations/cloud-worker/state/status.json", ClassificationScope.EXACT_PATH, EvidenceClass.OPERATIONAL_STATE, IntegrityTreatment.BLOCKING))
        first = evaluate_classification_policy(self.manifest, policy)
        second = evaluate_classification_policy(self.manifest, policy)
        self.assertEqual(first, second)
        self.assertEqual(4, first.summary.total_entries)
        self.assertEqual(3, first.summary.unknown_entries)
        self.assertEqual(1, first.summary.operational_state_entries)
        self.assertNotEqual(first.complete_source_fingerprint, first.organizational_evidence_fingerprint)
        changed = dict(self.manifest, entries=[*self.manifest["entries"][:-1], {"path": "src", "kind": "directory", "value": "changed", "size": None}])
        self.assertNotEqual(first.complete_source_fingerprint, evaluate_classification_policy(changed, policy).complete_source_fingerprint)

    def test_exact_path_overrides_broader_pattern_and_patterns_are_segment_safe(self) -> None:
        broad = self._record("broad-001", "operations/**", ClassificationScope.PATH_GLOB, EvidenceClass.GENERATED_ARTIFACT, IntegrityTreatment.NON_BLOCKING_REPORTED)
        exact = self._record("exact-001", "operations/cloud-worker/state/status.json", ClassificationScope.EXACT_PATH, EvidenceClass.ORGANIZATIONAL_EVIDENCE, IntegrityTreatment.BLOCKING)
        evaluation = evaluate_classification_policy(self.manifest, self._policy(broad, exact))
        status = next(item for item in evaluation.entries if item.path.endswith("status.json"))
        self.assertEqual("exact-001", status.classification_id)
        self.assertEqual(EvidenceClass.ORGANIZATIONAL_EVIDENCE, status.evidence_class)
        self.assertFalse(any(item.path == "docs/charter.md" and item.classification_id for item in evaluation.entries))

    def test_equivalent_conflicts_fall_back_to_conservative_unknown(self) -> None:
        first = self._record("conflict-a", "generated/*.json", ClassificationScope.PATH_GLOB, EvidenceClass.GENERATED_ARTIFACT, IntegrityTreatment.NON_BLOCKING_REPORTED)
        second = self._record("conflict-b", "generated/*.json", ClassificationScope.PATH_GLOB, EvidenceClass.INVENTORY_ONLY, IntegrityTreatment.BLOCKING)
        evaluation = evaluate_classification_policy(self.manifest, self._policy(first, second))
        generated = next(item for item in evaluation.entries if item.path == "generated/build.json")
        self.assertEqual(EvidenceClass.UNKNOWN, generated.evidence_class)
        self.assertEqual(IntegrityTreatment.BLOCKING, generated.integrity_treatment)
        self.assertEqual(("conflict-a", "conflict-b"), generated.conflict_ids)
        self.assertEqual(1, evaluation.summary.conflicted_entries)

    def test_generated_treatment_changes_organizational_not_complete_fingerprint(self) -> None:
        blocking = self._policy(self._record("generated-block", "generated/build.json", ClassificationScope.EXACT_PATH, EvidenceClass.GENERATED_ARTIFACT, IntegrityTreatment.BLOCKING))
        reported = self._policy(self._record("generated-report", "generated/build.json", ClassificationScope.EXACT_PATH, EvidenceClass.GENERATED_ARTIFACT, IntegrityTreatment.NON_BLOCKING_REPORTED))
        first = evaluate_classification_policy(self.manifest, blocking)
        second = evaluate_classification_policy(self.manifest, reported)
        self.assertEqual(first.complete_source_fingerprint, second.complete_source_fingerprint)
        self.assertNotEqual(first.organizational_evidence_fingerprint, second.organizational_evidence_fingerprint)
        self.assertEqual(1, second.summary.generated_non_blocking_reported_entries)

    def test_stale_policy_and_invalid_manifest_are_rejected(self) -> None:
        policy = self._policy()
        with self.assertRaisesRegex(ValueError, "stale"):
            evaluate_classification_policy(dict(self.manifest, manifest_fingerprint="c" * 64), policy)
        unordered = dict(self.manifest, entries=list(reversed(self.manifest["entries"])))
        with self.assertRaisesRegex(ValueError, "path sorted"):
            evaluate_classification_policy(unordered, policy)


if __name__ == "__main__":
    unittest.main()
