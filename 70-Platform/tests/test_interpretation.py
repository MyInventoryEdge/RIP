from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rip.interpretation.provider import InterpretationRequest
from rip.interpretation.service import chunk_messages, evidence_spans, interpret_session, resolve_span_references, validate_candidates
from rip.interpretation.openai_provider import OpenAIInterpreter


class FakeInterpreter:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.requests: list[InterpretationRequest] = []

    def interpret(self, request: InterpretationRequest) -> str:
        self.requests.append(request)
        return next(self.responses)


def session(messages: list[str]) -> dict[str, object]:
    return {
        "session_id": "test-session", "validation": {"passed": True},
        "messages": [{"source_message_id": f"m-{index}", "source_order": index, "role": "user", "markdown": text} for index, text in enumerate(messages)],
    }


def candidate(identifier: str, message_id: str, text: str, title: str = "Use SQLite") -> dict[str, object]:
    return {"id": identifier, "type": "architectural_decision", "title": title, "summary": "SQLite was adopted.", "confidence": 0.9, "status": "candidate", "reasoning": "The session explicitly adopts it.", "evidence": [{"message_id": message_id, "excerpt": text, "start_offset": 0, "end_offset": len(text)}]}


class InterpretationTests(unittest.TestCase):
    def write_session(self, directory: Path, payload: dict[str, object]) -> Path:
        path = directory / "canonical-session.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_empty_session_writes_valid_empty_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result = interpret_session(self.write_session(directory, session([])), directory / "out", interpreter=FakeInterpreter([]))
            self.assertEqual([], result.candidates)
            self.assertEqual(0, result.chunks_processed)
            self.assertTrue((directory / "out" / "candidate-knowledge.json").exists())

    def test_single_message_decision(self) -> None:
        text = "We approve SQLite as the embedded database."
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result = interpret_session(self.write_session(directory, session([text])), directory / "out", interpreter=FakeInterpreter([json.dumps({"candidates": [candidate("raw-1", "m-0", text)]})]))
            self.assertEqual(1, len(result.candidates))
            self.assertEqual("decision-19b70b14878cd0af", result.candidates[0].id)
            self.assertEqual(1, result.messages_with_evidence)

    def test_conflicting_or_unresolved_messages_can_produce_no_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result = interpret_session(self.write_session(directory, session(["Maybe SQLite.", "Or perhaps Postgres?"])), directory / "out", interpreter=FakeInterpreter(["{\"candidates\": []}"]))
            self.assertEqual([], result.candidates)

    def test_duplicate_decisions_merge_all_evidence_across_chunks(self) -> None:
        first, second = "SQLite is adopted.", "The SQLite decision is confirmed."
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result = interpret_session(self.write_session(directory, session([first, second])), directory / "out", interpreter=FakeInterpreter([json.dumps({"candidates": [candidate("raw-1", "m-0", first)]}), json.dumps({"candidates": [candidate("raw-2", "m-1", second)]})]), chunk_characters=len(first) + 10)
            self.assertEqual(1, len(result.candidates))
            self.assertEqual(2, len(result.candidates[0].evidence))

    def test_malformed_output_is_retried_once(self) -> None:
        text = "SQLite is adopted."
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            provider = FakeInterpreter(["not-json", json.dumps({"candidates": [candidate("raw-1", "m-0", text)]})])
            result = interpret_session(self.write_session(directory, session([text])), directory / "out", interpreter=provider)
            self.assertEqual(1, len(result.candidates))
            self.assertEqual(2, len(provider.requests))
            self.assertTrue(provider.requests[1].repair)

    def test_invalid_evidence_reference_fails_after_repair(self) -> None:
        payload = session(["SQLite is adopted."])
        invalid = candidate("raw-1", "missing", "SQLite is adopted.")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with self.assertRaisesRegex(ValueError, "invalid message id"):
                interpret_session(self.write_session(directory, payload), directory / "out", interpreter=FakeInterpreter([json.dumps({"candidates": [invalid]}), json.dumps({"candidates": [invalid]})]))

    def test_duplicate_candidate_ids_are_rejected(self) -> None:
        payload = session(["One."])
        item = candidate("same", "m-0", "One.")
        _, errors = validate_candidates([item, item], payload, {"m-0"})
        self.assertTrue(any("duplicate candidate id" in error for error in errors))

    def test_chunking_preserves_chronological_message_boundaries(self) -> None:
        messages = session(["a" * 10, "b" * 10, "c" * 10])["messages"]
        chunks = chunk_messages(messages, 90)  # each serialized message remains an intact unit
        self.assertEqual(["m-0", "m-1", "m-2"], [item["source_message_id"] for chunk in chunks for item in chunk])
        self.assertEqual(3, len(chunks))

    def test_evidence_spans_are_exact_message_substrings(self) -> None:
        text = "First decision.\nSecond decision."
        spans = evidence_spans(text)
        self.assertIn({"excerpt": "First decision.", "start_offset": 0, "end_offset": 15, "span_index": 0}, spans)
        self.assertTrue(all(text[item["start_offset"]:item["end_offset"]] == item["excerpt"] for item in spans))

    def test_provider_span_reference_resolves_to_public_evidence(self) -> None:
        payload = session(["SQLite is adopted."])
        raw = candidate("raw-1", "m-0", "SQLite is adopted.")
        raw["evidence"] = [{"message_id": "m-0", "span_index": 0}]
        resolved, errors = resolve_span_references([raw], payload)
        self.assertEqual([], errors)
        self.assertEqual("SQLite is adopted.", resolved[0]["evidence"][0]["excerpt"])

    def test_production_fixture_loads_and_chunks_without_provider_calls(self) -> None:
        fixture = Path(r"C:\Temp\rip-canonical-session-validation\canonical-session.json")
        if not fixture.exists():
            self.skipTest("Production fixture is not available at its validated local path.")
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(1334, len(payload["messages"]))
        self.assertGreater(len(chunk_messages(payload["messages"], 100_000)), 1)

    def test_openai_provider_requests_strict_candidate_schema(self) -> None:
        class Responses:
            def create(self, **kwargs):
                self.kwargs = kwargs
                return type("Response", (), {"output_text": "{\"candidates\": []}"})()
        client = type("Client", (), {"responses": Responses()})()
        result = OpenAIInterpreter(client=client).interpret(InterpretationRequest("test", "instructions", "{}"))
        self.assertEqual('{"candidates": []}', result)
        self.assertEqual("json_schema", client.responses.kwargs["text"]["format"]["type"])
        self.assertTrue(client.responses.kwargs["text"]["format"]["strict"])


if __name__ == "__main__":
    unittest.main()
