from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rip.onboarding import create_organization_workspace, create_verified_recovery_snapshot, load_verified_recovery_snapshot, recommend_reasoning_capability, restart_onboarding_run
from rip.onboarding import recovery


class RecoverySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(); base = Path(self.temp.name)
        self.source = base / "customer"; self.source.mkdir(); (self.source / "state.txt").write_text("before", encoding="utf-8")
        self.workspace = create_organization_workspace(base / "workspaces", organization_id="acme-org", display_name="Acme", repository_path=self.source)
        capability = recommend_reasoning_capability(environment={"OPENAI_API_KEY": "test"})
        self.context = restart_onboarding_run(self.workspace, repository_path=self.source, reasoning_capability=capability, environment={"OPENAI_API_KEY": "test"})
        self.run = Path(self.workspace.workspace_path) / "onboarding-runs" / self.context.onboarding_run_id
        (self.run / "state.json").write_text('{"schema":"rip.organization-onboarding.v1","state":"interrupted"}', encoding="utf-8")

    def tearDown(self) -> None: self.temp.cleanup()

    def test_verified_snapshot_is_linked_to_interrupted_run_and_source_remains_unchanged(self) -> None:
        context_before = (self.run / "context.json").read_bytes(); source_before = (self.source / "state.txt").read_bytes()
        progress = []
        snapshot = create_verified_recovery_snapshot(
            workspace_root=Path(self.workspace.workspace_path).parent,
            organization_id="acme-org",
            interrupted_run_id=self.context.onboarding_run_id,
            progress_callback=progress.append,
        )
        self.assertTrue(snapshot.verified_stable)
        self.assertEqual(source_before, (self.source / "state.txt").read_bytes())
        self.assertEqual(context_before, (self.run / "context.json").read_bytes())
        self.assertEqual(source_before, (Path(snapshot.snapshot_path) / "state.txt").read_bytes())
        self.assertEqual(snapshot, load_verified_recovery_snapshot(workspace_root=self.workspace.workspace_path, organization_id="acme-org", snapshot_id=snapshot.snapshot_id))
        self.assertEqual("Measuring the current customer source before copying", progress[0].phase)
        self.assertIn("Copying the verified recovery snapshot", {item.phase for item in progress})
        self.assertIn("Rechecking the current customer source for changes", {item.phase for item in progress})
        self.assertIn("Verifying the copied recovery snapshot", {item.phase for item in progress})
        self.assertEqual("Recovery snapshot verified", progress[-1].phase)
        self.assertTrue(any(item.processed_items is not None for item in progress))

    def test_changed_during_capture_is_not_usable(self) -> None:
        original = recovery.shutil.copytree
        def changing_copy(source, destination, **kwargs):
            result = original(source, destination, **kwargs)
            (self.source / "state.txt").write_text("changed", encoding="utf-8")
            return result
        with patch("rip.onboarding.recovery.shutil.copytree", side_effect=changing_copy):
            with self.assertRaisesRegex(ValueError, "changed while"):
                create_verified_recovery_snapshot(workspace_root=self.workspace.workspace_path, organization_id="acme-org", interrupted_run_id=self.context.onboarding_run_id)
        receipts = list((Path(self.workspace.workspace_path).parent / "recovery-snapshots" / "acme-org").glob("*/snapshot.json"))
        self.assertEqual(1, len(receipts))
        self.assertFalse(json.loads(receipts[0].read_text(encoding="utf-8"))["snapshot"]["verified_stable"])

    def test_only_interrupted_runs_are_eligible(self) -> None:
        (self.run / "state.json").write_text('{"schema":"rip.organization-onboarding.v1","state":"observed"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "interrupted"):
            create_verified_recovery_snapshot(workspace_root=self.workspace.workspace_path, organization_id="acme-org", interrupted_run_id=self.context.onboarding_run_id)

    def test_copied_snapshot_must_match_verified_source(self) -> None:
        original = recovery.shutil.copytree

        def corrupting_copy(source, destination, **kwargs):
            result = original(source, destination, **kwargs)
            (Path(destination) / "state.txt").write_text("corrupted copy", encoding="utf-8")
            return result

        with patch("rip.onboarding.recovery.shutil.copytree", side_effect=corrupting_copy):
            with self.assertRaisesRegex(ValueError, "does not match"):
                create_verified_recovery_snapshot(
                    workspace_root=self.workspace.workspace_path,
                    organization_id="acme-org",
                    interrupted_run_id=self.context.onboarding_run_id,
                )


if __name__ == "__main__": unittest.main()
