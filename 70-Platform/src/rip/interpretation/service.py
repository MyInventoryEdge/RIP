from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .openai_provider import OpenAIInterpreter
from .provider import InterpretationRequest, Interpreter

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_CHUNK_CHARACTERS = 100_000


@dataclass(frozen=True, slots=True)
class Evidence:
    message_id: str
    excerpt: str
    start_offset: int
    end_offset: int

    def to_dict(self) -> dict[str, object]:
        return {"message_id": self.message_id, "excerpt": self.excerpt, "start_offset": self.start_offset, "end_offset": self.end_offset}


@dataclass(frozen=True, slots=True)
class KnowledgeCandidate:
    id: str
    type: str
    title: str
    summary: str
    confidence: float
    status: str
    reasoning: str
    source_session: str
    evidence: tuple[Evidence, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id, "type": self.type, "title": self.title, "summary": self.summary,
            "confidence": self.confidence, "status": self.status, "reasoning": self.reasoning,
            "source_session": self.source_session,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(slots=True)
class InterpretationResult:
    candidates: list[KnowledgeCandidate]
    model: str
    prompt_version: str
    processing_seconds: float
    chunks_processed: int
    rejected_candidates: int = 0
    validation_failures: list[str] = field(default_factory=list)
    messages_with_evidence: int = 0


def interpret_session(
    input_path: Path,
    output_directory: Path,
    *,
    interpreter: Interpreter | None = None,
    model: str = DEFAULT_MODEL,
    chunk_characters: int = DEFAULT_CHUNK_CHARACTERS,
) -> InterpretationResult:
    session = load_validated_session(input_path)
    prompt, repair_prompt, prompt_version = load_prompt()
    chunks = chunk_messages(session["messages"], chunk_characters)
    provider = interpreter or OpenAIInterpreter()
    started = time.monotonic()
    raw_candidates: list[KnowledgeCandidate] = []
    validation_failures: list[str] = []
    rejected = 0
    for number, chunk in enumerate(chunks, start=1):
        request = InterpretationRequest(model, prompt, build_chunk_input(session, chunk, number, len(chunks)))
        candidates, errors = request_candidates(provider, request, session, {item["source_message_id"] for item in chunk})
        if errors:
            repair_request = InterpretationRequest(model, repair_prompt, build_repair_input(request.input_json, errors), repair=True)
            candidates, errors = request_candidates(provider, repair_request, session, {item["source_message_id"] for item in chunk})
        if errors:
            validation_failures.extend(f"chunk {number}: {error}" for error in errors)
            raise ValueError("Interpretation validation failed after one repair attempt: " + "; ".join(errors))
        raw_candidates.extend(candidates)
    merged = merge_candidates(raw_candidates)
    evidence_ids = {evidence.message_id for candidate in merged for evidence in candidate.evidence}
    result = InterpretationResult(
        candidates=merged, model=model, prompt_version=prompt_version,
        processing_seconds=time.monotonic() - started, chunks_processed=len(chunks),
        rejected_candidates=rejected, validation_failures=validation_failures,
        messages_with_evidence=len(evidence_ids),
    )
    write_outputs(result, session, input_path, output_directory)
    return result


def load_validated_session(path: Path) -> dict[str, Any]:
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Canonical session is not valid JSON: {path}") from exc
    if not isinstance(session, dict) or not isinstance(session.get("messages"), list):
        raise ValueError("Canonical session must contain a messages array.")
    validation = session.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        raise ValueError("Canonical session must have passed parser validation before interpretation.")
    session_id = session.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Canonical session must contain a nonempty session_id.")
    known: set[str] = set()
    for index, message in enumerate(session["messages"]):
        if not isinstance(message, dict):
            raise ValueError(f"Canonical message {index} must be an object.")
        message_id = message.get("source_message_id")
        markdown = message.get("markdown")
        if not isinstance(message_id, str) or not message_id or not isinstance(markdown, str):
            raise ValueError(f"Canonical message {index} lacks source_message_id or markdown.")
        if message_id in known:
            raise ValueError(f"Canonical session has duplicate message identifier: {message_id}")
        known.add(message_id)
    return session


def chunk_messages(messages: list[dict[str, Any]], maximum_characters: int) -> list[list[dict[str, Any]]]:
    if maximum_characters <= 0:
        raise ValueError("chunk_characters must be positive.")
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for message in messages:
        representation = json.dumps({"message_id": message["source_message_id"], "source_order": message.get("source_order"), "role": message.get("role"), "markdown": message["markdown"]}, ensure_ascii=False)
        length = len(representation)
        if current and size + length > maximum_characters:
            chunks.append(current)
            current, size = [], 0
        current.append(message)
        size += length
    if current:
        chunks.append(current)
    return chunks


def load_prompt() -> tuple[str, str, str]:
    path = Path(__file__).resolve().parents[3] / "prompts" / "architectural_decisions.md"
    text = path.read_text(encoding="utf-8")
    version_match = re.search(r"^Prompt-Version:\s*(.+)$", text, flags=re.MULTILINE)
    if not version_match:
        raise ValueError("Architectural decisions prompt is missing Prompt-Version metadata.")
    marker = "<!-- REPAIR INSTRUCTIONS -->"
    if marker not in text:
        raise ValueError("Architectural decisions prompt is missing repair instructions.")
    prompt, repair = text.split(marker, maxsplit=1)
    return prompt.strip(), repair.strip(), version_match.group(1).strip()


def build_chunk_input(session: dict[str, Any], chunk: list[dict[str, Any]], number: int, total: int) -> str:
    return json.dumps({"session_id": session["session_id"], "chunk": {"number": number, "total": total}, "messages": [{"message_id": item["source_message_id"], "source_order": item.get("source_order"), "role": item.get("role"), "markdown": item["markdown"], "evidence_spans": evidence_spans(item["markdown"])} for item in chunk]}, ensure_ascii=False)


def evidence_spans(markdown: str) -> list[dict[str, object]]:
    """Offer exact, deterministic message-local excerpts so providers need not count offsets."""
    spans: list[dict[str, object]] = []
    seen: set[tuple[int, int]] = set()
    for match in re.finditer(r"[^\n]+", markdown):
        start, end = match.span()
        if (start, end) not in seen:
            seen.add((start, end))
            spans.append({"excerpt": markdown[start:end], "start_offset": start, "end_offset": end})
    for match in re.finditer(r"(?s)[^.!?\n]+[.!?](?=\s|$)", markdown):
        start, end = match.span()
        excerpt = markdown[start:end]
        if excerpt.strip() and (start, end) not in seen:
            seen.add((start, end))
            spans.append({"excerpt": excerpt, "start_offset": start, "end_offset": end})
    for index, span in enumerate(spans):
        span["span_index"] = index
    return spans


def build_repair_input(original_input: str, errors: list[str]) -> str:
    return json.dumps({"original_input": json.loads(original_input), "validation_errors": errors}, ensure_ascii=False)


def request_candidates(provider: Interpreter, request: InterpretationRequest, session: dict[str, Any], allowed_ids: set[str]) -> tuple[list[KnowledgeCandidate], list[str]]:
    try:
        parsed = json.loads(provider.interpret(request))
    except json.JSONDecodeError:
        return [], ["model output is not valid JSON"]
    if not isinstance(parsed, dict) or not isinstance(parsed.get("candidates"), list):
        return [], ["model output must be an object with a candidates array"]
    resolved, errors = resolve_span_references(parsed["candidates"], session)
    candidates, validation_errors = validate_candidates(resolved, session, allowed_ids)
    return candidates, errors + validation_errors


def resolve_span_references(raw_candidates: list[Any], session: dict[str, Any]) -> tuple[list[Any], list[str]]:
    """Resolve provider span references into the public, offset-based evidence schema."""
    markdown_by_id = {item["source_message_id"]: item["markdown"] for item in session["messages"]}
    resolved: list[Any] = []
    errors: list[str] = []
    for candidate_index, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict) or not isinstance(raw.get("evidence"), list):
            resolved.append(raw)
            continue
        copy = dict(raw)
        evidence_items: list[Any] = []
        for evidence_index, evidence in enumerate(raw["evidence"]):
            if not isinstance(evidence, dict) or "span_index" not in evidence:
                evidence_items.append(evidence)
                continue
            message_id, span_index = evidence.get("message_id"), evidence.get("span_index")
            if not isinstance(message_id, str) or message_id not in markdown_by_id or isinstance(span_index, bool) or not isinstance(span_index, int):
                errors.append(f"candidate {candidate_index} evidence {evidence_index} has invalid span reference")
                evidence_items.append(evidence)
                continue
            spans = evidence_spans(markdown_by_id[message_id])
            if not 0 <= span_index < len(spans):
                errors.append(f"candidate {candidate_index} evidence {evidence_index} has invalid span reference")
                evidence_items.append(evidence)
                continue
            span = spans[span_index]
            evidence_items.append({"message_id": message_id, "excerpt": span["excerpt"], "start_offset": span["start_offset"], "end_offset": span["end_offset"]})
        copy["evidence"] = evidence_items
        resolved.append(copy)
    return resolved, errors


