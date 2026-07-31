from __future__ import annotations

import unittest
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from rip.discovery import CompatibilityStatus, discover_artifacts
from rip.foundation import load_foundation
from rip.observation import observe_filesystem
from rip.observation.models import Observation, ObservationSet


def observation(path: str, kind: str = "file", suffix: str = ".json") -> Observation:
    return Observation(
        observation_id="obs-" + path.replace("/", "-").replace(".", "_").lower(),
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), source="test", subject=Path(path).name,
        kind=kind, path=Path("C:/repository") / path, relative_path=path,
        metadata={"size_bytes": 10, "suffix": suffix},
    )


def foundation(*items: tuple[str, str, str]):
    return SimpleNamespace(artifacts=tuple(SimpleNamespace(artifact_id=identifier, title=title, path=Path("C:/repository/00-Constitution") / filename) for identifier, title, filename in items))


class ArtifactDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.foundation = foundation(("RIP-000", "Constitution", "RIP-000-Constitution.md"))
        self.observations = ObservationSet(
            Path("C:/repository"), datetime(2026, 1, 1, tzinfo=timezone.utc),
            (
                observation("00-Constitution/RIP-000-Constitution.md", "constitutional_artifact", ".md"),
                observation("60-Reference/Knowledge/archive/canonical-session.json"),
                observation("60-Reference/Knowledge/archive/parser-manifest.json"),
                observation("70-Platform/src/rip/reasoning/primary_evidence.py", "python_source_file", ".py"),
                observation("70-Platform/src/rip/voice/manager.py", "python_source_file", ".py"),
                observation("70-Platform/tests/test_discovery.py", "python_source_file", ".py"),
                observation("70-Platform/.rip-state/state.json"),
                observation("scratch/review.tmp", "file", ".tmp"),
                observation("assets/logo.png", "file", ".png"),
                observation("60-Reference/Knowledge/out/candidate-review.md", "markdown_file", ".md"),
            ),
        )

    def test_repeated_ranking_and_fingerprint_are_identical(self) -> None:
        first = discover_artifacts("primary evidence", self.observations, self.foundation, candidate_limit=3)
        second = discover_artifacts("primary evidence", self.observations, self.foundation, candidate_limit=3)
        self.assertEqual(first, second)
        self.assertEqual(first.report.to_json(), second.report.to_json())
        self.assertEqual(first.report.discovery_fingerprint, second.report.discovery_fingerprint)

    def test_phrase_filename_path_and_alias_matches_preserve_reason_vectors(self) -> None:
        result = discover_artifacts('"primary evidence" voice parser', self.observations, self.foundation, candidate_limit=5)
        ranked = {entry.candidate.repository_relative_path: entry for entry in result.report.rankings}
        primary = ranked["70-Platform/src/rip/reasoning/primary_evidence.py"]
        self.assertGreater(primary.score, 0)
        self.assertTrue(any(reason.signal == "filename-phrase" for reason in primary.reason_vector))
        voice = ranked["70-Platform/src/rip/voice/manager.py"]
        self.assertTrue(any(reason.signal == "alias" and "voice" in reason.matched_values for reason in voice.reason_vector))
        parser = ranked["60-Reference/Knowledge/archive/parser-manifest.json"]
        self.assertTrue(any(reason.signal == "filename" and "parser" in reason.matched_values for reason in parser.reason_vector))

    def test_ties_are_broken_by_path_and_zero_scores_are_retained(self) -> None:
        result = discover_artifacts("unmatched", self.observations, self.foundation, candidate_limit=2)
        paths = [entry.candidate.repository_relative_path for entry in result.report.rankings]
        self.assertEqual(paths, sorted(paths, key=str.casefold))
        self.assertTrue(all(entry.score == 0 for entry in result.report.rankings))
        self.assertEqual(result.selected_candidates, ())

    def test_eligibility_excludes_foundation_runtime_test_generated_and_binary_artifacts(self) -> None:
        result = discover_artifacts("anything", self.observations, self.foundation, candidate_limit=3)
        excluded = {item.candidate.repository_relative_path: item.reason for item in result.report.excluded_artifacts}
        self.assertEqual(excluded["00-Constitution/RIP-000-Constitution.md"], "already-supplied-by-foundation")
        self.assertEqual(excluded["70-Platform/tests/test_discovery.py"], "test-artifact")
        self.assertEqual(excluded["70-Platform/.rip-state/state.json"], "runtime-state")
        self.assertEqual(excluded["scratch/review.tmp"], "temporary-artifact")
        self.assertEqual(excluded["assets/logo.png"], "binary-or-unsupported-extension")
        self.assertEqual(excluded["60-Reference/Knowledge/out/candidate-review.md"], "generated-artifact")

    def test_compatibility_states_and_diagnostics_are_explicit(self) -> None:
        result = discover_artifacts("session", self.observations, self.foundation, candidate_limit=4)
        candidates = {item.repository_relative_path: item for item in result.report.considered_artifacts}
        self.assertEqual(candidates["60-Reference/Knowledge/archive/canonical-session.json"].compatibility, CompatibilityStatus.CHUNK_RETRIEVAL_COMPATIBLE)
        self.assertEqual(candidates["70-Platform/src/rip/voice/manager.py"].compatibility, CompatibilityStatus.PRIMARY_LOAD_COMPATIBLE)
        self.assertEqual(result.report.diagnostics.artifacts_observed, 10)
        self.assertEqual(result.report.diagnostics.artifacts_selected, 1)
        self.assertTrue(result.report.diagnostics.searchable_terms_present)

    def test_manual_constraints_are_reported_and_conflicts_are_rejected(self) -> None:
        result = discover_artifacts("voice", self.observations, self.foundation, candidate_limit=1, manual_inclusions=("70-Platform/src/rip/voice/manager.py",), manual_exclusions=("assets/logo.png",))
        self.assertEqual(result.report.manual_inclusions, ("70-Platform/src/rip/voice/manager.py",))
        self.assertEqual(result.report.manual_exclusions, ("assets/logo.png",))
        self.assertEqual(result.selected_candidates[0].repository_relative_path, "70-Platform/src/rip/voice/manager.py")
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            discover_artifacts("voice", self.observations, self.foundation, candidate_limit=1, manual_inclusions=("a.md",), manual_exclusions=("a.md",))

    def test_empty_punctuation_and_invalid_limit_are_deterministic(self) -> None:
        empty = discover_artifacts("!!!", self.observations, self.foundation, candidate_limit=1)
        self.assertFalse(empty.report.diagnostics.searchable_terms_present)
        self.assertTrue(all(entry.score == 0 for entry in empty.report.rankings))
        with self.assertRaisesRegex(ValueError, "candidate limit"):
            discover_artifacts("voice", self.observations, self.foundation, candidate_limit=0)

    def test_selection_uses_positive_scores_and_manual_exclusion_wins(self) -> None:
        automatic = discover_artifacts("parser", self.observations, self.foundation, candidate_limit=1)
        self.assertEqual([item.repository_relative_path for item in automatic.selected_candidates], ["60-Reference/Knowledge/archive/parser-manifest.json"])
        excluded = discover_artifacts("parser", self.observations, self.foundation, candidate_limit=2, manual_exclusions=("60-Reference/Knowledge/archive/parser-manifest.json",))
        self.assertNotIn("60-Reference/Knowledge/archive/parser-manifest.json", [item.repository_relative_path for item in excluded.selected_candidates])
        reasons = {item.candidate.repository_relative_path: item.reason for item in excluded.report.excluded_artifacts}
        self.assertEqual(reasons["60-Reference/Knowledge/archive/parser-manifest.json"], "manual-exclusion")

    def test_duplicate_paths_are_reported_once_and_never_selected_twice(self) -> None:
        duplicate = replace(observation("70-Platform/src/rip/voice/manager.py", "python_source_file", ".py"), observation_id="obs-duplicate")
        observations = replace(self.observations, observations=(*self.observations.observations, duplicate))
        result = discover_artifacts("voice", observations, self.foundation, candidate_limit=3)
        self.assertEqual([item.repository_relative_path for item in result.selected_candidates].count("70-Platform/src/rip/voice/manager.py"), 1)
        self.assertTrue(any(item.reason == "duplicate-underlying-artifact" for item in result.report.excluded_artifacts))

    def test_production_repository_queries_are_repeatable_without_runtime_integration(self) -> None:
        root = Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as temporary:
            loaded = load_foundation(root / "00-Constitution", state_path=Path(temporary) / "constitutional-memory.json")
            observed = observe_filesystem(root)
            for question in (
                "Why was RIP built?", "What governs organizational authority?", "What happened with parser-manifest.json?",
                "How does primary evidence work?", "How is voice integrated?", "What have we decided about JD Power?",
            ):
                with self.subTest(question=question):
                    first = discover_artifacts(question, observed, loaded, candidate_limit=3)
                    second = discover_artifacts(question, observed, loaded, candidate_limit=3)
                    self.assertEqual(first, second)
                    self.assertEqual(first.report.discovery_fingerprint, second.report.discovery_fingerprint)


if __name__ == "__main__":
    unittest.main()
