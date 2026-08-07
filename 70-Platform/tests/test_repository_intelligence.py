from __future__ import annotations

import unittest

from rip.desktop_pages.repository_intelligence import answer_question, render_answer
from rip.desktop_pages.repository_memory import RepositoryMemory


class RepositoryIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = RepositoryMemory("customer-zero", r"C:\INVENTORY_EDGE", "first", "latest", 1, ("fp",), ("70-Platform", "operations"), ("Observation", "Governance", "Journal"), ("operations/cloud-worker/state/",), "10", "2", (".py: 4",), "Not yet observed.", "metrics", "pause-affected-scope", ("first — run-001",))

    def test_answers_are_deterministic_and_evidence_backed(self) -> None:
        answer = answer_question(self.memory, "What runtime paths exist?")
        self.assertEqual("High", answer.confidence)
        self.assertIn("operations/cloud-worker/state/", answer.answer)
        self.assertEqual(("integrity-difference.json",), answer.evidence)
        self.assertIn("Confidence\nHigh", render_answer(answer))

    def test_insufficient_or_unrecognized_questions_fail_closed_to_not_observed(self) -> None:
        evolution = answer_question(self.memory, "What changed since the previous observation?")
        self.assertEqual("Not yet observed.", evolution.answer)
        self.assertEqual("Unknown", evolution.confidence)
        unknown = answer_question(self.memory, "Who owns the deployment pipeline?")
        self.assertEqual("Not yet observed.", unknown.answer)
        self.assertEqual("Unknown", unknown.confidence)

    def test_capabilities_and_latest_decision_are_from_memory(self) -> None:
        self.assertIn("Observation", answer_question(self.memory, "What constitutional capabilities exist?").answer)
        self.assertIn("pause-affected-scope", answer_question(self.memory, "What is the latest governed decision?").answer)


if __name__ == "__main__": unittest.main()
