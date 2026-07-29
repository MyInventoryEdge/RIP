from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReasoningRequest:
    question: str
    model: str
    evidence_json: str
    instructions: str


@dataclass(frozen=True, slots=True)
class ReasoningResult:
    answer: str
    provider: str
    model: str
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cited_observation_ids: tuple[str, ...] = ()
    unknown_observation_ids: tuple[str, ...] = ()
