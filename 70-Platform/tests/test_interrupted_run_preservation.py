from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rip.onboarding import (
    create_organization_workspace, observe_organization, preserve_interrupted_run,
    recommend_reasoning_capability, reopen_preserved_interrupted_run,
    restart_onboarding_run,
)
from tests.trust_test_context import trust_context


class InterruptedRunPreservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.source = base / "customer"; self.source.mkdir()
        (self.source / "state.json").write_text('{"state":"before"}', encoding="utf-8")
        self.workspace = create_organization_workspace(base / "workspaces", organization_id="acme-org", display_name="Acme", repository_path=self.source)
        capability = recommend_reasoning_capability(environment={"OPENAI_API_KEY": "test"})
        self.context = restart_onboarding_run(self.workspace, repository_path=self.source, reasoning_capability=capability, environment={"OPENAI_API_KEY": "test"})
        self.run = Path(self.workspace.workspace_path) / "onboarding-runs" / self.context.onboarding_run_id
        # Cause the normal final verification to produce a retained exact difference.
        original = __import__("rip.onboarding.service", fromlist=["_source_manifest"])._source_manifest
        calls = 0
        def changing_manifest(path, **kwargs):
            nonlocal calls
            calls += 1
            result = original(path, **kwargs)
            if calls == 1:
                (self.source / "state.json").write_text('{"state":"after"}', encoding="utf-8")
            return result
        with patch("rip.onboarding.service._source_manifest", side_effect=changing_manifest):
            with self.assertRaises(RuntimeError): observe_organization(self.context, journal_context=trust_context(base))

    def tearDown(self) -> None: self.temp.cleanup()

    def test_preservation_and_reopen_never_traverse_or_copy_customer_source(self) -> None:
        immutable = {name: (self.run / name).read_bytes() for name in ("initial-source-manifest.json", "final-source-manifest.json", "integrity-difference.json", "stages.json")}
        with patch("rip.onboarding.recovery._source_manifest", side_effect=AssertionError("preservation must not traverse source")), patch("rip.onboarding.recovery.shutil.copytree", side_effect=AssertionError("preservation must not copy source")):
            receipt = preserve_interrupted_run(workspace_root=self.workspace.workspace_path, organization_id="acme-org", interrupted_run_id=self.context.onboarding_run_id)
            reopened = reopen_preserved_interrupted_run(workspace_root=self.workspace.workspace_path, organization_id="acme-org", interrupted_run_id=self.context.onboarding_run_id)
        self.assertEqual(receipt, reopened)
        self.assertIn("integrity-difference.json", receipt.preserved_artifacts)
        for name, content in immutable.items(): self.assertEqual(content, (self.run / name).read_bytes())
        diff = json.loads((self.run / "integrity-difference.json").read_text(encoding="utf-8"))
        self.assertEqual(("state.json",), tuple(diff["modified_content_paths"]))


if __name__ == "__main__": unittest.main()
