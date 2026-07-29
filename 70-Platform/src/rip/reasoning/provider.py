from __future__ import annotations

from typing import Protocol

from .models import ReasoningRequest, ReasoningResult


class ReasoningProvider(Protocol):
    """Vendor-neutral contract for reasoning over a supplied evidence package."""

    def ask(self, request: ReasoningRequest) -> ReasoningResult:
        ...
