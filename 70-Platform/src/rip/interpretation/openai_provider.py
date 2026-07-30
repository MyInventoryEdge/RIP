from __future__ import annotations

import os
from typing import Any

from .provider import InterpretationRequest


_CANDIDATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "type", "title", "summary", "confidence", "status", "reasoning", "evidence"],
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": ["architectural_decision"]},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "status": {"type": "string", "enum": ["candidate"]},
                    "reasoning": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["message_id", "span_index"],
                            "properties": {
                                "message_id": {"type": "string"},
                                "span_index": {"type": "integer", "minimum": 0},
                            },
                        },
                    },
                },
            },
        },
    },
}


class OpenAIInterpreter:
    """OpenAI Responses API implementation of the Interpreter contract."""

    def __init__(self, *, api_key: str | None = None, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY is not set. Configure it before using 'rip interpret'.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The OpenAI SDK is not installed. Run: py -m pip install -e .") from exc
        self._client = OpenAI(api_key=resolved_key)

    def interpret(self, request: InterpretationRequest) -> str:
        response = self._client.responses.create(
            model=request.model,
            instructions=request.instructions,
            input=request.input_json,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "architectural_decision_candidates",
                    "strict": True,
                    "schema": _CANDIDATE_SCHEMA,
                }
            },
        )
        text = (getattr(response, "output_text", "") or "").strip()
        if not text:
            raise RuntimeError("OpenAI returned no text output for interpretation.")
        return text
