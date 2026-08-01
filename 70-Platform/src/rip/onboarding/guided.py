"""Deterministic, evidence-backed guided organizational understanding.

This module records supplied answers in an isolated onboarding run.  It neither
loads customer content nor creates governance, organizational memory, approval,
or activation state.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import (
    GuidedAnswerDisposition,
    GuidedAnswerRecord,
    GuidedQuestion,
    GuidedQuestionPriority,
    GuidedQuestionType,
    GuidedUnderstandingState,
    GuidedUnderstandingStatus,
    GuidedUnderstandingSummary,
    ObservationRun,
    UnderstandingState,
    fingerprint,
)
from .service import current_repository_fingerprint


GUIDED_UNDERSTANDING_SCHEMA = "rip.guided-understanding.v1"
_PRIORITY_ORDER = {GuidedQuestionPriority.CRITICAL: 0, GuidedQuestionPriority.HIGH: 1, GuidedQuestionPriority.STANDARD: 2}


def generate_guided_questions(observation: ObservationRun) -> tuple[GuidedQuestion, ...]:
    """Generate only questions justified by Phase 6A evidence uncertainty."""
    candidates: list[GuidedQuestion] = []
    for dimension in observation.understanding_meter.dimensions:
        if dimension.state is UnderstandingState.OBSERVED:
            continue
        if dimension.name == "Authority":
            candidates.append(_question(
                dimension.name, GuidedQuestionType.IDENTIFY_AUTHORITY, GuidedQuestionPriority.CRITICAL,
                "Who is authorized to identify the organization’s current governing authority, and where is it recorded?",
                dimension.explanation,
                "Authority must be identified before later governance work can be proposed.",
                "Whether a current authorized governance source exists and who can confirm it.",
                "The Authority dimension remains supplied knowledge with explicit provenance; it does not become authority.",
                dimension.observation_ids, dimension.evidence_paths,
            ))
        else:
            priority = GuidedQuestionPriority.HIGH if dimension.name in {"Mission", "Products", "Decision History"} else GuidedQuestionPriority.STANDARD
            candidates.append(_question(
                dimension.name, GuidedQuestionType.CONFIRM_INTERPRETATION, priority,
                f"What does the observed {dimension.name.lower()} evidence represent for this organization?",
                dimension.explanation,
                "Observed names and file classifications are evidence signals, not organizational meaning.",
                f"Whether the {dimension.name.lower()} signal is current, historical, draft, or unrelated.",
                f"The {dimension.name} dimension is updated as supplied interpretation only, with its respondent provenance retained.",
                dimension.observation_ids, dimension.evidence_paths,
            ))
    deduplicated = {item.resolution_key: item for item in candidates}
    return tuple(sorted(deduplicated.values(), key=lambda item: (_PRIORITY_ORDER[item.priority], item.dimension.casefold(), item.resolution_key)))


def begin_guided_understanding(observation: ObservationRun) -> GuidedUnderstandingState:
    """Create or resume the run's guided state after verifying source freshness."""
    _verify_fresh(observation)
    path = _state_path(observation)
    if path.exists():
        state = _load_state(path)
        if state.source_fingerprint != observation.repository_fingerprint:
            raise RuntimeError("Observed repository source changed; start a fresh read-only observation run.")
        return state
    questions = generate_guided_questions(observation)
    state = _state(observation, GuidedUnderstandingStatus.ACTIVE, questions, ())
    _write(path, _payload(state))
    return state


def record_guided_answer(
    observation: ObservationRun,
    state: GuidedUnderstandingState,
    *,
    question_id: str,
    respondent_identity: str,
    respondent_role: str,
    authority_claim: str,
    disposition: GuidedAnswerDisposition,
    answer: str = "",
) -> GuidedUnderstandingState:
    """Append a supplied answer; prior records are never replaced or silently rewritten."""
    _verify_fresh(observation)
    if state.status is GuidedUnderstandingStatus.STALE or state.source_fingerprint != observation.repository_fingerprint:
        raise RuntimeError("Guided understanding is stale; start a fresh read-only observation run.")
    question = next((item for item in state.questions if item.question_id == question_id), None)
    if question is None:
        raise ValueError("Guided question is not part of this onboarding run")
    if not respondent_identity.strip() or not authority_claim.strip():
        raise ValueError("Respondent identity and authority claim are required provenance")
    previous = next((item for item in reversed(state.answer_history) if item.question_id == question_id and item.respondent_identity == respondent_identity), None)
    sequence = len(state.answer_history)
    record_payload = {
        "question_id": question_id, "sequence": sequence, "respondent_identity": respondent_identity.strip(),
        "respondent_role": respondent_role.strip(), "authority_claim": authority_claim.strip(),
        "disposition": disposition.value, "answer": answer.strip(), "supersedes_answer_id": previous.answer_id if previous else None,
        "source_fingerprint": state.source_fingerprint,
    }
    record = GuidedAnswerRecord(
        answer_id="answer-" + fingerprint(record_payload)[:16], fingerprint=fingerprint(record_payload),
        **{**record_payload, "disposition": disposition},
    )
    history = (*state.answer_history, record)
    questions = _with_contradiction_questions(state.questions, history)
    updated = _state(observation, GuidedUnderstandingStatus.ACTIVE, questions, history)
    _write(_state_path(observation), _payload(updated))
    return updated


def _question(dimension, question_type, priority, prompt, observed, why, uncertainty, change, observation_ids, evidence_paths):
    key = f"{dimension.casefold()}:{question_type.value}"
    fingerprint_payload = {"dimension": dimension, "question_type": question_type.value, "priority": priority.value, "prompt": prompt, "observed": observed, "why_this_question": why, "uncertainty_resolved": uncertainty, "understanding_change": change, "observation_ids": observation_ids, "evidence_paths": evidence_paths, "resolution_key": key}
    values = {**fingerprint_payload, "question_type": question_type, "priority": priority}
    return GuidedQuestion("question-" + fingerprint(fingerprint_payload)[:16], fingerprint=fingerprint(fingerprint_payload), **values)


