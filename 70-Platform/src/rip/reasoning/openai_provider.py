from __future__ import annotations

import os
import re
from typing import Any

from .models import ReasoningRequest, ReasoningResult

_OBSERVATION_ID = re.compile(r"\bobs-[0-9a-f]{16}\b")


class OpenAIProvider:
    """OpenAI Responses API implementation of the reasoning-provider contract."""

    def __init__(self, *, api_key: str | None = None, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return

        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Configure it as an environment variable before using 'rip ask'."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The OpenAI SDK is not installed. Run: py -m pip install -e ."
            ) from exc

        self._client = OpenAI(api_key=resolved_key)

    def ask(self, request: ReasoningRequest) -> ReasoningResult:
        response = self._client.responses.create(
            model=request.model,
            instructions=request.instructions,
            input=request.evidence_json,
        )
        answer = (getattr(response, "output_text", "") or "").strip()
        if not answer:
            raise RuntimeError("OpenAI returned no text output.")

        cited = tuple(dict.fromkeys(_OBSERVATION_ID.findall(answer)))
        available = set(_OBSERVATION_ID.findall(request.evidence_json))
        unknown = tuple(item for item in cited if item not in available)
        usage = getattr(response, "usage", None)

        return ReasoningResult(
            answer=answer,
            provider="openai",
            model=request.model,
            response_id=getattr(response, "id", None),
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            cited_observation_ids=cited,
            unknown_observation_ids=unknown,
        )
