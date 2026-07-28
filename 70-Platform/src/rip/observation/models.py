from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Observation:
    """A deterministic statement about evidence visible to an observer."""

    observation_id: str
    observed_at: datetime
    source: str
    subject: str
    kind: str
    path: Path
    relative_path: str
    evidence: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["observed_at"] = self.observed_at.astimezone(timezone.utc).isoformat()
        value["path"] = str(self.path)
        value["evidence"] = list(self.evidence)
        return value


@dataclass(frozen=True, slots=True)
class ObservationSet:
    root: Path
    observed_at: datetime
    observations: tuple[Observation, ...]
    excluded_names: tuple[str, ...] = ()

    def by_kind(self, kind: str) -> tuple[Observation, ...]:
        return tuple(item for item in self.observations if item.kind == kind)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.observations:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat(),
            "excluded_names": list(self.excluded_names),
            "counts": self.counts(),
            "observations": [item.to_dict() for item in self.observations],
        }
