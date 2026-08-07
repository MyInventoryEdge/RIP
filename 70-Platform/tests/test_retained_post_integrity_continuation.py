from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rip.onboarding.models import ObservationMode, OrganizationContext, ReasoningCapability
from rip.onboarding.service import continue_retained_post_integrity_run


class RetainedPostIntegrityContinuationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name); self.run = root / "onboarding-runs" / "run-001"; self.run.mkdir(parents=True); (root / "audit").mkdir()
        (self.run / "state.json").write_text('{"state":"created"}', encoding="utf-8")
        self.difference = {"difference_fingerprint":"difference-1", "modified_content_paths":["state.json"], "added_paths":[], "removed_paths":[], "kind_changed_paths":[], "access_state_changed_paths":[]}
        (self.run / "integrity-difference.json").write_text(json.dumps(self.difference), encoding="utf-8")
        self.context = OrganizationContext("org", "run-001", str(root / "source"), str(root), ObservationMode.READ_ONLY, ReasoningCapability("test", "Test", "test", True, True, True, "test"))

    def tearDown(self) -> None: self.temp.cleanup()

    def test_crash_after_reasoning_retries_from_retained_checkpoint_without_rewriting_it(self) -> None:
        with patch("rip.onboarding.service.execute_trust_action", side_effect=RuntimeError("crash")):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                continue_retained_post_integrity_run(self.context, journal_context={})
        policy, reasoning = (self.run / "mutation-policy.json").read_bytes(), (self.run / "mutation-reasoning.json").read_bytes()
        with patch("rip.onboarding.service.execute_trust_action") as execute:
            continue_retained_post_integrity_run(self.context, journal_context={})
        self.assertEqual(policy, (self.run / "mutation-policy.json").read_bytes())
        self.assertEqual(reasoning, (self.run / "mutation-reasoning.json").read_bytes())
        execute.assert_called_once()


if __name__ == "__main__": unittest.main()
