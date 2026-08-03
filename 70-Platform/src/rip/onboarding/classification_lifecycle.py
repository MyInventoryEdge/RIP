"""Safe onboarding pause and resume boundary for evidence classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .classification import (
    ClassificationRequest,
    ClassificationDecision,
    ClassificationRequestStatus,
    ClassificationScope,
    EvidenceClass,
    EvidenceClassificationPolicy,
    IntegrityTreatment,
    _to_json,
    create_classification_request,
    persist_contract,
)
from .classification_engine import ClassificationEvaluation, evaluate_classification_policy
from .models import OnboardingRunState, OrganizationContext, fingerprint
from .service import ONBOARDING_SCHEMA, _read_json, _source_manifest, _write_json


CLASSIFICATION_LIFECYCLE_SCHEMA = "rip.evidence-classification-lifecycle.v1"
ATTENTION_EVENT_SCHEMA = "rip.evidence-classification-attention-event.v1"


class ClassificationReadiness(str, Enum):
    READY = "ready"
    AWAITING_CLASSIFICATION = "awaiting-classification"
    CONFLICTED = "conflicted"


@dataclass(frozen=True, slots=True)
class AttentionEvent:
    event_id: str
    organization_id: str
    onboarding_run_id: str
    event_type: str
    request_id: str
    source_manifest_fingerprint: str
    message: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ClassificationRecoveryState:
    organization_id: str
    onboarding_run_id: str
    state: OnboardingRunState
    source_manifest_fingerprint: str
    request_ids: tuple[str, ...]
    readiness: ClassificationReadiness
    evaluation_fingerprint: str | None
    fingerprint: str


def request_evidence_classification(
    context: OrganizationContext,
    *,
    target: str,
    scope: ClassificationScope,
    proposed_evidence_class: EvidenceClass,
    proposed_integrity_treatment: IntegrityTreatment,
    requester_identity: str,
    requester_role: str,
    authority_claim: str,
    rationale: str,
    created_at: str | None = None,
) -> ClassificationRequest:
    """Persist one immutable request and safely pause an already observed run."""
    workspace, run_root, final_manifest = _completed_run(context)
    source_fingerprint = str(final_manifest["manifest_fingerprint"])
    request_seed = {"organization_id": context.organization_id, "onboarding_run_id": context.onboarding_run_id, "source_manifest_fingerprint": source_fingerprint, "target": target, "scope": scope.value, "proposed_evidence_class": proposed_evidence_class.value, "proposed_integrity_treatment": proposed_integrity_treatment.value, "requester_identity": requester_identity, "authority_claim": authority_claim, "rationale": rationale}
    request = create_classification_request(
        request_id="classification-" + fingerprint(request_seed)[:24],
        organization_id=context.organization_id,
        onboarding_run_id=context.onboarding_run_id,
        source_manifest_fingerprint=source_fingerprint,
        target=target,
        scope=scope,
        proposed_evidence_class=proposed_evidence_class,
        proposed_integrity_treatment=proposed_integrity_treatment,
        requester_identity=requester_identity,
        requester_role=requester_role,
        authority_claim=authority_claim,
        rationale=rationale,
        created_at=created_at,
    )
    persist_contract(workspace, request)
    existing = _load_recovery(run_root, source_fingerprint)
    request_ids = tuple(sorted({*existing.request_ids, request.request_id}))
    recovery = _recovery(context, source_fingerprint, request_ids, ClassificationReadiness.AWAITING_CLASSIFICATION, None)
    _write_json(run_root / "classification-recovery.json", _json(recovery))
    _write_json(run_root / "state.json", {"schema": ONBOARDING_SCHEMA, "state": OnboardingRunState.AWAITING_CLASSIFICATION.value})
    _append_attention(workspace, AttentionEvent(
        event_id="attention-" + request.fingerprint[:24], organization_id=context.organization_id,
        onboarding_run_id=context.onboarding_run_id, event_type="classification-required",
        request_id=request.request_id, source_manifest_fingerprint=source_fingerprint,
        message="Human evidence classification is required before this onboarding run can resume.",
        fingerprint=fingerprint({"request": request.fingerprint, "type": "classification-required"}),
    ))
    return request


def evaluate_classification_readiness(context: OrganizationContext, policy: EvidenceClassificationPolicy) -> tuple[ClassificationReadiness, ClassificationEvaluation]:
    """Evaluate only the preserved final manifest; no source or lifecycle mutation occurs."""
    _, run_root, final_manifest = _completed_run(context, allow_awaiting=True)
    evaluation = evaluate_classification_policy(final_manifest, policy)
    readiness = ClassificationReadiness.CONFLICTED if evaluation.conflicts else (ClassificationReadiness.AWAITING_CLASSIFICATION if evaluation.summary.unknown_entries else ClassificationReadiness.READY)
    return readiness, evaluation


def resume_after_classification(context: OrganizationContext, policy: EvidenceClassificationPolicy, *, decisions: tuple[ClassificationDecision, ...]) -> ClassificationRecoveryState:
    """Reverify the complete source, then record evaluation; no checkpoint is continued unsafely."""
    workspace, run_root, final_manifest = _completed_run(context, allow_awaiting=True)
    if _read_json(run_root / "state.json").get("state") != OnboardingRunState.AWAITING_CLASSIFICATION.value:
        raise ValueError("onboarding run is not awaiting classification")
    current = _source_manifest(Path(context.repository_path).resolve())
    if current["manifest_fingerprint"] != final_manifest["manifest_fingerprint"]:
        _write_json(run_root / "resume-integrity-difference.json", {"expected_manifest_fingerprint": final_manifest["manifest_fingerprint"], "actual_manifest_fingerprint": current["manifest_fingerprint"]})
        _write_json(run_root / "state.json", {"schema": ONBOARDING_SCHEMA, "state": OnboardingRunState.INTERRUPTED.value})
        raise RuntimeError("Source changed before classification resume; preserved onboarding work was not continued.")
    _validate_approved_decisions(context, policy, decisions)
    readiness, evaluation = evaluate_classification_readiness(context, policy)
    _write_json(run_root / "classification-evaluation.json", _json(evaluation))
    existing = _load_recovery(run_root, str(final_manifest["manifest_fingerprint"]))
    recovery = _recovery(context, str(final_manifest["manifest_fingerprint"]), existing.request_ids, readiness, evaluation.fingerprint)
    _write_json(run_root / "classification-recovery.json", _json(recovery))
    if readiness is ClassificationReadiness.READY:
        _write_json(run_root / "state.json", {"schema": ONBOARDING_SCHEMA, "state": OnboardingRunState.OBSERVED.value})
    return recovery


def _validate_approved_decisions(context: OrganizationContext, policy: EvidenceClassificationPolicy, decisions: tuple[ClassificationDecision, ...]) -> None:
    indexed = {item.decision_id: item for item in decisions}
    for record in policy.classifications:
        decision = indexed.get(record.decision_id)
        if decision is None or decision.fingerprint != record.decision_fingerprint:
            raise ValueError("classification policy record lacks its approved immutable decision")
        if decision.status is not ClassificationRequestStatus.APPROVED or decision.organization_id != context.organization_id or decision.onboarding_run_id != context.onboarding_run_id:
            raise ValueError("classification policy record decision is not approved for this onboarding run")
        if decision.decided_evidence_class is not record.evidence_class or decision.decided_integrity_treatment is not record.integrity_treatment:
            raise ValueError("approved classification decision does not match its policy record")


def _completed_run(context: OrganizationContext, *, allow_awaiting: bool = False) -> tuple[Path, Path, dict[str, object]]:
    workspace = Path(context.workspace_path).resolve()
    run_root = workspace / "onboarding-runs" / context.onboarding_run_id
    state = _read_json(run_root / "state.json").get("state")
    allowed = {OnboardingRunState.OBSERVED.value}
    if allow_awaiting:
        allowed.add(OnboardingRunState.AWAITING_CLASSIFICATION.value)
    if state not in allowed or not (run_root / "observation.json").is_file() or not (run_root / "final-source-manifest.json").is_file():
        raise ValueError("classification lifecycle requires a completed preserved observation")
    return workspace, run_root, _read_json(run_root / "final-source-manifest.json")


def _load_recovery(run_root: Path, source_fingerprint: str) -> ClassificationRecoveryState:
    path = run_root / "classification-recovery.json"
    if not path.exists():
        return _recovery_from_values("", run_root.name, source_fingerprint, (), ClassificationReadiness.AWAITING_CLASSIFICATION, None)
    raw = _read_json(path)
    return _recovery_from_values(str(raw["organization_id"]), str(raw["onboarding_run_id"]), str(raw["source_manifest_fingerprint"]), tuple(raw["request_ids"]), ClassificationReadiness(raw["readiness"]), raw.get("evaluation_fingerprint"))


def _recovery(context: OrganizationContext, source_fingerprint: str, request_ids: tuple[str, ...], readiness: ClassificationReadiness, evaluation_fingerprint: str | None) -> ClassificationRecoveryState:
    return _recovery_from_values(context.organization_id, context.onboarding_run_id, source_fingerprint, request_ids, readiness, evaluation_fingerprint)


def _recovery_from_values(organization_id: str, run_id: str, source_fingerprint: str, request_ids: tuple[str, ...], readiness: ClassificationReadiness, evaluation_fingerprint: str | None) -> ClassificationRecoveryState:
    state = OnboardingRunState.OBSERVED if readiness is ClassificationReadiness.READY else OnboardingRunState.AWAITING_CLASSIFICATION
    payload = {"organization_id": organization_id, "onboarding_run_id": run_id, "state": state.value, "source_manifest_fingerprint": source_fingerprint, "request_ids": request_ids, "readiness": readiness.value, "evaluation_fingerprint": evaluation_fingerprint}
    return ClassificationRecoveryState(organization_id, run_id, state, source_fingerprint, request_ids, readiness, evaluation_fingerprint, fingerprint(payload))


def _append_attention(workspace: Path, event: AttentionEvent) -> None:
    path = workspace / "attention-events.json"
    existing = _read_json(path) if path.exists() else []
    payload = _json(event)
    if not any(item.get("event_id") == event.event_id for item in existing):
        _write_json(path, [*existing, payload])


def _json(value: object) -> dict[str, object]:
    return _to_json(asdict(value))
