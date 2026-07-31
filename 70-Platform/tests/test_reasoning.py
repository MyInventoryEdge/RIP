from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from rip.foundation import load_foundation
from rip.observation import observe_filesystem
from rip.reasoning.models import ReasoningRequest
from rip.reasoning.openai_provider import OpenAIProvider
from rip.reasoning.prompt_builder import SYSTEM_INSTRUCTIONS, build_evidence_package, serialize_evidence_package
from rip.reasoning.service import ask_repository

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

    def test_oversized_primary_evidence_fails_before_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._repository(root)
            (root / "large.txt").write_text("x" * 2_500_000, encoding="utf-8")
            provider = FakeProvider()
            with self.assertRaisesRegex(ValueError, "Primary evidence is too large") as raised:
                ask_repository("Read it", root=root, provider=provider, primary_paths=["large.txt"])
            self.assertIsNone(provider.request)
            message = str(raised.exception)
            self.assertIn("No content was sent to the language model.", message)
            self.assertIn("- large.txt", message)
            self.assertIn("approximately", message)
            self.assertIn("800,000 tokens", message)
            self.assertIn("Selective retrieval is required.", message)

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
