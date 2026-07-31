from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..foundation import load_foundation
from ..observation import find_repository_root, observe_filesystem
from ..retrieval import CoverageStatus, DeterministicLexicalRetrievalEngine
from .models import ReasoningRequest, ReasoningResult
from .openai_provider import OpenAIProvider
from .prompt_builder import SYSTEM_INSTRUCTIONS, build_evidence_package, build_user_input, serialize_evidence_package
from .provider import ReasoningProvider
from .primary_evidence import canonical_session_catalog, load_primary_evidence, materialize_retrieved_primary_evidence

DEFAULT_MODEL = "gpt-5.5"
# GPT-5.5 has a 1,050,000-token context window. Reserve 250,000 tokens for
# output and reasoning; estimate conservatively at three UTF-8 bytes per token.
SAFE_INPUT_TOKEN_BUDGET = 800_000
CONSERVATIVE_BYTES_PER_TOKEN = 3


@dataclass(frozen=True, slots=True)
class RetrievalDecision:
    """Internal orchestration record; it is never sent to a reasoning provider."""

    oversized_request_detected: bool
    compatible_artifact_path: str | None
    retrieval_performed: bool
    retrieval_skipped: bool
    retrieval_failed: bool
    selected_chunk_count: int
    coverage_status: CoverageStatus | None
    retrieval_fingerprint: str | None


def ask_repository(
    question: str,
    *,
    root: str | Path | None = None,
    model: str | None = None,
    provider: ReasoningProvider | None = None,
    status_callback: Callable[[str], None] | None = None,
    primary_paths: list[str] | None = None,
) -> ReasoningResult:
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("Question must not be empty.")

    report = status_callback or (lambda _status: None)
    report("Locating repository...")
    repository_root = find_repository_root(root)
    report("Loading foundation...")
    foundation = load_foundation(repository_root / "00-Constitution")
    report("Observing repository...")
    observations = observe_filesystem(repository_root)
    report("Building evidence package...")
    primary = load_primary_evidence(repository_root, observations, primary_paths or [])
    if primary_paths and not primary:
        raise ValueError("Primary-evidence integration error: requested artifacts were not loaded.")
    primary, _decision = _prepare_primary_evidence(foundation, observations, cleaned, primary)
    package = build_evidence_package(foundation, observations, cleaned, primary)
    request = _build_request(cleaned, model, package)
    _preflight_request_size(request)
    active_provider = provider or OpenAIProvider()
    report("Reasoning...")
    result = active_provider.ask(request)
    report("Formatting response...")
    return result


def _build_request(question: str, model: str | None, package: dict[str, object]) -> ReasoningRequest:
    evidence_json = serialize_evidence_package(package)
    return ReasoningRequest(question, model or os.getenv("RIP_OPENAI_MODEL", DEFAULT_MODEL), build_user_input(evidence_json), SYSTEM_INSTRUCTIONS)


def _prepare_primary_evidence(foundation, observations, question: str, primary: list[dict[str, object]]) -> tuple[list[dict[str, object]], RetrievalDecision]:
    """Replace exactly one oversized compatible artifact with selected governed chunks."""
    complete_request = _build_request(question, None, build_evidence_package(foundation, observations, question, primary))
    if _estimated_tokens(complete_request) <= SAFE_INPUT_TOKEN_BUDGET:
        return primary, RetrievalDecision(False, None, False, True, False, 0, None, None)
    if not primary:
        return primary, RetrievalDecision(True, None, False, True, False, 0, None, None)

    empty_primary_request = _build_request(question, None, build_evidence_package(foundation, observations, question, []))
    remaining_for_one_artifact = max(0, SAFE_INPUT_TOKEN_BUDGET - _estimated_tokens(empty_primary_request))
    oversized = [
        item
        for item in primary
        if (
            _package_request_bytes(build_evidence_package(foundation, observations, question, [item]))
            - len(empty_primary_request.evidence_json.encode("utf-8"))
        ) / CONSERVATIVE_BYTES_PER_TOKEN > remaining_for_one_artifact
    ]
    if len(oversized) != 1:
        raise ValueError(
            "Automatic governed retrieval currently supports exactly one oversized compatible primary evidence artifact; "
            "multiple oversized artifacts or aggregate-only overflow are not yet implemented."
        )
    artifact = oversized[0]
    other_primary = [item for item in primary if item is not artifact]
    try:
        catalog = canonical_session_catalog(artifact)
    except (LookupError, ValueError) as exc:
        raise ValueError(
            f"Automatic governed retrieval cannot operate for {artifact['repository_relative_path']}: {exc}"
        ) from exc
    placeholder = {**artifact, "chunked": True, "content": ""}
    placeholder_package = build_evidence_package(foundation, observations, question, [*other_primary, placeholder])
    available_bytes = SAFE_INPUT_TOKEN_BUDGET * CONSERVATIVE_BYTES_PER_TOKEN - _package_request_bytes(placeholder_package)
    serialization_factor = max(
        len(json.dumps(chunk.content, ensure_ascii=False).encode("utf-8")) / len(chunk.content.encode("utf-8"))
        for chunk in catalog.chunks
    ) if catalog.chunks else 1
    # Reserve separators for every possible chunk; the engine alone owns selection.
    available_bytes = max(0, available_bytes - max(0, len(catalog.chunks) - 1) * 2)
    retrieval_budget = int(available_bytes / (CONSERVATIVE_BYTES_PER_TOKEN * serialization_factor))
    result = DeterministicLexicalRetrievalEngine().retrieve(question, catalog, token_budget=retrieval_budget)
    coverage = result.report.coverage[0].status
    decision = RetrievalDecision(True, artifact["repository_relative_path"], True, False, False, len(result.selected_chunks), coverage, result.report.retrieval_fingerprint)
    if not result.selected_chunks:
        raise ValueError(
            f"Automatic governed retrieval selected no evidence for {artifact['repository_relative_path']}. "
            f"Retrieval fingerprint: {result.report.retrieval_fingerprint}. No content was sent to the language model."
        )
    retrieved = materialize_retrieved_primary_evidence(artifact, result.selected_chunks)
    return [retrieved if item is artifact else item for item in primary], decision


def _preflight_request_size(request: ReasoningRequest) -> None:
    """Fail locally rather than transmit an oversized selected evidence package."""
    estimated_tokens = len(request.evidence_json.encode("utf-8")) / CONSERVATIVE_BYTES_PER_TOKEN
    if estimated_tokens <= SAFE_INPUT_TOKEN_BUDGET:
        return
    raise ValueError(
        "Selected primary evidence is too large for a single reasoning request.\n\n"
        "No content was sent to the language model.\n\n"
        "Estimated input size:\n"
        f"- approximately {estimated_tokens:,.0f} tokens\n\n"
        "Configured safe input budget:\n"
        f"- {SAFE_INPUT_TOKEN_BUDGET:,} tokens"
    )


def _estimated_tokens(request: ReasoningRequest) -> float:
    return len(request.evidence_json.encode("utf-8")) / CONSERVATIVE_BYTES_PER_TOKEN


def _package_request_bytes(package: dict[str, object]) -> int:
    """Measure a package-shaped placeholder without treating it as provider-ready evidence."""
    evidence_json = json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return len(build_user_input(evidence_json).encode("utf-8"))
