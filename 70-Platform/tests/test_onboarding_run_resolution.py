from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rip.onboarding import load_classification_review, resolve_onboarding_run_directory, resolve_organization_workspace


class OnboardingRunResolutionTests(unittest.TestCase):
    def test_parent_and_scoped_workspace_resolve_the_same_organization_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp); workspace = parent / "inventory-edge"; run = workspace / "onboarding-runs" / "run-003"
            run.mkdir(parents=True)
            (workspace / "workspace.json").write_text('{"schema":"rip.organization-workspace.v1","organization_id":"inventory-edge"}', encoding="utf-8")
            self.assertEqual(workspace, resolve_organization_workspace(parent, "inventory-edge"))
            self.assertEqual(workspace, resolve_organization_workspace(workspace, "inventory-edge"))
            self.assertEqual(run, resolve_onboarding_run_directory(parent, "inventory-edge", "run-003"))
            self.assertEqual(run, resolve_onboarding_run_directory(workspace, "inventory-edge", "run-003"))

    def test_missing_or_foreign_run_has_clear_customer_facing_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp); workspace = parent / "inventory-edge"; workspace.mkdir()
            (workspace / "workspace.json").write_text('{"schema":"rip.organization-workspace.v1","organization_id":"inventory-edge"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not found"):
                resolve_onboarding_run_directory(parent, "inventory-edge", "run-003")
            with self.assertRaisesRegex(ValueError, "invalid"):
                resolve_onboarding_run_directory(parent, "inventory-edge", "../run-003")

    def test_interrupted_observation_opens_review_from_parent_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp); workspace = parent / "inventory-edge"; run = workspace / "onboarding-runs" / "run-003"
            (run / "classifications" / "requests").mkdir(parents=True)
            (workspace / "workspace.json").write_text('{"schema":"rip.organization-workspace.v1","organization_id":"inventory-edge"}', encoding="utf-8")
            (run / "context.json").write_text('{"organization_id":"inventory-edge"}', encoding="utf-8")
            (run / "state.json").write_text('{"state":"interrupted"}', encoding="utf-8")
            (run / "final-source-manifest.json").write_text('{"manifest_fingerprint":"retained"}', encoding="utf-8")
            (run / "integrity-difference.json").write_text('{"difference_fingerprint":"changed"}', encoding="utf-8")
            (run / "classifications" / "requests" / "request.json").write_text(json.dumps({"contract": {"request_id":"request-003", "target":"src/app.py", "scope":"exact-path", "proposed_evidence_class":"operational-state", "proposed_integrity_treatment":"blocking", "authority_claim":"owner", "fingerprint":"retained"}}), encoding="utf-8")
            before = {path.name: path.read_bytes() for path in run.iterdir() if path.is_file()}
            review = load_classification_review(parent, "inventory-edge", "run-003")
            self.assertEqual("interrupted", review.state)
            self.assertEqual("inventory-edge", review.organization_id)
            self.assertEqual(before, {path.name: path.read_bytes() for path in run.iterdir() if path.is_file()})


if __name__ == "__main__":
    unittest.main()