def validate_candidates(raw_candidates: list[Any], session: dict[str, Any], allowed_ids: set[str]) -> tuple[list[KnowledgeCandidate], list[str]]:
    messages = {item["source_message_id"]: item["markdown"] for item in session["messages"]}
    candidates: list[KnowledgeCandidate] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_candidates):
        prefix = f"candidate {index}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} is not an object")
            continue
        identifier = raw.get("id")
        title, reasoning = raw.get("title"), raw.get("reasoning")
        if not isinstance(identifier, str) or not identifier.strip(): errors.append(f"{prefix} has missing id")
        elif identifier in seen_ids: errors.append(f"{prefix} has duplicate candidate id {identifier}")
        else: seen_ids.add(identifier)
        if not isinstance(title, str) or not title.strip(): errors.append(f"{prefix} has missing title")
        if not isinstance(reasoning, str) or not reasoning.strip(): errors.append(f"{prefix} has missing reasoning")
        confidence = raw.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1: errors.append(f"{prefix} has invalid confidence")
        if raw.get("type") != "architectural_decision": errors.append(f"{prefix} must have type architectural_decision")
        if raw.get("status") != "candidate": errors.append(f"{prefix} must have status candidate")
        evidence_raw = raw.get("evidence")
        if not isinstance(evidence_raw, list) or not evidence_raw:
            errors.append(f"{prefix} has no evidence")
            continue
        evidence: list[Evidence] = []
        for evidence_index, item in enumerate(evidence_raw):
            evidence_prefix = f"{prefix} evidence {evidence_index}"
            if not isinstance(item, dict): errors.append(f"{evidence_prefix} is not an object"); continue
            message_id, excerpt = item.get("message_id"), item.get("excerpt")
            start, end = item.get("start_offset"), item.get("end_offset")
            if not isinstance(message_id, str) or message_id not in messages: errors.append(f"{evidence_prefix} references an invalid message id"); continue
            if message_id not in allowed_ids: errors.append(f"{evidence_prefix} references a message outside its chunk"); continue
            if not isinstance(excerpt, str) or not excerpt: errors.append(f"{evidence_prefix} has empty excerpt"); continue
            if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start or end > len(messages[message_id]): errors.append(f"{evidence_prefix} has invalid offsets"); continue
            if messages[message_id][start:end] != excerpt: errors.append(f"{evidence_prefix} excerpt does not match its message offsets"); continue
            evidence.append(Evidence(message_id, excerpt, start, end))
        if len(evidence) != len(evidence_raw): continue
        if all(isinstance(raw.get(key), str) and raw[key].strip() for key in ("id", "title", "reasoning", "summary")) and isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0 <= confidence <= 1 and raw.get("type") == "architectural_decision" and raw.get("status") == "candidate":
            candidates.append(KnowledgeCandidate(raw["id"], raw["type"], raw["title"].strip(), raw["summary"].strip(), float(confidence), raw["status"], raw["reasoning"].strip(), session["session_id"], tuple(evidence)))
        elif not isinstance(raw.get("summary"), str) or not raw["summary"].strip():
            errors.append(f"{prefix} has missing summary")
    return candidates, errors


