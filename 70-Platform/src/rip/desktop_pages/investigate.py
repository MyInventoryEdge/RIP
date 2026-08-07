"""Safe operator presentation of retained evidence; no replay or interpretation."""
from __future__ import annotations

import json
import getpass
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..paths import storage_directory


@dataclass(frozen=True, slots=True)
class EvidenceView:
    context: str; available: tuple[str, ...]; integrity: str; relationship: str
    source: str; started: str; lifecycle_state: str; completed_stages: tuple[str, ...]; next_stage: str; attention: str
    integrity_difference: str; affected_path: str; mutation_action: str; trust_action: str
    journal_reference: str; execution_result: str; final_state: str


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    title: str
    status: str
    timestamp: str
    explanation: str


def _read_json(path: Path, default: object) -> object:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Evidence unavailable: {path.name} is malformed.") from error


def _artifact_value(artifact: object, *path: str, unavailable: str) -> str:
    value = artifact
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return f"Evidence unavailable: {unavailable}"
        value = value[key]
    return str(value) if value not in (None, "") else f"Evidence unavailable: {unavailable}"


def open_evidence(context: str) -> EvidenceView:
    run_id = context.strip()
    if not run_id:
        raise ValueError("A run context is required to open evidence.")
    organization, separator, selected_run = run_id.partition(" / ")
    roots = tuple(sorted({path.parent for path in storage_directory("Workspace").glob(f"{organization}/onboarding-runs/{selected_run}/*" if separator else f"*/onboarding-runs/{run_id}/*")}))
    if not roots:
        raise ValueError("Evidence unavailable for the requested context.")
    if len(roots) != 1:
        raise ValueError("Evidence context is ambiguous; select a specific retained run.")
    run = roots[0]
    context_data = _read_json(run / "context.json", {})
    state_data = _read_json(run / "state.json", {})
    stages_data = _read_json(run / "stages.json", [])
    if not isinstance(context_data, dict) or not isinstance(state_data, dict) or not isinstance(stages_data, list):
        raise ValueError("Evidence context is not a valid retained run.")
    completed = tuple(str(item.get("stage", "activity")).replace("-", " ").title() for item in stages_data if isinstance(item, dict) and item.get("state") == "completed")
    first_stage = stages_data[0] if stages_data and isinstance(stages_data[0], dict) else {}
    difference_artifact = _read_json(run / "integrity-difference.json", {})
    reasoning_artifact = _read_json(run / "mutation-reasoning.json", {})
    action_artifact = _read_json(run / "trust-action.json", {})
    envelope_artifact = _read_json(run / "trust-decision-envelope.json", {})
    receipt_artifact = _read_json(run / "trust-execution-receipt.json", {})
    difference = isinstance(difference_artifact, dict)
    reasoning = isinstance(reasoning_artifact, dict)
    state = str(state_data.get("state", "unknown"))
    attention = "None retained."
    next_stage = "No further stage retained."
    if state == "created" and difference:
        attention = "Integrity difference retained; mutation reasoning is " + ("available." if reasoning else "not retained.")
        next_stage = "No post-integrity stage is retained."
    names = tuple(path.stem.replace("-", " ").title() for path in sorted(run.iterdir()) if path.is_file())
    paths = difference_artifact.get("modified_content_paths", []) if isinstance(difference_artifact, dict) else []
    affected = ", ".join(str(path) for path in paths) if isinstance(paths, list) and paths else "Evidence unavailable: affected path is not retained."
    difference_summary = f"{len(paths)} modified content path(s) retained" if isinstance(paths, list) else "Evidence unavailable: integrity difference is not retained."
    return EvidenceView(
        run_id, names, "Available retained evidence", "Evidence is linked to the selected run.",
        str(context_data.get("repository_path", "Not retained")), str(first_stage.get("operational_timestamp", "Not retained")),
        state.replace("-", " ").title(), completed, next_stage, attention,
        difference_summary, affected,
        _artifact_value(reasoning_artifact, "interpretation", "required_trust_action", unavailable="mutation action is not retained."),
        _artifact_value(action_artifact, "action", "action", unavailable="Trust action is not retained."),
        _artifact_value(envelope_artifact, "journal_record_hash", unavailable="Journal publication reference is not retained."),
        _artifact_value(receipt_artifact, "status", unavailable="execution result is not retained."),
        state.replace("-", " ").title(),
    )


