"""Read-only-from-customer integration of persisted immutable classifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from .classification import (
    ClassificationDecision,
    ClassificationRequest,
    ClassificationRequestStatus,
    ClassificationScope,
    EvidenceClass,
    EvidenceClassification,
    EvidenceClassificationPolicy,
    IntegrityTreatment,
    create_classification_decision,
    create_classification_policy,
    create_classification_request,
    create_evidence_classification,
    load_contract_payload,
    persist_contract,
)
from .classification_engine import ClassificationEvaluation, evaluate_classification_policy
from .classification_lifecycle import ClassificationReadiness
from .models import fingerprint
from .policy_history import PolicyReconstruction, reconstruct_policy_history


INTEGRATION_SCHEMA = "rip.evidence-classification-integration.v1"
_T = TypeVar("_T", ClassificationRequest, ClassificationDecision, EvidenceClassification, EvidenceClassificationPolicy)


@dataclass(frozen=True, slots=True)
class ClassificationIntegrationResult:
    organization_id: str
    onboarding_run_id: str
    source_manifest_fingerprint: str
    readiness: ClassificationReadiness
    request_ids: tuple[str, ...]
    unresolved_request_ids: tuple[str, ...]
    decision_ids: tuple[str, ...]
    record_ids: tuple[str, ...]
    policy_history: PolicyReconstruction
    evaluation: ClassificationEvaluation | None
    fingerprint: str


def integrate_persisted_classifications(*, workspace: str | Path, onboarding_run_id: str) -> ClassificationIntegrationResult:
    """Integrate only retained immutable artifacts; never resume or verify customer sources."""
    root = Path(workspace)
    workspace_manifest = _read_object(root / "workspace.json", "workspace")
    organization_id = _string(workspace_manifest, "organization_id", "workspace")
    run_root = root / "onboarding-runs" / onboarding_run_id
    context = _read_object(run_root / "context.json", "onboarding run")
    if context.get("organization_id") != organization_id or context.get("onboarding_run_id") != onboarding_run_id:
        raise ValueError("retained onboarding run does not match workspace")
    manifest = _read_object(run_root / "final-source-manifest.json", "retained manifest")
    source_fingerprint = _string(manifest, "manifest_fingerprint", "retained manifest")
    recovery = _read_object(run_root / "classification-recovery.json", "classification recovery") if (run_root / "classification-recovery.json").is_file() else {}
    retained_source_is_stale = bool(recovery) and recovery.get("source_manifest_fingerprint") != source_fingerprint
    requests = _load_typed(root, onboarding_run_id, "requests", ClassificationRequest)
    decisions = _load_typed(root, onboarding_run_id, "decisions", ClassificationDecision)
    records = _load_typed(root, onboarding_run_id, "records", EvidenceClassification)
    policies = _load_typed(root, onboarding_run_id, "policies", EvidenceClassificationPolicy)
    _validate_scope(organization_id, onboarding_run_id, source_fingerprint, requests, decisions, records, policies)

    reconstruction = reconstruct_policy_history(
        organization_id=organization_id,
        onboarding_run_id=onboarding_run_id,
        source_manifest_fingerprint=source_fingerprint,
        records=tuple(records),
    )
    decision_by_id = {item.decision_id: item for item in decisions}
    _validate_record_decisions(records, decision_by_id)
    unresolved = tuple(sorted(item.request_id for item in requests if not _is_approved(item, decisions)))
    readiness, evaluation = _evaluate_readiness(manifest, reconstruction, unresolved, policies, source_fingerprint, retained_source_is_stale)
    if reconstruction.policy is not None:
        persist_contract(root, reconstruction.policy)
    result = _result(organization_id, onboarding_run_id, source_fingerprint, requests, decisions, records, reconstruction, unresolved, readiness, evaluation)
    _write_summary(run_root / "classification-integration.json", result)
    return result


def _load_typed(root: Path, run_id: str, kind: str, contract_type: type[_T]) -> tuple[_T, ...]:
    directory = root / "onboarding-runs" / run_id / "classifications" / kind
    if not directory.is_dir():
        return ()
    loaded: list[_T] = []
    for path in sorted(directory.glob("*.json")):
        payload = load_contract_payload(path)
        expected_schema = "rip.evidence-classification-policy.v1" if contract_type is EvidenceClassificationPolicy else "rip.evidence-classification.v1"
        if payload.get("schema") != expected_schema:
            raise ValueError(f"persisted {kind} contract has unsupported schema: {path.name}")
        raw = payload["contract"]
        if not isinstance(raw, dict):
            raise ValueError(f"persisted {kind} contract is invalid: {path.name}")
        loaded.append(_typed_contract(raw, contract_type, path.name))
    return tuple(loaded)


def _typed_contract(raw: dict[str, object], contract_type: type[_T], name: str) -> _T:
    values = dict(raw)
    supplied_fingerprint = values.pop("fingerprint", None)
    try:
        if contract_type is ClassificationRequest:
            values["scope"] = ClassificationScope(values["scope"])
            values["proposed_evidence_class"] = EvidenceClass(values["proposed_evidence_class"])
            values["proposed_integrity_treatment"] = IntegrityTreatment(values["proposed_integrity_treatment"])
            result = create_classification_request(**values)
        elif contract_type is ClassificationDecision:
            values["status"] = ClassificationRequestStatus(values["status"])
            if values.get("decided_evidence_class") is not None:
                values["decided_evidence_class"] = EvidenceClass(values["decided_evidence_class"])
            if values.get("decided_integrity_treatment") is not None:
                values["decided_integrity_treatment"] = IntegrityTreatment(values["decided_integrity_treatment"])
            result = create_classification_decision(**values)
        elif contract_type is EvidenceClassification:
            values["scope"] = ClassificationScope(values["scope"])
            values["evidence_class"] = EvidenceClass(values["evidence_class"])
            values["integrity_treatment"] = IntegrityTreatment(values["integrity_treatment"])
            result = create_evidence_classification(**values)
        else:
            raw_records = values.get("classifications")
            if not isinstance(raw_records, list):
                raise ValueError("policy classifications are required")
            values["classifications"] = tuple(_typed_contract(item, EvidenceClassification, name) for item in raw_records if isinstance(item, dict))
            if len(values["classifications"]) != len(raw_records):
                raise ValueError("policy classifications are invalid")
            result = create_classification_policy(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"persisted {contract_type.__name__} contract is invalid: {name}") from exc
    if result.fingerprint != supplied_fingerprint:
        raise ValueError(f"persisted {contract_type.__name__} fingerprint does not match: {name}")
    return result


def _validate_scope(
    organization_id: str, run_id: str, source_fingerprint: str,
    requests: tuple[ClassificationRequest, ...], decisions: tuple[ClassificationDecision, ...],
    records: tuple[EvidenceClassification, ...], policies: tuple[EvidenceClassificationPolicy, ...],
) -> None:
    if any(item.organization_id != organization_id or item.onboarding_run_id != run_id for item in (*requests, *decisions, *records, *policies)):
        raise ValueError("persisted classification artifacts are foreign to this workspace or run")
    if any(item.source_manifest_fingerprint != source_fingerprint for item in (*requests, *records)):
        raise ValueError("persisted classification artifacts are stale for the retained source manifest")


def _validate_record_decisions(records: tuple[EvidenceClassification, ...], decisions: dict[str, ClassificationDecision]) -> None:
    for record in records:
        decision = decisions.get(record.decision_id)
        if decision is None or decision.fingerprint != record.decision_fingerprint:
            raise ValueError("classification record lacks its persisted immutable decision")
        if decision.status is not ClassificationRequestStatus.APPROVED:
            raise ValueError("classification record decision is not approved")
        if decision.decided_evidence_class is not record.evidence_class or decision.decided_integrity_treatment is not record.integrity_treatment:
            raise ValueError("classification record does not match its approved decision")


def _is_approved(request: ClassificationRequest, decisions: tuple[ClassificationDecision, ...]) -> bool:
    return any(item.request_fingerprint == request.fingerprint and item.status is ClassificationRequestStatus.APPROVED for item in decisions)


def _evaluate_readiness(
    manifest: dict[str, object], reconstruction: PolicyReconstruction, unresolved: tuple[str, ...],
    policies: tuple[EvidenceClassificationPolicy, ...], source_fingerprint: str, retained_source_is_stale: bool,
) -> tuple[ClassificationReadiness, ClassificationEvaluation | None]:
    if retained_source_is_stale:
        return ClassificationReadiness.STALE_SOURCE, None
    if any(policy.source_manifest_fingerprint != source_fingerprint for policy in policies):
        return ClassificationReadiness.STALE_POLICY, None
    if reconstruction.conflict_ids:
        return ClassificationReadiness.BLOCKED_BY_CONFLICT, None
    if reconstruction.policy is None:
        return ClassificationReadiness.AWAITING_CLASSIFICATION, None
    evaluation = evaluate_classification_policy(manifest, reconstruction.policy)
    if unresolved or evaluation.summary.unknown_entries:
        return ClassificationReadiness.AWAITING_CLASSIFICATION, evaluation
    return ClassificationReadiness.READY, evaluation


def _result(
    organization_id: str, run_id: str, source_fingerprint: str, requests: tuple[ClassificationRequest, ...],
    decisions: tuple[ClassificationDecision, ...], records: tuple[EvidenceClassification, ...], reconstruction: PolicyReconstruction,
    unresolved: tuple[str, ...], readiness: ClassificationReadiness, evaluation: ClassificationEvaluation | None,
) -> ClassificationIntegrationResult:
    result_values = {
        "organization_id": organization_id, "onboarding_run_id": run_id, "source_manifest_fingerprint": source_fingerprint,
        "readiness": readiness, "request_ids": tuple(item.request_id for item in requests),
        "unresolved_request_ids": unresolved, "decision_ids": tuple(item.decision_id for item in decisions),
        "record_ids": tuple(item.classification_id for item in records),
    }
    fingerprint_payload = {
        **{**result_values, "readiness": readiness.value}, "policy_history_fingerprint": reconstruction.fingerprint,
        "evaluation_fingerprint": evaluation.fingerprint if evaluation else None,
    }
    return ClassificationIntegrationResult(
        **result_values, policy_history=reconstruction, evaluation=evaluation,
        fingerprint=fingerprint(fingerprint_payload),
    )


def _write_summary(path: Path, result: ClassificationIntegrationResult) -> None:
    payload = {
        "schema": INTEGRATION_SCHEMA, "organization_id": result.organization_id, "onboarding_run_id": result.onboarding_run_id,
        "source_manifest_fingerprint": result.source_manifest_fingerprint, "readiness": result.readiness.value,
        "request_ids": result.request_ids, "unresolved_request_ids": result.unresolved_request_ids,
        "decision_ids": result.decision_ids, "record_ids": result.record_ids,
        "policy_history_fingerprint": result.policy_history.fingerprint,
        "evaluation_fingerprint": result.evaluation.fingerprint if result.evaluation else None, "fingerprint": result.fingerprint,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing is not None and existing != encoded:
        raise ValueError("classification integration summary already exists with different content")
    if existing is None:
        path.write_text(encoded, encoding="utf-8")


def _read_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"{label} is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is invalid")
    return payload


def _string(payload: dict[str, object], name: str, label: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} {name} is required")
    return value
