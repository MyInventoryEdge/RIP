from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rip.desktop import RipDesktop
from rip.desktop_pages.work_queue import WorkItem, load_work_queue, resolve_work


class WorkQueueTests(unittest.TestCase):
    def test_resolver_returns_exactly_one_supported_classification(self) -> None:
        cases = (
            (dict(lifecycle_state="", trust_action=None, execution_status=None, provisioning_ready=True, evidence_available=False), "Critical"),
            (dict(lifecycle_state="paused-affected-scope", trust_action="pause-affected-scope", execution_status="completed", provisioning_ready=True, evidence_available=True), "Needs Attention"),
            (dict(lifecycle_state="created", trust_action=None, execution_status=None, provisioning_ready=False, evidence_available=True), "Needs Attention"),
            (dict(lifecycle_state="created", trust_action=None, execution_status=None, provisioning_ready=True, evidence_available=True), "In Progress"),
            (dict(lifecycle_state="observed", trust_action=None, execution_status="completed", provisioning_ready=True, evidence_available=True), "Completed Today"),
            (dict(lifecycle_state="observed", trust_action=None, execution_status=None, provisioning_ready=True, evidence_available=True), "Healthy"),
        )
        for inputs, expected in cases:
            with self.subTest(expected=expected):
                item = resolve_work(**inputs, repository=r"C:\INVENTORY_EDGE", run_id="run-001")
                self.assertEqual(expected, item.classification)

    def test_customer_zero_paused_run_projects_needs_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); run = root / "customer-zero" / "onboarding-runs" / "run-001"; run.mkdir(parents=True)
            (run / "context.json").write_text(json.dumps({"repository_path": r"C:\INVENTORY_EDGE", "onboarding_run_id": "run-001"}), encoding="utf-8")
            (run / "state.json").write_text(json.dumps({"state": "paused-affected-scope"}), encoding="utf-8")
            (run / "trust-action.json").write_text(json.dumps({"action": {"action": "pause-affected-scope"}}), encoding="utf-8")
            (run / "trust-execution-receipt.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            with patch("rip.desktop_pages.work_queue.storage_directory", return_value=root):
                items = load_work_queue(provisioning_ready=True)
        self.assertEqual(1, len(items)); item = items[0]
        self.assertEqual("Needs Attention", item.classification)
        self.assertEqual("Paused — affected scope", item.constitutional_state)
        self.assertEqual("Review retained runtime mutation.", item.recommendation)
        self.assertEqual("Open Workspace", item.primary_action)

    def test_open_workspace_card_navigates_directly_to_in_window_investigate(self) -> None:
        shell = object.__new__(RipDesktop)
        shell._evidence_context = Mock(); shell._show_page = Mock()
        item = WorkItem("Needs Attention", r"C:\INVENTORY_EDGE", "run-001", "Paused — affected scope", "Paused.", "Review retained runtime mutation.", "Open Workspace", "customer-zero / run-001")
        shell._open_work_item(item)
        shell._evidence_context.set.assert_called_once_with("customer-zero / run-001")
        shell._show_page.assert_called_once_with("Investigate")


if __name__ == "__main__":
    unittest.main()
