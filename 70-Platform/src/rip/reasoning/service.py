from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from ..foundation import load_foundation
from ..observation import find_repository_root, observe_filesystem
from .models import ReasoningRequest, ReasoningResult
from .openai_provider import OpenAIProvider
from .prompt_builder import SYSTEM_INSTRUCTIONS, build_evidence_package, build_user_input, serialize_evidence_package
from .provider import ReasoningProvider
from .primary_evidence import load_primary_evidence

DEFAULT_MODEL = "gpt-5.5"
# GPT-5.5 has a 1,050,000-token context window. Reserve 250,000 tokens for
# output and reasoning; estimate conservatively at three UTF-8 bytes per token.
SAFE_INPUT_TOKEN_BUDGET = 800_000
CONSERVATIVE_BYTES_PER_TOKEN = 3


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
    package = build_evidence_package(foundation, observations, cleaned, primary)
    evidence_json = serialize_evidence_package(package)
    request = ReasoningRequest(
        question=cleaned,
        model=model or os.getenv("RIP_OPENAI_MODEL", DEFAULT_MODEL),
        evidence_json=build_user_input(evidence_json),
        instructions=SYSTEM_INSTRUCTIONS,
    )
    _preflight_primary_evidence(request, primary)
    active_provider = provider or OpenAIProvider()
    report("Reasoning...")
    result = active_provider.ask(request)
    report("Formatting response...")
    return result


def _preflight_primary_evidence(request: ReasoningRequest, primary: list[dict[str, object]]) -> None:
    """Fail locally rather than transmit oversized selected evidence."""
    if not primary:
        return
    estimated_tokens = len(request.evidence_json.encode("utf-8")) / CONSERVATIVE_BYTES_PER_TOKEN
    if estimated_tokens <= SAFE_INPUT_TOKEN_BUDGET:
        return
    paths = "\n".join(f"- {item['repository_relative_path']}" for item in primary)
    raise ValueError(
        "Primary evidence is too large for a single reasoning request.\n\n"
        "No content was sent to the language model.\n\n"
        "Oversized artifact(s):\n"
        f"{paths}\n\n"
        "Estimated input size:\n"
        f"- approximately {estimated_tokens:,.0f} tokens\n\n"
        "Configured safe input budget:\n"
        f"- {SAFE_INPUT_TOKEN_BUDGET:,} tokens\n\n"
        "Selective retrieval is required.\n\n"
        "Examples:\n\n"
        "• Summarize the first 100 messages.\n"
        "• Explain the architectural decisions regarding provider serialization.\n"
        "• Show discussions related to evidence packages.\n"
        "• Find every discussion mentioning parser-manifest.json.\n"
        "• Summarize the final implementation decisions.\n"
        "• Search for references to \"JD Power\".\n\n"
        "Future versions of RIP will perform selective retrieval automatically."
    )
