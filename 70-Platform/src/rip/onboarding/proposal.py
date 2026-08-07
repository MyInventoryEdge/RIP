"""Deterministic, non-authoritative organizational understanding proposals."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from ..paths import onboarding_run_directory

from .models import (
    ConfirmedInterpretation, EpistemicLabel, GuidedAnswerDisposition, GuidedUnderstandingState,
    ObservationRun, OrganizationalUnderstandingProposal, OrganizationalUnderstandingSection,
    ProposalReadiness, ProposalStatus, ProposedStatementType, ProposedUnderstandingStatement,
    StatementProvenance, WithdrawalRecord, fingerprint,
)
from .service import current_repository_fingerprint


PROPOSAL_SCHEMA = "rip.organizational-understanding-proposal.v1"
SECTION_ORDER = (
    "Organization Identity", "Mission", "Products and Services", "Repository Landscape",
    "Organizational Authority", "Governance Sources", "Architecture Overview", "Decision Ownership",
    "Active vs Historical Assets", "Outstanding Unknowns", "Outstanding Contradictions", "Readiness Assessment",
)
_DIMENSION_SECTION = {"Mission": "Mission", "Products": "Products and Services", "Architecture": "Architecture Overview", "Authority": "Organizational Authority", "Decision History": "Decision Ownership", "Repositories": "Repository Landscape"}


def confirm_interpretation(observation: ObservationRun, state: GuidedUnderstandingState, *, question_id: str, answer_ids: tuple[str, ...], statement_text: str, authority_category: str, authority_accepted: bool) -> ConfirmedInterpretation:
    """Create a non-authoritative confirmation only from fresh, non-conflicting supplied evidence."""
    _assert_fresh(observation, state)
    question = next((item for item in state.questions if item.question_id == question_id), None)
    answers = tuple(item for item in state.answer_history if item.answer_id in answer_ids and item.question_id == question_id and item.disposition is GuidedAnswerDisposition.ANSWERED)
    if question is None or len(answers) != len(answer_ids) or not statement_text.strip() or not authority_category.strip() or not authority_accepted:
        raise ValueError("confirmed interpretations require current question, answered evidence, and accepted authority category")
    if state.summary.contradictions:
        raise ValueError("confirmed interpretations cannot be created while a material contradiction remains")
    effective = {item.answer_id for item in _effective_answers(state, set())}
    if any(item.answer_id not in effective for item in answers):
        raise ValueError("confirmed interpretations require effective current answers")
    payload = {"organization_id": state.organization_id, "onboarding_run_id": state.onboarding_run_id, "question_id": question_id, "answer_ids": tuple(sorted(answer_ids)), "observation_ids": question.observation_ids, "statement_text": statement_text.strip(), "authority_category": authority_category.strip(), "source_fingerprint": state.source_fingerprint, "question_fingerprint": question.fingerprint, "answer_fingerprints": tuple(sorted(item.fingerprint for item in answers))}
    return ConfirmedInterpretation("interpretation-" + fingerprint(payload)[:16], fingerprint=fingerprint(payload), **payload)


def withdraw_record(*, organization_id: str, onboarding_run_id: str, target_id: str, target_type: str, respondent_identity: str, reason: str, source_fingerprint: str) -> WithdrawalRecord:
    """Record a withdrawal without deleting or mutating its historical target."""
    payload = {"organization_id": organization_id, "onboarding_run_id": onboarding_run_id, "target_id": target_id, "target_type": target_type, "respondent_identity": respondent_identity.strip(), "reason": reason.strip(), "source_fingerprint": source_fingerprint}
    if not all(payload.values()):
        raise ValueError("withdrawal records require target, respondent, reason, and source provenance")
    return WithdrawalRecord("withdrawal-" + fingerprint(payload)[:16], fingerprint=fingerprint(payload), **payload)


def generate_understanding_proposal(observation: ObservationRun, state: GuidedUnderstandingState, *, confirmed_interpretations: tuple[ConfirmedInterpretation, ...] = (), withdrawals: tuple[WithdrawalRecord, ...] = (), generated_at: str | None = None) -> OrganizationalUnderstandingProposal:
    """Generate and persist one inspectable proposal; no provider or customer-source write occurs."""
    _assert_fresh(observation, state)
    _validate_withdrawals(observation, state, confirmed_interpretations, withdrawals)
    withdrawn = {item.target_id for item in withdrawals}
    effective = _effective_answers(state, withdrawn)
    interpretations = tuple(_validate_interpretation(observation, state, item, withdrawn) for item in confirmed_interpretations if item.interpretation_id not in withdrawn)
    root_observation_id = next(item for item in observation.understanding_meter.dimensions if item.name == "Repositories").observation_ids[0]
    statements = [_statement("Repository Landscape", "repository-scope", f"Repository observation completed with {len(observation.discovery_feed)} recorded onboarding events.", ProposedStatementType.DIRECT_OBSERVATION, EpistemicLabel.DIRECTLY_OBSERVED, observation_ids=(root_observation_id,), rules=("phase6a-observation",))]
    for answer in effective:
        question = next(item for item in state.questions if item.question_id == answer.question_id)
        section = _DIMENSION_SECTION.get(question.dimension)
        if section:
            statements.append(_statement(section, question.dimension.casefold(), answer.answer, ProposedStatementType.SUPPLIED_KNOWLEDGE, EpistemicLabel.SUPPLIED_BY_CUSTOMER, observation_ids=question.observation_ids, answer_ids=(answer.answer_id,), rules=("effective-supplied-answer",)))
    for item in interpretations:
        question = next(question for question in state.questions if question.question_id == item.question_id)
        section = _DIMENSION_SECTION.get(question.dimension, "Organization Identity")
        statements.append(_statement(section, question.dimension.casefold(), item.statement_text, ProposedStatementType.CONFIRMED_INTERPRETATION, EpistemicLabel.CONFIRMED_INTERPRETATION, observation_ids=item.observation_ids, answer_ids=item.answer_ids, interpretation_ids=(item.interpretation_id,), rules=("confirmed-interpretation",)))
    answered = {item.question_id for item in effective}
    unknown = tuple(item.question_id for item in state.questions if item.question_id not in answered)
    for question_id in unknown:
        question = next(item for item in state.questions if item.question_id == question_id)
        statements.append(_statement("Outstanding Unknowns", question.dimension.casefold(), question.uncertainty_resolved, ProposedStatementType.OUTSTANDING_UNKNOWN, EpistemicLabel.UNRESOLVED, observation_ids=question.observation_ids, uncertainty_ids=(question_id,), rules=("unanswered-guided-question",)))
    contradictions = tuple(item.question_id for item in state.questions if item.question_type.value == "resolve-contradiction" and item.question_id not in answered)
    for question_id in contradictions:
        question = next(item for item in state.questions if item.question_id == question_id)
        statements.append(_statement("Outstanding Contradictions", question.dimension.casefold(), question.observed, ProposedStatementType.OUTSTANDING_CONTRADICTION, EpistemicLabel.CONTRADICTED, observation_ids=question.observation_ids, contradiction_ids=(question_id,), rules=("guided-contradiction",)))
    confirmed_questions = {item.question_id for item in interpretations}
    authority = tuple(item.question_id for item in state.questions if item.dimension == "Authority" and item.question_id not in confirmed_questions)
    for question_id in authority:
        question = next(item for item in state.questions if item.question_id == question_id)
        statements.append(_statement("Organizational Authority", "authority", question.uncertainty_resolved, ProposedStatementType.AUTHORITY_GAP, EpistemicLabel.AUTHORITY_NOT_ESTABLISHED, observation_ids=question.observation_ids, uncertainty_ids=(question_id,), rules=("authority-gap",)))
    readiness, reasons, blockers = _readiness(unknown, contradictions, authority, effective, interpretations)
    statements.append(_statement("Readiness Assessment", "readiness", "; ".join(reasons), ProposedStatementType.READINESS_ASSESSMENT, EpistemicLabel.UNRESOLVED if blockers else EpistemicLabel.CONFIRMED_INTERPRETATION, observation_ids=(root_observation_id,), uncertainty_ids=blockers, rules=("phase6c-readiness",)))
    sections = _sections(statements)
    semantic = {"organization_id": observation.context.organization_id, "onboarding_run_id": observation.context.onboarding_run_id, "source_snapshot_fingerprint": observation.repository_fingerprint, "sections": sections, "unresolved": unknown, "contradictions": contradictions, "authority": authority, "answers": tuple(item.answer_id for item in effective), "interpretations": tuple(item.interpretation_id for item in interpretations), "readiness": readiness.value, "reasons": reasons, "blockers": blockers}
    proposal_fingerprint = fingerprint(_payload(semantic))
    proposal = OrganizationalUnderstandingProposal("proposal-" + proposal_fingerprint[:16], observation.context.organization_id, observation.context.onboarding_run_id, observation.repository_fingerprint, proposal_fingerprint, 0, generated_at, ProposalStatus.GENERATED, sections, unknown, contradictions, authority, tuple(sorted({identifier for _, item in statements for identifier in item.provenance.observation_ids})), tuple(item.answer_id for item in effective), tuple(item.interpretation_id for item in interpretations), ("phase6c-deterministic-proposal",), readiness, reasons, blockers)
    _persist(observation, proposal, interpretations, withdrawals)
    return proposal


def mark_proposal_reviewed(proposal: OrganizationalUnderstandingProposal) -> OrganizationalUnderstandingProposal:
    """Review is a visible lifecycle mark only; it never means approval."""
    return replace(proposal, proposal_status=ProposalStatus.REVIEWED)


def review_understanding_proposal(observation: ObservationRun, proposal: OrganizationalUnderstandingProposal) -> OrganizationalUnderstandingProposal:
    reviewed = mark_proposal_reviewed(proposal)
    _persist(observation, reviewed, (), (), lifecycle_event="reviewed")
    return reviewed


def _effective_answers(state, withdrawn):
    latest = {}
    for answer in state.answer_history:
        if answer.answer_id not in withdrawn and answer.disposition is GuidedAnswerDisposition.ANSWERED:
            latest[(answer.question_id, answer.respondent_identity)] = answer
    return tuple(sorted(latest.values(), key=lambda item: item.answer_id))


def _validate_interpretation(observation, state, item, withdrawn):
    if item.organization_id != state.organization_id or item.onboarding_run_id != state.onboarding_run_id or item.source_fingerprint != state.source_fingerprint:
        raise ValueError("confirmed interpretation identity or source snapshot is invalid")
    question = next((value for value in state.questions if value.question_id == item.question_id), None)
    if question is None or question.fingerprint != item.question_fingerprint:
        raise ValueError("confirmed interpretation question provenance is invalid")
    answers = {value.answer_id: value for value in state.answer_history}
    effective = {value.answer_id: value for value in _effective_answers(state, withdrawn)}
    if not item.answer_ids or tuple(sorted(item.answer_ids)) != item.answer_ids or any(answer_id not in effective for answer_id in item.answer_ids):
        raise ValueError("confirmed interpretation references non-effective answers")
    if any(answers[answer_id].question_id != item.question_id for answer_id in item.answer_ids) or tuple(sorted(answers[answer_id].fingerprint for answer_id in item.answer_ids)) != item.answer_fingerprints:
        raise ValueError("confirmed interpretation answer provenance is invalid")
    if state.summary.contradictions or not item.authority_category.strip():
        raise ValueError("confirmed interpretation has unresolved contradiction or authority gap")
    payload = {"organization_id": item.organization_id, "onboarding_run_id": item.onboarding_run_id, "question_id": item.question_id, "answer_ids": item.answer_ids, "observation_ids": item.observation_ids, "statement_text": item.statement_text, "authority_category": item.authority_category, "source_fingerprint": item.source_fingerprint, "question_fingerprint": item.question_fingerprint, "answer_fingerprints": item.answer_fingerprints}
    if item.fingerprint != fingerprint(payload) or item.interpretation_id != "interpretation-" + item.fingerprint[:16]:
        raise ValueError("confirmed interpretation fingerprint is invalid")
    return item


def _validate_withdrawals(observation, state, interpretations, withdrawals):
    answers = {item.answer_id for item in state.answer_history}
    known_interpretations = {item.interpretation_id for item in interpretations}
    seen = set()
    for item in withdrawals:
        payload = {"organization_id": item.organization_id, "onboarding_run_id": item.onboarding_run_id, "target_id": item.target_id, "target_type": item.target_type, "respondent_identity": item.respondent_identity, "reason": item.reason, "source_fingerprint": item.source_fingerprint}
        if item.organization_id != state.organization_id or item.onboarding_run_id != state.onboarding_run_id or item.source_fingerprint != state.source_fingerprint or item.fingerprint != fingerprint(payload) or item.withdrawal_id != "withdrawal-" + item.fingerprint[:16]:
            raise ValueError("withdrawal provenance is invalid")
        if item.target_type not in {"answer", "interpretation"} or (item.target_type == "answer" and item.target_id not in answers) or (item.target_type == "interpretation" and item.target_id not in known_interpretations) or item.target_id in seen:
            raise ValueError("withdrawal target is invalid or duplicated")
        seen.add(item.target_id)


def _statement(section, subject, text, statement_type, label, *, observation_ids=(), answer_ids=(), interpretation_ids=(), uncertainty_ids=(), contradiction_ids=(), rules=()):
    provenance_payload = {"observation_ids": tuple(sorted(observation_ids)), "answer_ids": tuple(sorted(answer_ids)), "interpretation_ids": tuple(sorted(interpretation_ids)), "uncertainty_ids": tuple(sorted(uncertainty_ids)), "contradiction_ids": tuple(sorted(contradiction_ids)), "derivation_rules": tuple(sorted(rules))}
    provenance = StatementProvenance(fingerprint=fingerprint(provenance_payload), **provenance_payload)
    payload = {"section": section, "subject": subject, "text": text, "type": statement_type.value, "label": label.value, "provenance": provenance.fingerprint}
    return (section, ProposedUnderstandingStatement("statement-" + fingerprint(payload)[:16], text, statement_type, label, subject, provenance, provenance.fingerprint))


def _sections(statements):
    result = []
    for order, title in enumerate(SECTION_ORDER):
        items = tuple(sorted((item for section, item in statements if section == title), key=lambda item: (item.epistemic_label.value, item.normalized_subject, item.provenance_fingerprint, item.statement_id)))
        if items:
            result.append(OrganizationalUnderstandingSection("section-" + fingerprint(_payload({"title": title, "statements": items}))[:16], title, order, items))
    return tuple(result)


def _readiness(unknown, contradictions, authority, effective, interpretations):
    blockers = tuple(sorted((*authority, *contradictions)))
    if blockers: return ProposalReadiness.HUMAN_REVIEW_REQUIRED, ("Human review is required because authority or contradiction blockers remain visible.",), blockers
    if unknown: return ProposalReadiness.PRELIMINARY, ("Evidence-backed understanding is preliminary because guided uncertainty remains.",), tuple(sorted(unknown))
    if effective and interpretations: return ProposalReadiness.GOVERNANCE_DRAFT_READY, ("Evidence and required confirmed interpretations are current and provenance-backed; this is not governance.",), ()
    if effective: return ProposalReadiness.EVIDENCE_COMPLETE, ("Available observation and supplied knowledge are represented with provenance; organizational meaning is not yet confirmed.",), ()
    return ProposalReadiness.PRELIMINARY, ("Insufficient supported evidence exists beyond repository observation.",), ("insufficient-supported-evidence",)


def _assert_fresh(observation, state):
    if observation.context.organization_id != state.organization_id or observation.context.onboarding_run_id != state.onboarding_run_id or current_repository_fingerprint(observation.context) != observation.repository_fingerprint or state.source_fingerprint != observation.repository_fingerprint:
        raise RuntimeError("Onboarding source snapshot is stale or inconsistent; start a fresh read-only observation run.")


def _persist(observation, proposal, interpretations, withdrawals, lifecycle_event="generated"):
    root = onboarding_run_directory(observation.context.workspace_path, observation.context.onboarding_run_id) / "proposals"
    root.mkdir(exist_ok=True)
    suffix = ".json" if lifecycle_event == "generated" else "." + lifecycle_event + ".json"
    path = root / (proposal.proposal_id + suffix)
    payload = {"schema": PROPOSAL_SCHEMA, "proposal": _payload(proposal), "confirmed_interpretations": _payload(interpretations), "withdrawals": _payload(withdrawals), "lifecycle_event": lifecycle_event}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _payload(value):
    if isinstance(value, tuple): return [_payload(item) for item in value]
    if hasattr(value, "__dataclass_fields__"): return _payload(asdict(value))
    if isinstance(value, dict): return {key: _payload(item) for key, item in value.items()}
    if hasattr(value, "value"): return value.value
    return value
