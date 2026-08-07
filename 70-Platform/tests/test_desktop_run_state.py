from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rip.desktop_pages.history import load_history
from rip.desktop_pages.investigate import append_investigation_note, load_notes, open_evidence, project_timeline, render_evidence, render_decision_summary, render_workspace, review_evidence
from rip.desktop import RipDesktop
from rip.desktop_pages.runs import load_runs, run_display_text


class DesktopRunStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Workspace"
        self.run = self.root / "customer-zero" / "onboarding-runs" / "run-001"
        self.run.mkdir(parents=True)
        (self.run / "context.json").write_text(json.dumps({"organization_id": "customer-zero", "onboarding_run_id": "run-001", "repository_path": r"C:\INVENTORY_EDGE"}), encoding="utf-8")
        (self.run / "state.json").write_text(json.dumps({"state": "paused-affected-scope"}), encoding="utf-8")
        (self.run / "stages.json").write_text(json.dumps([
            {"run_id": "run-001", "stage": "initial-fingerprint", "state": "completed", "operational_timestamp": "2026-08-05T18:11:39+00:00", "processed_entry_count": 107186, "references": ["initial"]},
            {"run_id": "run-001", "stage": "integrity-verification", "state": "completed", "operational_timestamp": "2026-08-05T19:17:18+00:00", "processed_entry_count": 107186, "references": ["final"]},
        ]), encoding="utf-8")
        (self.run / "integrity-difference.json").write_text(json.dumps({"modified_content_paths": ["operations/cloud-worker/state/cloud-worker-status.json"]}), encoding="utf-8")
        (self.run / "mutation-reasoning.json").write_text(json.dumps({"interpretation": {"required_trust_action": "pause-affected-scope"}}), encoding="utf-8")
        (self.run / "trust-action.json").write_text(json.dumps({"action": {"action": "pause-affected-scope"}}), encoding="utf-8")
        (self.run / "trust-decision-envelope.json").write_text(json.dumps({"journal_record_hash": "journal-001", "created_at": "2026-08-05T21:11:07+00:00", "trust_action": "pause-affected-scope"}), encoding="utf-8")
        (self.run / "trust-execution-receipt.json").write_text(json.dumps({"status": "completed", "completed_at": "2026-08-05T21:11:08+00:00"}), encoding="utf-8")
        audit = self.root / "customer-zero" / "audit"
        audit.mkdir()
        (audit / "audit.json").write_text(json.dumps([{"sequence": 1, "operation": "onboarding-run-created", "payload": {"run_id": "run-001"}}]), encoding="utf-8")
        state = self.root
        (state / "transaction-journal.ndjson").write_text(json.dumps({"record_hash": "journal-001", "producer_authority_type": "trust-authority", "producer_authority_id": "trust-v1", "producer_record_type": "trust-decision-envelope", "publication_sequence": 1, "published_at": "2026-08-05T21:11:07.5+00:00"}) + "\n", encoding="utf-8")
        (state / "journal-head-history.ndjson").write_text(json.dumps({"record_hash": "journal-001", "commit_sequence": 1}) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_run_projection_identifies_retained_integrity_difference_without_mutating_evidence(self) -> None:
        before = {path.name: path.read_bytes() for path in self.run.iterdir()}
        with patch("rip.desktop_pages.runs.storage_directory", return_value=self.root):
            runs = load_runs()
        self.assertEqual(1, len(runs))
        self.assertEqual("Paused — affected scope", runs[0].status)
        self.assertEqual("Last completed stage: Integrity Verification", runs[0].progress)
        self.assertEqual("run-001", runs[0].run_id)
        self.assertIn(r"Source: C:\INVENTORY_EDGE", runs[0].detail)
        self.assertIn("Evidence available", run_display_text(runs[0]))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.run.iterdir()})

    def test_history_selection_data_contains_retained_stage_details_and_run_context(self) -> None:
        with patch("rip.desktop_pages.history.storage_directory", return_value=self.root):
            history = load_history("integrity")
        stage = next(item for item in history if item.title == "Integrity Verification")
        self.assertEqual("run-001", stage.run)
        self.assertIn("Processed entries: 107186", stage.detail)
        self.assertIn("Evidence references: 1", stage.detail)

    def test_evidence_view_presents_retained_run_state_without_replaying_it(self) -> None:
        before = {path.name: path.read_bytes() for path in self.run.iterdir()}
        with patch("rip.desktop_pages.investigate.storage_directory", return_value=self.root):
            view = open_evidence("run-001")
        self.assertEqual("Paused Affected Scope", view.lifecycle_state)
        self.assertEqual("2026-08-05T18:11:39+00:00", view.started)
        self.assertEqual(("Initial Fingerprint", "Integrity Verification"), view.completed_stages)
        rendered = render_evidence(view)
        for expected in ("Run ID: run-001", r"Source: C:\INVENTORY_EDGE", "Lifecycle state: Paused Affected Scope", "Affected path: operations/cloud-worker/state/cloud-worker-status.json", "Mutation action: pause-affected-scope", "Trust action: pause-affected-scope", "Journal publication reference: journal-001", "Execution result: completed", "Final state: Paused Affected Scope"):
            self.assertIn(expected, rendered)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.run.iterdir()})

    def test_open_run_navigates_in_window_and_loads_selected_context(self) -> None:
        with patch("rip.desktop_pages.runs.storage_directory", return_value=self.root):
            run = load_runs()[0]
        shell = object.__new__(RipDesktop)
        shell._runs_list = Mock(curselection=Mock(return_value=(0,)))
        shell._runs = (run,)
        shell._runs_detail = Mock()
        shell._evidence_context = Mock()
        shell._show_page = Mock()
        shell._open_evidence = Mock()
        shell._open_run()
        shell._evidence_context.set.assert_called_once_with("customer-zero / run-001")
        shell._show_page.assert_called_once_with("Investigate")
        shell._open_evidence.assert_called_once()

    def test_open_evidence_returns_visible_reason_instead_of_silent_failure(self) -> None:
        self.assertEqual("Evidence unavailable: A run context is required to open evidence.", RipDesktop._evidence_result(""))

    def test_decision_summary_and_each_retained_evidence_action_are_operator_visible(self) -> None:
        with patch("rip.desktop_pages.investigate.storage_directory", return_value=self.root):
            view = open_evidence("run-001")
            summary = render_decision_summary(view)
            difference = review_evidence("run-001", "difference")
            reasoning = review_evidence("run-001", "reasoning")
            trust = review_evidence("run-001", "trust")
            journal = review_evidence("run-001", "journal")
        for expected in ("Paused — affected scope", "One changed path was retained for review.", "Only the identified scope is paused."):
            self.assertIn(expected, summary)
        self.assertIn("Change type: Modified content", difference)
        self.assertIn("Mutation action: pause-affected-scope", reasoning)
        self.assertIn("Trust action: pause-affected-scope", trust)
        self.assertIn("Producer identity: trust-authority / trust-v1", journal)

    def test_missing_requested_evidence_returns_visible_reason(self) -> None:
        (self.run / "trust-action.json").unlink()
        with patch("rip.desktop_pages.investigate.storage_directory", return_value=self.root):
            result = review_evidence("run-001", "trust")
        self.assertIn("Evidence unavailable: Trust action is not retained.", result)

    def test_completed_paused_continuation_projects_open_decision_in_observe(self) -> None:
        self.assertEqual(
            "Run completed\n\nDecision:\nPaused — affected scope\n\nAffected paths:\n1",
            RipDesktop._resume_completion_text({"run_id": "run-001", "state": "paused-affected-scope", "trust_action": "pause-affected-scope"}),
        )

    def test_workspace_timeline_projects_retained_journey_and_notes_are_append_only(self) -> None:
        before = {path.name: path.read_bytes() for path in self.run.iterdir()}
        with patch("rip.desktop_pages.investigate.storage_directory", return_value=self.root):
            timeline = project_timeline("run-001")
            first = append_investigation_note("run-001", "Runtime state requires review.", author="operator-a")
            second = append_investigation_note("run-001", "Escalated for verification.", author="operator-b")
            notes = load_notes("run-001")
            workspace = render_workspace(open_evidence("run-001"))
        self.assertEqual((first, second), notes)
        self.assertEqual(("Initial Fingerprint", "Integrity Verification", "Trust Decision", "Journal Publication", "Paused — affected scope"), tuple(entry.title for entry in timeline))
        self.assertIn("Investigation Notes", workspace)
        self.assertIn("operator-a: Runtime state requires review.", workspace)
        for expected in ("Guided Resolution", "1. What happened?", "2. Why?", "3. Should I be worried?", "4. My choices", "5. RIP recommends", "6. What happens next?", "Advanced Evidence"):
            self.assertIn(expected, workspace)
        for name, value in before.items():
            self.assertEqual(value, (self.run / name).read_bytes())
        self.assertEqual(2, len((self.run / "investigation-notes.ndjson").read_text(encoding="utf-8").splitlines()))

    def test_windows_path_matching_is_case_insensitive_and_ignores_trailing_separators(self) -> None:
        self.assertEqual(
            RipDesktop._normalized_windows_path(r"C:\Inventory_Edge\\"),
            RipDesktop._normalized_windows_path(r"c:\inventory_edge"),
        )
        self.assertEqual(
            RipDesktop._normalized_windows_path(r"C:\RIP\Workspace\..\..\Inventory_Edge"),
            RipDesktop._normalized_windows_path(r"C:\Inventory_Edge"),
        )


if __name__ == "__main__":
    unittest.main()
