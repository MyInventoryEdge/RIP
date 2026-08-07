"""Read-only operator work resolver over retained run evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..paths import storage_directory


@dataclass(frozen=True, slots=True)
class WorkItem:
    classification: str
    repository: str
    run_id: str
    constitutional_state: str
    explanation: str
    recommendation: str
    primary_action: str
    evidence_context: str = ""


def _json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def resolve_work(*, lifecycle_state: str, trust_action: str | None, execution_status: str | None,
                 provisioning_ready: bool, evidence_available: bool, repository: str, run_id: str, organization_id: str = "") -> WorkItem:
    """Classify exactly one operator work state from retained constitutional inputs."""
    state = lifecycle_state.replace("-", " ").title(); context = f"{organization_id} / {run_id}" if organization_id else run_id
    if not lifecycle_state or not evidence_available:
        return WorkItem("Critical", repository, run_id, state or "Unavailable", "Retained run evidence is incomplete.", "Review retained evidence.", "Open Workspace", context)
    if lifecycle_state == "paused-affected-scope" or trust_action == "pause-affected-scope":
        return WorkItem("Needs Attention", repository, run_id, "Paused — affected scope", "RIP paused only the affected runtime scope.", "Review retained runtime mutation.", "Open Workspace", context)
    if lifecycle_state == "created" and not provisioning_ready:
        return WorkItem("Needs Attention", repository, run_id, state, "Platform provisioning is required before governed continuation.", "Provision the platform.", "Provision Platform")
    if lifecycle_state in {"created", "interrupted", "awaiting-classification"}:
        return WorkItem("In Progress", repository, run_id, state, "Retained work is awaiting its next governed stage.", "Observe progress.", "Observe Progress")
    if lifecycle_state == "observed" and execution_status == "completed":
        return WorkItem("Completed Today", repository, run_id, state, "A governed decision completed for this retained run.", "View the decision.", "View Decision")
    return WorkItem("Healthy", repository, run_id, state, "No operator action is currently required.", "View retained evidence.", "View Decision")


def load_work_queue(*, provisioning_ready: bool, include_constitutional: bool = False) -> tuple[WorkItem, ...]:
    root = storage_directory("Workspace")
    items = []
    # Constitutional bootstrap is retained state and is resolved through this
    # one work-queue boundary, alongside all other operator recommendations.
    if include_constitutional and not (storage_directory("State") / "sda-bootstrap.json").exists():
        items.append(WorkItem("Critical", "RIP", "sda-first-decision", "Bootstrap required",
            "Constitutional Bootstrap must be completed before constitutional evolution can continue.",
            "Review the pending constitutional decision.", "REVIEW CONSTITUTIONAL DECISION", "sda-first-decision"))
    elif include_constitutional and (storage_directory("State") / "sda-published-decision.json").exists():
        items.append(WorkItem("Healthy", "RIP", "sda-first-decision", "Bootstrap complete",
            "The first constitutional decision is active and its Journal publication is retained.",
            "Constitutional Bootstrap Complete.", "View Published Decision", "sda-first-decision"))
    if not root.is_dir(): return tuple(items)
    for run in sorted(root.glob("*/onboarding-runs/*"), key=lambda item: item.name, reverse=True):
        context, state = _json(run / "context.json"), _json(run / "state.json")
        action, receipt = _json(run / "trust-action.json"), _json(run / "trust-execution-receipt.json")
        action_value = action.get("action", {}).get("action") if isinstance(action.get("action"), dict) else None
        items.append(resolve_work(
            lifecycle_state=str(state.get("state", "")), trust_action=str(action_value) if action_value else None,
            execution_status=str(receipt.get("status")) if receipt.get("status") else None,
            provisioning_ready=provisioning_ready,
            evidence_available=(run / "context.json").is_file() and (run / "state.json").is_file(),
            repository=str(context.get("repository_path", "Not retained")), run_id=str(context.get("onboarding_run_id", run.name)), organization_id=run.parent.parent.name,
        ))
    return tuple(items)


def primary_recommendation(items: tuple[WorkItem, ...]) -> WorkItem | None:
    """Presentation selection only; work classification remains above."""
    attention = ("Critical", "Needs Attention", "In Progress")
    return next((item for classification in attention for item in items if item.classification == classification), None)
