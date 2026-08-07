from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rip.desktop_pages.repository_memory import build_repository_memory, render_repository_memory


class RepositoryMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.run = self.root / "customer-zero" / "onboarding-runs" / "run-001"; self.run.mkdir(parents=True)
        (self.run / "context.json").write_text(json.dumps({"organization_id":"customer-zero", "repository_path":r"C:\INVENTORY_EDGE"}), encoding="utf-8")
        (self.run / "stages.json").write_text(json.dumps([{"stage":"initial-fingerprint","state":"completed","operational_timestamp":"2026-08-05T18:11:39+00:00"}]), encoding="utf-8")
        manifest = {"entry_count":4,"aggregate_fingerprint":"fingerprint-001","counts":{"file":2,"directory":2},"entries":[{"path":"70-Platform/src/rip/desktop.py","kind":"file"},{"path":"operations/cloud-worker/state/status.json","kind":"file"},{"path":"operations/cloud-worker/state","kind":"directory"}]}
        (self.run / "final-source-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.run / "initial-source-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.run / "integrity-difference.json").write_text(json.dumps({"modified_content_paths":["operations/cloud-worker/state/status.json"]}), encoding="utf-8")
        (self.run / "mutation-reasoning.json").write_text("{}", encoding="utf-8")
        (self.run / "trust-decision-envelope.json").write_text(json.dumps({"trust_action":"pause-affected-scope"}), encoding="utf-8")

    def tearDown(self) -> None: self.temp.cleanup()

    def test_projection_is_deterministic_rebuildable_and_traceable(self) -> None:
        with patch("rip.desktop_pages.repository_memory.storage_directory", return_value=self.root):
            first = build_repository_memory(); second = build_repository_memory()
        self.assertEqual(first, second); self.assertEqual(1, len(first))
        memory = first[0]
        self.assertEqual("customer-zero", memory.repository)
        self.assertEqual(r"C:\INVENTORY_EDGE", memory.repository_root)
        self.assertEqual(("fingerprint-001",), memory.fingerprints)
        self.assertEqual(("operations/cloud-worker/state/",), memory.runtime_areas)
        self.assertIn("Observation", memory.capabilities)
        self.assertEqual("pause-affected-scope", memory.latest_decision)

    def test_memory_view_uses_not_yet_observed_for_insufficient_evidence(self) -> None:
        with patch("rip.desktop_pages.repository_memory.storage_directory", return_value=self.root):
            text = render_repository_memory(build_repository_memory()[0])
        self.assertIn("Not yet observed.", text)
        self.assertIn("Repository Timeline", text)
        self.assertIn("2026-08-05T18:11:39+00:00 — run-001", text)


if __name__ == "__main__": unittest.main()
