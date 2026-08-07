"""Read-only operator projection of retained onboarding runs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..paths import storage_directory


@dataclass(frozen=True, slots=True)
class RunSummary:
    name: str
    status: str
    progress: str
    started: str
    last_activity: str
    run_id: str
    detail: str
    source: str
    lifecycle_state: str


_LABELS = {
    "created": "Waiting",
    "observed": "Completed",
    "awaiting-classification": "Needs Review",
    "paused-affected-scope": "Paused — affected scope",
    "interrupted": "Interrupted",
}


def _read_json(path: Path, default: object) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _run_projection(run: Path, context: dict[str, object], state: str, stages: list[object]) -> RunSummary:
    latest = stages[-1] if stages and isinstance(stages[-1], dict) else {}
    stage = str(latest.get("stage", "awaiting-work"))
    last_activity = str(latest.get("operational_timestamp", "Not yet active"))
    run_id = str(context.get("onboarding_run_id", run.name))
    name = f"{context.get('organization_id', 'Organization')} / {run_id}"
    difference = run / "integrity-difference.json"
    reasoning = run / "mutation-reasoning.json"
    if state == "created" and difference.is_file():
        return RunSummary(
            name, "Attention required", "Integrity difference retained", run_id, last_activity, run_id,
            "Lifecycle state: Created. Integrity Verification completed and retained a source difference. "
            f"Mutation reasoning retained: {'Yes' if reasoning.is_file() else 'No'}. "
            "Open Evidence to review the retained run artifacts.", str(context.get("repository_path", "")), state,
        )
    if state == "paused-affected-scope":
        completed = next((item for item in reversed(stages) if isinstance(item, dict) and item.get("state") == "completed"), {})
        completed_stage = str(completed.get("stage", "not retained")).replace("-", " ").title()
        return RunSummary(
            name, "Paused — affected scope", f"Last completed stage: {completed_stage}", run_id, last_activity, run_id,
            f"Source: {context.get('repository_path', '')}. Lifecycle state: Paused — affected scope. "
            f"Last completed stage: {completed_stage}. Evidence available.", str(context.get("repository_path", "")), state,
        )
    return RunSummary(
        name, _LABELS.get(state, "Unknown"), stage.replace("-", " ").title(), run_id, last_activity, run_id,
        f"Lifecycle state: {state.replace('-', ' ').title()}. Latest retained stage: {stage.replace('-', ' ').title()} "
        f"({str(latest.get('state', 'recorded')).replace('-', ' ')}).", str(context.get("repository_path", "")), state,
    )


def load_runs() -> tuple[RunSummary, ...]:
    root = storage_directory("Workspace")
    if not root.is_dir():
        return ()
    result = []
    for run in sorted(root.glob("*/onboarding-runs/*"), key=lambda path: path.name, reverse=True):
        try:
            state_data = _read_json(run / "state.json", {})
            context_data = _read_json(run / "context.json", {})
            stages_data = _read_json(run / "stages.json", [])
            if not isinstance(state_data, dict) or not isinstance(context_data, dict) or not isinstance(stages_data, list):
                continue
            result.append(_run_projection(run, context_data, str(state_data.get("state", "unknown")), stages_data))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return tuple(result)


def run_display_text(run: RunSummary) -> str:
    """One complete, read-only operator row for a retained run."""
    return f"{run.name}  —  {run.status}  —  Source: {run.source}  —  {run.progress}  —  Evidence available"
