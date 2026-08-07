from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from rip.observation import observe_filesystem, observe_source_manifest
from rip.onboarding import (
    create_organization_workspace,
    observe_organization,
    recommend_reasoning_capability,
    restart_onboarding_run,
)
from rip.onboarding import service
from rip.onboarding.source_watch import start_source_change_tracker
from tests.trust_test_context import trust_context


class _FakeTracker:
    def __init__(self) -> None:
        self.healthy = True
        self.changed = False
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self.healthy = False


class OnboardingPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repository = self.base / "customer"
        self.repository.mkdir()
        (self.repository / "docs").mkdir()
        (self.repository / "docs" / "README.md").write_text("# Evidence\n", encoding="utf-8")
        (self.repository / "large.bin").write_bytes((b"deterministic-content" * 400_000))
        self.workspace = create_organization_workspace(
            self.base / "workspaces",
            organization_id="acme-org",
            display_name="Acme",
            repository_path=self.repository,
        )
        self.context = restart_onboarding_run(
            self.workspace,
            repository_path=self.repository,
            reasoning_capability=recommend_reasoning_capability(environment={"OPENAI_API_KEY": "test"}),
            environment={"OPENAI_API_KEY": "test"},
        )

    def tearDown(self) -> None:
        key = service._source_tracker_key(self.context)
        tracked = service._SOURCE_TRACKERS.pop(key, None)
        if tracked is not None:
            tracked.tracker.close()
        self.temp.cleanup()

    def test_streaming_parallel_manifest_preserves_sha256_and_is_deterministic(self) -> None:
        progress = []
        first = service._source_manifest(self.repository, progress=lambda count, path: progress.append((count, path)))
        second = service._source_manifest(self.repository)
        large = next(item for item in first["entries"] if item["path"] == "large.bin")
        self.assertEqual(hashlib.sha256((self.repository / "large.bin").read_bytes()).hexdigest(), large["value"])
        self.assertEqual(first, second)
        self.assertEqual(list(range(1, first["entry_count"] + 1)), [count for count, _ in progress])

    def test_manifest_projection_matches_filesystem_observation_semantics(self) -> None:
        (self.repository / ".git").mkdir()
        (self.repository / ".git" / "ignored").write_text("ignored", encoding="utf-8")
        (self.repository / "node_modules").mkdir()
        (self.repository / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
        manifest = service._source_manifest(self.repository)
        walked = observe_filesystem(self.repository)
        projected = observe_source_manifest(self.repository, manifest["entries"])

        def semantic(observations):
            return tuple(
                (item.observation_id, item.kind, item.relative_path, item.evidence, item.metadata)
                for item in observations.observations
            )

        self.assertEqual(semantic(walked), semantic(projected))

    def test_progress_is_coalesced_and_performance_is_persisted(self) -> None:
        for index in range(1_205):
            (self.repository / f"entry-{index:04}.txt").write_text(str(index), encoding="utf-8")
        events = []
        tracker = _FakeTracker()
        with patch("rip.onboarding.service.start_source_change_tracker", return_value=tracker):
            result = observe_organization(self.context, progress_callback=events.append)
        progress = [item for item in result.discovery_feed if item.event_type.endswith("progress")]
        self.assertLess(len(progress), 10)
        self.assertEqual(
            [1, 500, 1_000],
            [item.processed_entries for item in progress if item.event_type == "repository-fingerprint-progress"],
        )
        performance_path = Path(self.workspace.workspace_path) / "onboarding-runs" / self.context.onboarding_run_id / "observation-performance.json"
        performance = json.loads(performance_path.read_text(encoding="utf-8"))
        self.assertEqual("independent-full-content-before-and-after", performance["verification_method"])
        self.assertEqual(4, performance["hash_workers"])
        self.assertEqual(500, performance["progress_interval_entries"])
        self.assertEqual("completed", performance["outcome"])

    def test_clean_tracker_avoids_rehash_and_any_change_falls_back(self) -> None:
        tracker = _FakeTracker()
        with patch("rip.onboarding.service.start_source_change_tracker", return_value=tracker):
            result = observe_organization(self.context)
        with patch("rip.onboarding.service._repository_fingerprint") as full_scan:
            self.assertEqual(result.repository_fingerprint, service.current_repository_fingerprint(self.context))
            full_scan.assert_not_called()

        (self.repository / "changed.txt").write_text("changed", encoding="utf-8")
        with patch("rip.onboarding.service._repository_fingerprint") as full_scan:
            with self.assertRaisesRegex(RuntimeError, "source changed"):
                service.current_repository_fingerprint(self.context)
            full_scan.assert_not_called()
        self.assertFalse(tracker.closed)

    def test_native_tracker_reports_source_change_or_is_explicitly_unavailable(self) -> None:
        tracker = start_source_change_tracker(self.repository)
        if tracker is None:
            self.skipTest("native source change tracking is unavailable; full-scan fallback applies")
        try:
            (self.repository / "native-change.txt").write_text("change", encoding="utf-8")
            deadline = time.monotonic() + 2
            while not tracker.changed and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(tracker.changed)
            self.assertIn("native-change.txt", tracker.changed_paths)
        finally:
            tracker.close()

    def test_independent_second_hash_still_detects_change_during_observation(self) -> None:
        changed = False

        def mutate_after_baseline(event) -> None:
            nonlocal changed
            if event.event_type == "repository-observation-started" and not changed:
                changed = True
                (self.repository / "docs" / "README.md").write_text("# Changed during observation\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "source changed"):
            observe_organization(self.context, progress_callback=mutate_after_baseline, journal_context=trust_context(self.base))
        run = Path(self.workspace.workspace_path) / "onboarding-runs" / self.context.onboarding_run_id
        difference = json.loads((run / "integrity-difference.json").read_text(encoding="utf-8"))
        performance = json.loads((run / "observation-performance.json").read_text(encoding="utf-8"))
        self.assertIn("docs/README.md", difference["modified_content_paths"])
        self.assertEqual("interrupted", performance["outcome"])


if __name__ == "__main__":
    unittest.main()
