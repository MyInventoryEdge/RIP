"""Chronological, read-only projection of existing operational evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..paths import storage_directory


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    timestamp: str
    title: str
    description: str
    status: str
    evidence: str
    run: str
    detail: str


def load_history(query: str = "") -> tuple[HistoryEntry, ...]:
    root = storage_directory("Workspace")
    entries = []
    if not root.is_dir():
        return ()
    for path in root.glob("*/audit/audit.json"):
        try:
            for item in json.loads(path.read_text(encoding="utf-8")):
                operation = str(item.get("operation", "platform activity")).replace("-", " ").title()
                payload = item.get("payload", {})
                run = str(payload.get("run_id", "-")) if isinstance(payload, dict) else "-"
                detail = f"Audit sequence: {item.get('sequence', 'unknown')}. Retained operation: {operation}."
                entries.append(HistoryEntry("Recorded", operation, "Retained audit activity.", "Recorded", "Available", run, detail))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    for path in root.glob("*/onboarding-runs/*/stages.json"):
        try:
            for item in json.loads(path.read_text(encoding="utf-8")):
                stage = str(item.get("stage", "activity")).replace("-", " ").title()
                status = str(item.get("state", "Recorded")).replace("-", " ").title()
                references = item.get("references", [])
                reference_count = len(references) if isinstance(references, list) else 0
                detail = f"Retained stage: {stage}. State: {status}. Processed entries: {item.get('processed_entry_count', 0)}. Evidence references: {reference_count}."
                entries.append(HistoryEntry(str(item.get("operational_timestamp", "Recorded")), stage, "Retained run stage.", status, "Available", str(item.get("run_id", "-")), detail))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    needle = query.casefold().strip()
    return tuple(item for item in sorted(entries, key=lambda item: item.timestamp, reverse=True) if not needle or needle in " ".join((item.title, item.description, item.run, item.status, item.detail)).casefold())