def _run_directory(run_id: str) -> Path:
    organization, separator, selected_run = run_id.partition(" / ")
    roots = tuple(sorted({path.parent for path in storage_directory("Workspace").glob(f"{organization}/onboarding-runs/{selected_run}/*" if separator else f"*/onboarding-runs/{run_id}/*")}))
    if len(roots) != 1:
        raise ValueError("Evidence unavailable: the retained run could not be located.")
    return roots[0]


def render_decision_summary(view: EvidenceView) -> str:
    return "\n".join((
        "Decision", "", "Paused — affected scope", "", "What happened",
        "RIP completed repository observation and integrity verification.",
        "One changed path was retained for review.", "", "Affected path", view.affected_path, "",
        "Why RIP paused", f"The retained mutation reasoning and governed Trust decision selected {view.trust_action}.", "",
        "What this means", "Only the identified scope is paused.",
        "The retained evidence and completed Trust execution remain available.", "", "Next action",
        "Review the retained difference and mutation reasoning before deciding whether the changed path is expected runtime state or requires further investigation.",
    ))


def action_recommendation(view: EvidenceView) -> tuple[str, str]:
    if view.final_state == "Paused Affected Scope":
        return ("Review retained runtime mutation.", "The affected scope remains paused until its retained difference and reasoning are reviewed.")
    return ("Review retained evidence.", "No additional governed action is currently available in this workspace.")


def project_timeline(context: str) -> tuple[TimelineEntry, ...]:
    view = open_evidence(context); run = _run_directory(view.context)
    stages = _read_json(run / "stages.json", [])
    entries: list[TimelineEntry] = []
    if isinstance(stages, list):
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            if stage.get("stage") == "mutation-interpretation":
                continue
            name = str(stage.get("stage", "retained activity")).replace("-", " ").title()
            state = str(stage.get("state", "recorded")).replace("-", " ").title()
            explanation = {"Initial Fingerprint": "Repository observation began from a retained baseline.", "Integrity Verification": "The retained final fingerprint was compared with the baseline.", "Mutation Interpretation": "Retained mutation reasoning selected the governed action."}.get(name, "Retained lifecycle activity.")
            entries.append(TimelineEntry(name, state, str(stage.get("operational_timestamp", "Not retained")), explanation))
    reasoning = _read_json(run / "mutation-reasoning.json", {})
    if isinstance(reasoning, dict) and reasoning.get("timestamp"):
        entries.append(TimelineEntry("Mutation Reasoning", str(_artifact_value(reasoning, "interpretation", "required_trust_action", unavailable="action is not retained.")).replace("-", " ").title(), str(reasoning["timestamp"]), "Retained mutation reasoning selected the governed action."))
    envelope = _read_json(run / "trust-decision-envelope.json", {})
    if isinstance(envelope, dict) and envelope.get("created_at"):
        entries.append(TimelineEntry("Trust Decision", str(envelope.get("trust_action", "recorded")).replace("-", " ").title(), str(envelope["created_at"]), "The governed Trust decision was retained."))
        try:
            record, _ = _journal_record(str(envelope.get("journal_record_hash", "")))
            entries.append(TimelineEntry("Journal Publication", "Committed", str(record.get("published_at", "Not retained")), "Journal Authority committed the Trust decision publication."))
        except ValueError:
            pass
    receipt = _read_json(run / "trust-execution-receipt.json", {})
    if isinstance(receipt, dict) and receipt.get("completed_at"):
        entries.append(TimelineEntry("Paused — affected scope", str(receipt.get("status", "completed")).title(), str(receipt["completed_at"]), "Only the identified runtime scope was paused."))
    return tuple(sorted(entries, key=lambda item: item.timestamp))


