"""Artifact-location boundary for Producer Policy Authority evidence."""
from __future__ import annotations

from pathlib import Path

from .paths import storage_directory


class PlatformProducerPolicyStorage:
    """Production locations only; policy meaning belongs to the authority."""

    def policy_history_path(self) -> Path:
        return storage_directory("State") / "producer-policy-history.ndjson"

    def certificate_path(self) -> Path:
        return storage_directory("State") / "producer-admission-certificates.ndjson"

    def event_path(self) -> Path:
        return storage_directory("State") / "producer-policy-events.ndjson"

    def current_policy_path(self) -> Path:
        return storage_directory("State") / "producer-policy-current.json"
