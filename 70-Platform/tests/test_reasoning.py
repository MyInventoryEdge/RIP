from __future__ import annotations

import json
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

FIXTURE_FOUNDATION = Path(__file__).parent / "fixtures" / "00-Constitution"


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
        (root / "00-Constitution").mkdir()
        for source in FIXTURE_FOUNDATION.iterdir():
            (root / "00-Constitution" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
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
            self.assertEqual(len(decoded["foundation"]["artifacts"]), 5)
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
