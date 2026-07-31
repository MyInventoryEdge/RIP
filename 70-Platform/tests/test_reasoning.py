from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rip.foundation import load_foundation
from rip.observation import observe_filesystem
from rip.reasoning.models import ReasoningRequest
from rip.reasoning.openai_provider import OpenAIProvider
from rip.reasoning.prompt_builder import SYSTEM_INSTRUCTIONS, build_evidence_package, serialize_evidence_package
from rip.reasoning import service
from rip.reasoning.service import DiscoveryMode, RetrievalDecision, ask_repository

FIXTURE_FOUNDATION = Path(__file__).resolve().parents[2] / "00-Constitution"


class FakeProvider:
    def __init__(self) -> None:
        self.request = None

    def ask(self, request):
        self.request = request
        from rip.reasoning.models import ReasoningResult
        return ReasoningResult(
            answer="Observed repository [obs-0000000000000000].\nBoundary: AI interpretation grounded in supplied evidence; not organizational authority.",
            provider="fake",
            model=request.model,
            cited_observation_ids=("obs-0000000000000000",),
        )


class FakeResponses:
    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp-test",
            output_text="A claim [obs-0123456789abcdef].",
            usage=SimpleNamespace(input_tokens=12, output_tokens=5),
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


class ReasoningTests(unittest.TestCase):
    def _repository(self, root: Path) -> None:
        shutil.copytree(FIXTURE_FOUNDATION, root / "00-Constitution")
        (root / "70-Platform").mkdir()
        (root / "README.md").write_text("# Example", encoding="utf-8")

    def test_evidence_package_contains_foundation_and_observation_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            package = build_evidence_package(load_foundation(root / "00-Constitution"), observe_filesystem(root), "What is this?")
            encoded = serialize_evidence_package(package)
            decoded = json.loads(encoded)
            self.assertEqual(decoded["schema"], "rip.reasoning.evidence.v1")
            self.assertEqual(len(decoded["foundation"]["artifacts"]), 8)
            self.assertEqual([item["artifact_id"] for item in decoded["foundation"]["artifacts"]], [f"RIP-{index:03}" for index in range(8)])
            self.assertTrue(any(item["observation_id"].startswith("obs-") for item in decoded["observation_set"]["observations"]))

    def test_service_builds_request_without_provider_filesystem_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            provider = FakeProvider()
            result = ask_repository("What is this?", root=root, model="test-model", provider=provider)
            self.assertEqual(result.provider, "fake")
            self.assertEqual(provider.request.model, "test-model")
            self.assertIn("rip.reasoning.evidence.v1", provider.request.evidence_json)
            self.assertIn("Do not claim direct filesystem access", SYSTEM_INSTRUCTIONS)

    def test_small_primary_evidence_reaches_provider_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            artifact = root / "evidence.txt"; artifact.write_text("exact primary evidence", encoding="utf-8")
            provider = FakeProvider()
            ask_repository("Read it", root=root, provider=provider, primary_paths=["evidence.txt"])
            package = json.loads(provider.request.evidence_json.split("\n\n", 1)[1])
            self.assertEqual(package["primary_evidence"]["artifacts"][0]["content"], "exact primary evidence")

    def test_automatic_discovery_and_foundation_only_decisions_are_reported_without_provider_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            voice = root / "70-Platform" / "src" / "rip" / "voice" / "manager.py"; voice.parent.mkdir(parents=True); voice.write_text("voice evidence", encoding="utf-8")
            provider = FakeProvider(); decisions = []
            ask_repository("voice", root=root, provider=provider, discovery_callback=decisions.append)
            self.assertEqual(decisions[0].mode, DiscoveryMode.AUTOMATIC)
            self.assertEqual(decisions[0].resolved_paths, ("70-Platform/src/rip/voice/manager.py",))
            package = json.loads(provider.request.evidence_json.split("\n\n", 1)[1])
            self.assertEqual(package["primary_evidence"]["artifacts"][0]["content"], "voice evidence")
            decisions.clear(); ask_repository("unmatched", root=root, provider=FakeProvider(), discovery_callback=decisions.append)
            self.assertTrue(decisions[0].foundation_only)
            self.assertEqual(decisions[0].resolved_paths, ())
            first = decisions[0]
            decisions.clear(); ask_repository("unmatched", root=root, provider=FakeProvider(), discovery_callback=decisions.append)
            self.assertEqual(decisions[0], first)

    def test_constraints_use_only_legacy_and_automatic_retrieval_compose_deterministically(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            artifact = root / "canonical-session.json"; artifact.write_text(self._canonical_session(), encoding="utf-8")
            provider = FakeProvider(); decisions = []
            ask_repository("needle", root=root, provider=provider, discovery_includes=["canonical-session.json"], discovery_callback=decisions.append)
            self.assertEqual(decisions[0].mode, DiscoveryMode.CONSTRAINED)
            package = json.loads(provider.request.evidence_json.split("\n\n", 1)[1])
            self.assertTrue(package["primary_evidence"]["artifacts"][0]["chunked"])
            decisions.clear(); ask_repository("needle", root=root, provider=FakeProvider(), primary_paths=["canonical-session.json"], discovery_callback=decisions.append)
            self.assertEqual(decisions[0].mode, DiscoveryMode.LEGACY)
            decisions.clear(); ask_repository("needle", root=root, provider=FakeProvider(), discovery_includes=["canonical-session.json"], use_only_selected_artifacts=True, discovery_callback=decisions.append)
            self.assertEqual(decisions[0].mode, DiscoveryMode.USE_ONLY)
            with self.assertRaisesRegex(ValueError, "requires at least one"):
                ask_repository("needle", root=root, provider=FakeProvider(), use_only_selected_artifacts=True)
            decisions.clear(); ask_repository("session", root=root, provider=FakeProvider(), discovery_excludes=["canonical-session.json"], discovery_callback=decisions.append)
            self.assertTrue(decisions[0].foundation_only)

    @staticmethod
    def _canonical_session(message_count: int = 100, markdown: str = "needle") -> str:
        messages = [
            {"source_message_id": f"message-{index}", "source_order": index, "participant_id": "role:user", "role": "user", "markdown": markdown + " " + ("x" * 23_900)}
            for index in range(message_count)
        ]
        return json.dumps({"session_id": "session", "source_format": "test", "messages": messages, "validation": {"passed": True}}, ensure_ascii=False)

    def test_oversized_canonical_session_automatically_retrieves_selected_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            artifact = root / "large.json"
            artifact.write_text(self._canonical_session(), encoding="utf-8")
            provider = FakeProvider()
            ask_repository("needle", root=root, provider=provider, primary_paths=["large.json"])
            package = json.loads(provider.request.evidence_json.split("\n\n", 1)[1])
            selected = package["primary_evidence"]["artifacts"][0]
            self.assertTrue(selected["chunked"])
            self.assertIn("needle", selected["content"])
            self.assertLess(len(selected["content"]), artifact.stat().st_size)
            self.assertNotIn("retrieval_fingerprint", package)

    def test_oversized_unsupported_artifact_fails_before_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            (root / "large.txt").write_text("x" * 2_500_000, encoding="utf-8")
            provider = FakeProvider()
            with self.assertRaisesRegex(ValueError, "No compatible governed chunker"):
                ask_repository("Read it", root=root, provider=provider, primary_paths=["large.txt"])
            self.assertIsNone(provider.request)

    def test_retrieval_decision_budget_partial_coverage_and_determinism(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            (root / "large.json").write_text(self._canonical_session(), encoding="utf-8")
            foundation = load_foundation(root / "00-Constitution")
            observations = observe_filesystem(root)
            primary = service.load_primary_evidence(root, observations, ["large.json"])
            budgets = []
            real_engine = service.DeterministicLexicalRetrievalEngine
            class RecordingEngine:
                def retrieve(self, *args, **kwargs):
                    budgets.append(kwargs["token_budget"])
                    return real_engine().retrieve(*args, **kwargs)
            with patch.object(service, "DeterministicLexicalRetrievalEngine", RecordingEngine):
                first, first_decision = service._prepare_primary_evidence(foundation, observations, "needle", primary)
                second, second_decision = service._prepare_primary_evidence(foundation, observations, "needle", primary)
            self.assertIsInstance(first_decision, RetrievalDecision)
            self.assertTrue(first_decision.oversized_request_detected)
            self.assertTrue(first_decision.retrieval_performed)
            self.assertFalse(first_decision.retrieval_failed)
            self.assertGreater(first_decision.selected_chunk_count, 0)
            self.assertEqual(first_decision.coverage_status.value, "partial")
            self.assertEqual(first_decision.retrieval_fingerprint, second_decision.retrieval_fingerprint)
            self.assertEqual(first, second)
            self.assertEqual(len(budgets), 2)
            self.assertGreater(budgets[0], 0)
            self.assertEqual(budgets[0], budgets[1])

    def test_retrieval_decision_reports_complete_coverage_when_all_chunks_fit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            (root / "session.json").write_text(self._canonical_session(message_count=3), encoding="utf-8")
            foundation = load_foundation(root / "00-Constitution")
            observations = observe_filesystem(root)
            primary = service.load_primary_evidence(root, observations, ["session.json"])
            complete = service._build_request("needle", None, build_evidence_package(foundation, observations, "needle", primary))
            with patch.object(service, "SAFE_INPUT_TOKEN_BUDGET", int(service._estimated_tokens(complete)) - 1):
                _prepared, decision = service._prepare_primary_evidence(foundation, observations, "needle", primary)
            self.assertEqual(decision.coverage_status.value, "complete")

    def test_zero_result_does_not_call_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            (root / "large.json").write_text(self._canonical_session(markdown="unrelated"), encoding="utf-8")
            provider = FakeProvider()
            with self.assertRaisesRegex(ValueError, "selected no evidence"):
                ask_repository("needle", root=root, provider=provider, primary_paths=["large.json"])
            self.assertIsNone(provider.request)

    def test_openai_provider_uses_responses_api_and_reports_usage(self):
        client = FakeClient()
        provider = OpenAIProvider(client=client)
        request = ReasoningRequest(
            question="Q",
            model="test-model",
            evidence_json='{"observation_id":"obs-0123456789abcdef"}',
            instructions="Instructions",
        )
        result = provider.ask(request)
        self.assertEqual(client.responses.kwargs["model"], "test-model")
        self.assertEqual(result.response_id, "resp-test")
        self.assertEqual(result.input_tokens, 12)
        self.assertEqual(result.cited_observation_ids, ("obs-0123456789abcdef",))
        self.assertEqual(result.unknown_observation_ids, ())

    def test_openai_provider_detects_unknown_citations(self):
        client = FakeClient()
        provider = OpenAIProvider(client=client)
        request = ReasoningRequest("Q", "test", "{}", "Instructions")
        result = provider.ask(request)
        self.assertEqual(result.unknown_observation_ids, ("obs-0123456789abcdef",))


if __name__ == "__main__":
    unittest.main()