def load_notes(context: str) -> tuple[dict[str, object], ...]:
    return _read_json_lines(_run_directory(context.strip()) / "investigation-notes.ndjson")


def append_investigation_note(context: str, text: str, *, author: str | None = None) -> dict[str, object]:
    """Append one immutable, attributed operator note to the selected retained run."""
    message = text.strip()
    if not message:
        raise ValueError("Evidence unavailable: enter an investigation note before recording it.")
    run = _run_directory(context.strip()); path = run / "investigation-notes.ndjson"
    identity = author or os.environ.get("USERNAME") or getpass.getuser()
    note = {"schema": "rip.investigation-note.v1", "note_id": "note-" + uuid.uuid4().hex,
            "recorded_at": datetime.now(timezone.utc).isoformat(), "author": identity, "text": message}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(note, sort_keys=True, separators=(",", ":")) + "\n"); handle.flush(); os.fsync(handle.fileno())
    return note


def render_workspace(view: EvidenceView) -> str:
    action, reason = action_recommendation(view)
    timeline = project_timeline(view.context)
    notes = load_notes(view.context)
    return "\n".join((
        "Operator Workspace", "", "Workspace Header", f"Repository: {view.source}", f"Run: {view.context}",
        f"Current constitutional state: {view.final_state}", f"Current recommendation: {action}", "Confidence: Governed retained evidence", "",
        "Guided Resolution", "",
        "1. What happened?", "Repository paused. Only one runtime-generated area requires review.", "This is not a repository-wide integrity failure.", "",
        "2. Why?", f"Affected path: {view.affected_path}", "This file changed after integrity verification. Only this runtime area was paused.", "",
        "3. Should I be worried?", "Known information", "• Repository remains readable.", "• Only one governed runtime area paused.", "• No repository corruption observed.", "• Trust completed successfully.", "",
        "4. My choices", "Review Changed Runtime Area", "Why is this governed?", "View Technical Evidence", "",
        "5. RIP recommends", action, reason, "The remaining engineering question is whether this changed runtime file is expected state or needs investigation.", "",
        "6. What happens next?", "Workspace review complete when you have reviewed the retained runtime mutation.", "No further operator action is currently available in this workspace.", "",
        "Advanced Evidence", f"Affected path: {view.affected_path}", f"Journal publication reference: {view.journal_reference}", "",
        "Investigation Notes", *((f"• {note.get('recorded_at', 'Not retained')} — {note.get('author', 'Unknown')}: {note.get('text', '')}" for note in notes) if notes else ("No investigation notes retained.",)), "",
        "Activity Timeline", *((f"• {entry.timestamp} — {entry.title} — {entry.status}: {entry.explanation}" for entry in timeline) if timeline else ("Evidence unavailable: no retained timeline activity.",)),
    ))


def _journal_record(record_hash: str) -> tuple[dict[str, object], dict[str, object]]:
    if not record_hash or record_hash.startswith("Evidence unavailable:"):
        raise ValueError("Evidence unavailable: Journal publication reference is not retained.")
    journal = storage_directory("State") / "transaction-journal.ndjson"
    history = storage_directory("State") / "journal-head-history.ndjson"
    records = _read_json_lines(journal)
    heads = _read_json_lines(history)
    record = next((item for item in records if item.get("record_hash") == record_hash), None)
    head = next((item for item in heads if item.get("record_hash") == record_hash), None)
    if record is None or head is None:
        raise ValueError("Evidence unavailable: retained Journal publication is not available.")
    return record, head


def _read_json_lines(path: Path) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        return ()
    try:
        return tuple(item for item in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()) if isinstance(item, dict))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Evidence unavailable: {path.name} is malformed.") from error