def merge_candidates(candidates: list[KnowledgeCandidate]) -> list[KnowledgeCandidate]:
    merged: dict[tuple[str, str], KnowledgeCandidate] = {}
    for candidate in candidates:
        key = (candidate.type, " ".join(candidate.title.casefold().split()))
        existing = merged.get(key)
        if existing is None:
            identifier = "decision-" + hashlib.sha256((candidate.type + "\0" + key[1]).encode("utf-8")).hexdigest()[:16]
            merged[key] = KnowledgeCandidate(identifier, candidate.type, candidate.title, candidate.summary, candidate.confidence, candidate.status, candidate.reasoning, candidate.source_session, candidate.evidence)
            continue
        evidence = list(existing.evidence)
        present = {(item.message_id, item.start_offset, item.end_offset, item.excerpt) for item in evidence}
        evidence.extend(item for item in candidate.evidence if (item.message_id, item.start_offset, item.end_offset, item.excerpt) not in present)
        merged[key] = KnowledgeCandidate(existing.id, existing.type, existing.title, existing.summary, max(existing.confidence, candidate.confidence), existing.status, existing.reasoning, existing.source_session, tuple(evidence))
    return list(merged.values())


def write_outputs(result: InterpretationResult, session: dict[str, Any], input_path: Path, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    candidates_path = output_directory / "candidate-knowledge.json"
    manifest_path = output_directory / "interpretation-manifest.json"
    report_path = output_directory / "interpretation-report.md"
    candidates_path.write_text(json.dumps({"source_session": session["session_id"], "knowledge_type": "architectural_decision", "candidates": [item.to_dict() for item in result.candidates]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {"input": str(input_path), "outputs": [candidates_path.name, report_path.name], "knowledge_type": "architectural_decision", "model": result.model, "prompt_version": result.prompt_version, "chunks_processed": result.chunks_processed, "processing_seconds": result.processing_seconds, "candidate_count": len(result.candidates), "messages_with_evidence": result.messages_with_evidence, "rejected_candidates": result.rejected_candidates, "validation_failures": result.validation_failures, "validation": "PASS"}
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total_messages = len(session["messages"])
    average = sum(item.confidence for item in result.candidates) / len(result.candidates) if result.candidates else 0.0
    report_path.write_text("\n".join(["# Knowledge Interpretation Report", "", "Knowledge Type: Architectural Decisions", f"Processing time: {result.processing_seconds:.2f} seconds", f"Model: {result.model}", f"Prompt version: {result.prompt_version}", f"Candidates: {len(result.candidates)}", f"Average confidence: {average:.2f}", f"Evidence coverage: {result.messages_with_evidence} of {total_messages} messages", f"Rejected: {result.rejected_candidates}", f"Validation failures: {len(result.validation_failures)}", "Validation: PASS", "", "Knowledge Interpretation Complete", "" ]), encoding="utf-8")
