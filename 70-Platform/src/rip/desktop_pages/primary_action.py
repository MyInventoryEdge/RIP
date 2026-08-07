"""Reusable presentation model for one operator next action."""
from __future__ import annotations
from dataclasses import dataclass
from .work_queue import WorkItem, primary_recommendation

@dataclass(frozen=True, slots=True)
class PrimaryAction:
    summary: str
    reason: str
    estimated_time: str
    button_label: str | None
    work_item: WorkItem | None
    has_more_work: bool

def resolve_primary_action(items: tuple[WorkItem, ...]) -> PrimaryAction:
    item = primary_recommendation(items)
    if item is None:
        completed = next((candidate for candidate in items if candidate.run_id == "sda-first-decision" and candidate.constitutional_state == "Bootstrap complete"), None)
        if completed is not None:
            return PrimaryAction("Constitutional Bootstrap Complete.", completed.explanation, "", None, None, False)
        return PrimaryAction("Nothing requires your attention.", "RIP has completed every action it is constitutionally authorized to perform.", "", None, None, False)
    estimate = "3 minutes" if item.run_id == "sda-first-decision" else "2 minutes"
    return PrimaryAction(item.recommendation, item.explanation, estimate, item.primary_action, item, len(items) > 1)
