from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class InterpretationRequest:
    """A provider-neutral request for one chronological session chunk."""

    model: str
    instructions: str
    input_json: str
    repair: bool = False


class Interpreter(Protocol):
    """Interchangeable source of structured knowledge candidates."""

    def interpret(self, request: InterpretationRequest) -> str: ...
