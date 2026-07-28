from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from rip.observation import find_repository_root, observe_filesystem


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "RIP"
        (self.root / ".git").mkdir(parents=True)
        (self.root / "00-Constitution").mkdir()
        (self.root / "70-Platform" / "src").mkdir(parents=True)
        (self.root / "00-Constitution" / "RIP-000-Constitution.md").write_text("# RIP-000 - Constitution\n", encoding="utf-8")
        (self.root / "70-Platform" / "pyproject.toml").write_text("[project]\nname='rip'\n", encoding="utf-8")
        (self.root / "70-Platform" / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
        (self.root / "README.md").write_text("# RIP\n", encoding="utf-8")
        (self.root / "__pycache__").mkdir()
        (self.root / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
        egg_info = self.root / "70-Platform" / "src" / "repository_intelligence_platform.egg-info"
        egg_info.mkdir()
        (egg_info / "PKG-INFO").write_text("generated metadata", encoding="utf-8")
        fixture_dir = self.root / "70-Platform" / "tests" / "fixtures" / "00-Constitution"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "RIP-000-Constitution.md").write_text("# Fixture copy\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_finds_repository_root_from_descendant(self):
        self.assertEqual(self.root.resolve(), find_repository_root(self.root / "70-Platform" / "src"))

    def test_observes_expected_evidence_kinds(self):
        result = observe_filesystem(self.root)
        kinds = {item.relative_path: item.kind for item in result.observations}
        self.assertEqual("repository_root", kinds["."])
        self.assertEqual("constitutional_artifact", kinds["00-Constitution/RIP-000-Constitution.md"])
        self.assertEqual("python_project_manifest", kinds["70-Platform/pyproject.toml"])
        self.assertEqual("python_source_file", kinds["70-Platform/src/main.py"])
        self.assertEqual("markdown_file", kinds["README.md"])

    def test_excludes_cache_directories(self):
        result = observe_filesystem(self.root)
        paths = {item.relative_path for item in result.observations}
        self.assertFalse(any(path.startswith("__pycache__") for path in paths))

    def test_excludes_egg_info_directories(self):
        result = observe_filesystem(self.root)
        paths = {item.relative_path for item in result.observations}
        self.assertFalse(any(".egg-info" in path for path in paths))

    def test_classifies_constitutional_fixture_separately(self):
        result = observe_filesystem(self.root)
        kinds = {item.relative_path: item.kind for item in result.observations}
        fixture_path = "70-Platform/tests/fixtures/00-Constitution/RIP-000-Constitution.md"
        self.assertEqual("test_fixture_artifact", kinds[fixture_path])
        self.assertEqual(1, len(result.by_kind("constitutional_artifact")))
        self.assertEqual(1, len(result.by_kind("test_fixture_artifact")))

    def test_observation_ids_are_stable(self):
        first = observe_filesystem(self.root)
        second = observe_filesystem(self.root)
        first_ids = {(item.kind, item.relative_path): item.observation_id for item in first.observations}
        second_ids = {(item.kind, item.relative_path): item.observation_id for item in second.observations}
        self.assertEqual(first_ids, second_ids)

    def test_json_representation_is_serializable(self):
        result = observe_filesystem(self.root)
        encoded = json.dumps(result.to_dict())
        self.assertIn("constitutional_artifact", encoded)


if __name__ == "__main__":
    unittest.main()
