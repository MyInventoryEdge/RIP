from __future__ import annotations
import unittest
from rip.desktop_pages.primary_action import resolve_primary_action
from rip.desktop_pages.work_queue import WorkItem

def item(classification="Critical", run_id="run", action="OPEN WORKSPACE"):
    return WorkItem(classification, "repo", run_id, "state", "reason", "summary", action)

class PrimaryActionTests(unittest.TestCase):
    def test_one_recommendation_becomes_one_primary_action(self):
        result=resolve_primary_action((item(),))
        self.assertEqual("OPEN WORKSPACE", result.button_label); self.assertFalse(result.has_more_work)

    def test_no_recommendation_has_no_button(self):
        result=resolve_primary_action((item("Healthy"),))
        self.assertIsNone(result.button_label); self.assertIn("Nothing requires", result.summary)

    def test_multiple_recommendations_keep_one_primary_action(self):
        result=resolve_primary_action((item("Needs Attention", "later"), item("Critical", "first")))
        self.assertEqual("first", result.work_item.run_id); self.assertTrue(result.has_more_work)

    def test_sda_bootstrap_action_is_obvious(self):
        result=resolve_primary_action((item("Critical", "sda-first-decision", "REVIEW CONSTITUTIONAL DECISION"),))
        self.assertEqual("3 minutes", result.estimated_time); self.assertEqual("REVIEW CONSTITUTIONAL DECISION", result.button_label)

if __name__ == "__main__": unittest.main()
