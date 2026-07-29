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

DEFAULT_MODEL = "gpt-5.5"


def ask_repository(
    question: str,
    *,
    root: str | Path | None = None,
    model: str | None = None,
    provider: ReasoningProvider | None = None,
    status_callback: Callable[[str], None] | None = None,
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
    package = build_evidence_package(foundation, observations, cleaned)
    evidence_json = serialize_evidence_package(package)
    request = ReasoningRequest(
        question=cleaned,
        model=model or os.getenv("RIP_OPENAI_MODEL", DEFAULT_MODEL),
        evidence_json=build_user_input(evidence_json),
        instructions=SYSTEM_INSTRUCTIONS,
    )
    active_provider = provider or OpenAIProvider()
    report("Reasoning...")
    result = active_provider.ask(request)
    report("Formatting response...")
    return result
