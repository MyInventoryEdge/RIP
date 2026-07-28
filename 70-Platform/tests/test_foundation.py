from pathlib import Path
import unittest

from rip.foundation import find_foundation_root, load_foundation


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "00-Constitution"


class FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.foundation = load_foundation(FIXTURE_ROOT)

    def test_loads_all_five_artifacts(self):
        self.assertEqual(5, len(self.foundation.artifacts))

    def test_primary_object_is_organization(self):
        self.assertEqual("Organization", self.foundation.primary_object)

    def test_authority_definition_is_available_case_insensitively(self):
        self.assertIn("approved organizational", self.foundation.term("authority"))

    def test_section_lookup_ignores_section_number(self):
        section = self.foundation.constitution.section("Mission")
        self.assertIn("RIP SHALL preserve", section.body)

    def test_discovers_parent_foundation_directory(self):
        discovered = find_foundation_root(FIXTURE_ROOT.parent / "child" / "deeper")
        self.assertEqual(FIXTURE_ROOT.resolve(), discovered)


if __name__ == "__main__":
    unittest.main()