def review_evidence(context: str, section: str) -> str:
    """Present one retained evidence category without replaying any authority."""
    view = open_evidence(context)
    run = _run_directory(view.context)
    if section == "difference":
        artifact = _read_json(run / "integrity-difference.json", {})
        if not isinstance(artifact, dict):
            raise ValueError("Evidence unavailable: retained integrity difference is not available.")
        modified = artifact.get("modified_content_paths", [])
        change_type = "Modified content" if isinstance(modified, list) and modified else "Evidence unavailable: change type is not retained."
        return "\n".join(("Retained Difference", "", f"Affected path: {view.affected_path}", f"Change type: {change_type}", f"Initial fingerprint: {artifact.get('initial_fingerprint', 'Evidence unavailable: initial fingerprint is not retained.')}", f"Final fingerprint: {artifact.get('final_fingerprint', 'Evidence unavailable: final fingerprint is not retained.')}", f"Integrity-difference identity: {artifact.get('difference_fingerprint', 'Evidence unavailable: identity is not retained.')}"))
    if section == "reasoning":
        artifact = _read_json(run / "mutation-reasoning.json", {})
        if not isinstance(artifact, dict):
            raise ValueError("Evidence unavailable: retained mutation reasoning is not available.")
        interpretation = artifact.get("interpretation", {})
        policy = artifact.get("governing_policy", {})
        return "\n".join(("Retained Reasoning", "", f"Mutation action: {view.mutation_action}", f"Affected scope: {view.affected_path}", f"Reasoning summary: {interpretation.get('explanation', 'Evidence unavailable: reasoning summary is not retained.') if isinstance(interpretation, dict) else 'Evidence unavailable: reasoning summary is not retained.'}", f"Policy identity: {policy.get('fingerprint', policy.get('policy_identifier', 'Evidence unavailable: policy identity is not retained.')) if isinstance(policy, dict) else 'Evidence unavailable: policy identity is not retained.'}"))
    if section == "trust":
        envelope = _read_json(run / "trust-decision-envelope.json", {})
        return "\n".join(("Trust Decision", "", f"Trust action: {view.trust_action}", f"Decision-envelope identity: {envelope.get('fingerprint', 'Evidence unavailable: decision-envelope identity is not retained.') if isinstance(envelope, dict) else 'Evidence unavailable: decision-envelope identity is not retained.'}", f"Execution result: {view.execution_result}", f"Final lifecycle state: {view.final_state}"))
    if section == "journal":
        record, head = _journal_record(view.journal_reference)
        return "\n".join(("Journal Evidence", "", f"Journal publication reference: {view.journal_reference}", f"Producer identity: {record.get('producer_authority_type', 'Evidence unavailable')} / {record.get('producer_authority_id', 'Evidence unavailable')}", f"Record type: {record.get('producer_record_type', 'Evidence unavailable')}", f"Publication sequence: {record.get('publication_sequence', 'Evidence unavailable')}", f"Commit sequence: {head.get('commit_sequence', 'Evidence unavailable')}", f"Committed record: {head.get('record_hash', 'Evidence unavailable')}"))
    raise ValueError("Evidence unavailable: requested evidence category is not supported.")


def render_evidence(view: EvidenceView) -> str:
    """Render all retained evidence fields without replaying or interpreting them."""
    return "\n".join((
        "Run Detail", "", f"Run ID: {view.context}", f"Source: {view.source}",
        f"Lifecycle state: {view.lifecycle_state}", f"Retained integrity difference: {view.integrity_difference}",
        f"Affected path: {view.affected_path}", f"Mutation action: {view.mutation_action}",
        f"Trust action: {view.trust_action}", f"Journal publication reference: {view.journal_reference}",
        f"Execution result: {view.execution_result}", f"Final state: {view.final_state}", "",
        "Evidence Available", *(f"• {item}" for item in view.available),
    ))
