from pathlib import Path
import shutil
import tempfile
import unittest

from rip.foundation import find_foundation_root, load_foundation


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "00-Constitution"


class FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = tempfile.TemporaryDirectory()
        cls.foundation = load_foundation(FIXTURE_ROOT, state_path=Path(cls.state.name) / "memory.json")

    @classmethod
    def tearDownClass(cls):
        cls.state.cleanup()

    def test_loads_the_complete_registered_corpus(self):
        self.assertEqual(8, len(self.foundation.artifacts))
        self.assertEqual("RIP-001", self.foundation.mission.artifact_id)
        self.assertEqual("RIP-006", self.foundation.artifact("RIP-006").artifact_id)
        self.assertEqual("RIP-007", self.foundation.artifact("RIP-007").artifact_id)

    def test_primary_object_is_organization(self):
        self.assertEqual("Organization", self.foundation.primary_object)

    def test_authority_definition_is_available_case_insensitively(self):
        self.assertIn("approved organizational", self.foundation.term("authority"))

    def test_section_lookup_ignores_section_number(self):
        section = self.foundation.constitution.section("Mission Authority")
        self.assertIn("RIP-001", section.body)

    def test_discovers_parent_foundation_directory(self):
        discovered = find_foundation_root(FIXTURE_ROOT.parent / "child" / "deeper")
        self.assertEqual(FIXTURE_ROOT.resolve(), discovered)

    def test_boot_persists_reuses_refreshes_and_recovers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "00-Constitution"
            shutil.copytree(FIXTURE_ROOT, root)
            state = Path(temp) / "memory.json"
            first = load_foundation(root, state_path=state)
            self.assertEqual("rebuilt", first.source)
            second = load_foundation(root, state_path=state)
            self.assertEqual("persisted", second.source)
            lexicon = root / "RIP-002-Lexicon.md"
            lexicon.write_text(lexicon.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            refreshed = load_foundation(root, state_path=state)
            self.assertEqual("refreshed", refreshed.source)
            state.write_text("not json", encoding="utf-8")
            recovered = load_foundation(root, state_path=state)
            self.assertEqual("recovered", recovered.source)


if __name__ == "__main__":
    unittest.main()