def _state(observation, status, questions, answers):
    summary = _summary(questions, answers)
    payload = {"organization_id": observation.context.organization_id, "onboarding_run_id": observation.context.onboarding_run_id, "source_fingerprint": observation.repository_fingerprint, "status": status.value, "questions": questions, "answer_history": answers, "summary": summary}
    return GuidedUnderstandingState(fingerprint=fingerprint(_payload(payload)), **payload)


def _summary(questions, answers):
    effective = _effective_answers(answers)
    answered_ids = {item.question_id for item in effective if item.disposition is GuidedAnswerDisposition.ANSWERED}
    authority = [item for item in questions if item.question_type is GuidedQuestionType.IDENTIFY_AUTHORITY]
    authority_gaps = sum(1 for item in authority if item.question_id not in answered_ids)
    contradictions = sum(1 for question in questions if len({item.answer.casefold() for item in effective if item.question_id == question.question_id and item.disposition is GuidedAnswerDisposition.ANSWERED}) > 1)
    unresolved = len(questions) - len(answered_ids)
    readiness = "not-ready" if authority_gaps or contradictions else ("ready-for-review" if not unresolved else "needs-supplied-knowledge")
    base = {"total_questions": len(questions), "answered_questions": len(answered_ids), "unresolved_questions": unresolved, "authority_gaps": authority_gaps, "contradictions": contradictions, "readiness": readiness}
    return GuidedUnderstandingSummary(fingerprint=fingerprint(base), **base)


def _with_contradiction_questions(questions, answers):
    """Expose conflicting supplied knowledge as a new explicit uncertainty, never as a decision."""
    by_id = {item.question_id: item for item in questions}
    additions = []
    for question_id, original in tuple(by_id.items()):
        values = sorted({item.answer.casefold() for item in _effective_answers(answers) if item.question_id == question_id and item.disposition is GuidedAnswerDisposition.ANSWERED})
        if len(values) < 2:
            continue
        key = original.resolution_key + ":contradiction:" + fingerprint(values)[:12]
        if any(item.resolution_key == key for item in questions):
            continue
        base = _question(
            original.dimension, GuidedQuestionType.RESOLVE_CONTRADICTION, GuidedQuestionPriority.CRITICAL,
            f"Conflicting supplied answers exist for {original.dimension}. Which supplied interpretation should be retained for review?",
            "Multiple respondents supplied different answers to the same evidence-backed question.",
            "RIP must preserve and expose the conflict instead of silently choosing an answer.",
            "Which supplied interpretation remains unresolved and needs an authorized organizational review.",
            "The conflict remains explicit; no supplied answer becomes governance or authority.",
            original.observation_ids, original.evidence_paths,
        )
        additions.append(GuidedQuestion(**{**asdict(base), "resolution_key": key, "question_id": "question-" + fingerprint(key)[:16], "fingerprint": fingerprint({"base": asdict(base), "key": key})}))
    return tuple(sorted((*questions, *additions), key=lambda item: (_PRIORITY_ORDER[item.priority], item.dimension.casefold(), item.resolution_key)))


def _effective_answers(answers):
    latest = {}
    for answer in answers:
        latest[(answer.question_id, answer.respondent_identity)] = answer
    return tuple(latest.values())


def _verify_fresh(observation):
    if current_repository_fingerprint(observation.context) != observation.repository_fingerprint:
        raise RuntimeError("Observed repository source changed; start a fresh read-only observation run.")


def _state_path(observation):
    return Path(observation.context.workspace_path) / "onboarding-runs" / observation.context.onboarding_run_id / "guided-understanding.json"


def _payload(value):
    if isinstance(value, tuple): return [_payload(item) for item in value]
    if hasattr(value, "__dataclass_fields__"): return _payload(asdict(value))
    if isinstance(value, dict): return {key: _payload(item) for key, item in value.items()}
    if hasattr(value, "value"): return value.value
    return value


def _write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"schema": GUIDED_UNDERSTANDING_SCHEMA, "state": value}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _load_state(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != GUIDED_UNDERSTANDING_SCHEMA: raise ValueError("Guided understanding state schema is not supported")
    item = data["state"]
    questions = tuple(GuidedQuestion(question_type=GuidedQuestionType(row["question_type"]), priority=GuidedQuestionPriority(row["priority"]), observation_ids=tuple(row["observation_ids"]), evidence_paths=tuple(row["evidence_paths"]), **{key: row[key] for key in ("question_id", "dimension", "prompt", "observed", "why_this_question", "uncertainty_resolved", "understanding_change", "resolution_key", "fingerprint")}) for row in item["questions"])
    answers = tuple(GuidedAnswerRecord(disposition=GuidedAnswerDisposition(row["disposition"]), **{key: row[key] for key in ("answer_id", "question_id", "sequence", "respondent_identity", "respondent_role", "authority_claim", "answer", "supersedes_answer_id", "source_fingerprint", "fingerprint")}) for row in item["answer_history"])
    summary_row = item["summary"]
    summary = GuidedUnderstandingSummary(**summary_row)
    return GuidedUnderstandingState(organization_id=item["organization_id"], onboarding_run_id=item["onboarding_run_id"], source_fingerprint=item["source_fingerprint"], status=GuidedUnderstandingStatus(item["status"]), questions=questions, answer_history=answers, summary=summary, fingerprint=item["fingerprint"])
