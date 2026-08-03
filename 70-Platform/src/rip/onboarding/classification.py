"""Immutable, contract-only evidence-classification records for onboarding.

This module deliberately records classifications without applying them to
observation, integrity, lifecycle, or organizational understanding.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .models import fingerprint


EVIDENCE_CLASSIFICATION_SCHEMA = "rip.evidence-classification.v1"
EVIDENCE_CLASSIFICATION_POLICY_SCHEMA = "rip.evidence-classification-policy.v1"


class EvidenceClass(str, Enum):
    """Declared interpretation classes; no interpretation is applied in CZ-EC-1."""

    ORGANIZATIONAL_EVIDENCE = "organizational-evidence"
    OPERATIONAL_STATE = "operational-state"
    GENERATED_ARTIFACT = "generated-artifact"
    INVENTORY_ONLY = "inventory-only"
    UNKNOWN = "unknown"


class IntegrityTreatment(str, Enum):
    BLOCKING = "blocking"
    NON_BLOCKING_REPORTED = "non-blocking-reported"


class ClassificationScope(str, Enum):
    EXACT_PATH = "exact-path"
    PATH_GLOB = "path-glob"


class ClassificationRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


@dataclass(frozen=True, slots=True)
class ClassificationRequest:
    """An immutable request for a human-reviewed evidence classification."""

    request_id: str
    organization_id: str
    onboarding_run_id: str
    source_manifest_fingerprint: str
    target: str
    scope: ClassificationScope
    proposed_evidence_class: EvidenceClass
    proposed_integrity_treatment: IntegrityTreatment
    requester_identity: str
    requester_role: str
    authority_claim: str
    rationale: str
    created_at: str | None
    fingerprint: str

    def __post_init__(self) -> None:
        _validate_identity(self.request_id, "request")
        _validate_scope_target(self.target, self.scope)
        _validate_required(self.organization_id, self.onboarding_run_id, self.source_manifest_fingerprint,
                           self.requester_identity, self.authority_claim, self.rationale, self.fingerprint)
        _validate_treatment(self.proposed_evidence_class, self.proposed_integrity_treatment)
        _validate_fingerprint(self.fingerprint, "classification request")


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    """An immutable decision. It does not apply a classification to any runtime flow."""

    decision_id: str
    request_id: str
    request_fingerprint: str
    organization_id: str
    onboarding_run_id: str
    status: ClassificationRequestStatus
    decided_evidence_class: EvidenceClass | None
    decided_integrity_treatment: IntegrityTreatment | None
    reviewer_identity: str
    reviewer_role: str
    authority_claim: str
    rationale: str
    supersedes_decision_id: str | None
    decided_at: str | None
    fingerprint: str

    def __post_init__(self) -> None:
        _validate_identity(self.decision_id, "decision")
        _validate_required(self.request_id, self.request_fingerprint, self.organization_id, self.onboarding_run_id,
                           self.reviewer_identity, self.authority_claim, self.rationale, self.fingerprint)
        _validate_fingerprint(self.request_fingerprint, "request")
        _validate_fingerprint(self.fingerprint, "classification decision")
        if self.status is ClassificationRequestStatus.APPROVED:
            if self.decided_evidence_class is None or self.decided_integrity_treatment is None:
                raise ValueError("approved classification decisions require class and integrity treatment")
            _validate_treatment(self.decided_evidence_class, self.decided_integrity_treatment)
        elif self.decided_evidence_class is not None or self.decided_integrity_treatment is not None:
            raise ValueError("non-approved classification decisions must not carry a classification")


@dataclass(frozen=True, slots=True)
class EvidenceClassification:
    """A durable, append-only accepted classification record."""

    classification_id: str
    organization_id: str
    onboarding_run_id: str
    target: str
    scope: ClassificationScope
    evidence_class: EvidenceClass
    integrity_treatment: IntegrityTreatment
    source_manifest_fingerprint: str
    decision_id: str
    decision_fingerprint: str
    supersedes_classification_id: str | None
    fingerprint: str

    def __post_init__(self) -> None:
        _validate_identity(self.classification_id, "classification")
        _validate_scope_target(self.target, self.scope)
        _validate_required(self.organization_id, self.onboarding_run_id, self.source_manifest_fingerprint,
                           self.decision_id, self.decision_fingerprint, self.fingerprint)
        _validate_treatment(self.evidence_class, self.integrity_treatment)
        _validate_fingerprint(self.decision_fingerprint, "decision")
        _validate_fingerprint(self.fingerprint, "evidence classification")


@dataclass(frozen=True, slots=True)
class EvidenceClassificationPolicy:
    """Organization-scoped policy assembled only from accepted immutable records."""

    policy_id: str
    organization_id: str
    onboarding_run_id: str
    source_manifest_fingerprint: str
    classifications: tuple[EvidenceClassification, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        _validate_identity(self.policy_id, "policy")
        _validate_required(self.organization_id, self.onboarding_run_id, self.source_manifest_fingerprint, self.fingerprint)
        _validate_fingerprint(self.fingerprint, "classification policy")
        ids = [item.classification_id for item in self.classifications]
        if len(ids) != len(set(ids)):
            raise ValueError("classification policy records must be unique")
        if any(item.organization_id != self.organization_id or item.onboarding_run_id != self.onboarding_run_id for item in self.classifications):
            raise ValueError("classification policy records must remain organization and run scoped")


def create_classification_request(**values: Any) -> ClassificationRequest:
    return _build(ClassificationRequest, values)


def create_classification_decision(**values: Any) -> ClassificationDecision:
    return _build(ClassificationDecision, values)


def create_evidence_classification(**values: Any) -> EvidenceClassification:
    return _build(EvidenceClassification, values)


def create_classification_policy(**values: Any) -> EvidenceClassificationPolicy:
    return _build(EvidenceClassificationPolicy, values)


def serialize_contract(value: ClassificationRequest | ClassificationDecision | EvidenceClassification | EvidenceClassificationPolicy) -> dict[str, object]:
    """Return canonical JSON-compatible data, including schema and deterministic fingerprint."""
    return {"schema": _schema_for(value), "contract": _to_json(asdict(value))}


def persist_contract(workspace_path: str | Path, value: ClassificationRequest | ClassificationDecision | EvidenceClassification | EvidenceClassificationPolicy) -> Path:
    """Persist one immutable contract beneath its explicit onboarding-run workspace."""
    root = Path(workspace_path)
    directory = root / "onboarding-runs" / _run_for(value) / "classifications" / _kind_for(value)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{_id_for(value)}.json"
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        proposed = _canonical_json(serialize_contract(value))
        if existing != proposed:
            raise ValueError("immutable classification contract already exists with different content")
        return destination
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(_canonical_json(serialize_contract(value)), encoding="utf-8")
    temporary.replace(destination)
    return destination


def load_contract_payload(path: str | Path) -> dict[str, object]:
    """Load persisted contract JSON without inferring, applying, or reclassifying evidence."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("schema"), str) or not isinstance(payload.get("contract"), dict):
        raise ValueError("invalid persisted evidence-classification contract")
    return payload


def _build(contract_type: Any, values: dict[str, Any]) -> Any:
    supplied = dict(values)
    supplied.pop("fingerprint", None)
    supplied["fingerprint"] = fingerprint(_to_json(supplied))
    return contract_type(**supplied)


def _to_json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _to_json(asdict(value))
    if isinstance(value, tuple):
        return [_to_json(item) for item in value]
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json(item) for key, item in value.items()}
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema_for(value: object) -> str:
    return EVIDENCE_CLASSIFICATION_POLICY_SCHEMA if isinstance(value, EvidenceClassificationPolicy) else EVIDENCE_CLASSIFICATION_SCHEMA


def _kind_for(value: object) -> str:
    return {
        ClassificationRequest: "requests",
        ClassificationDecision: "decisions",
        EvidenceClassification: "records",
        EvidenceClassificationPolicy: "policies",
    }[type(value)]


def _id_for(value: object) -> str:
    return getattr(value, {ClassificationRequest: "request_id", ClassificationDecision: "decision_id", EvidenceClassification: "classification_id", EvidenceClassificationPolicy: "policy_id"}[type(value)])


def _run_for(value: object) -> str:
    return getattr(value, "onboarding_run_id")


def _validate_treatment(evidence_class: EvidenceClass, treatment: IntegrityTreatment) -> None:
    if evidence_class is EvidenceClass.UNKNOWN and treatment is not IntegrityTreatment.BLOCKING:
        raise ValueError("unknown evidence classifications must remain blocking")


def _validate_scope_target(target: str, scope: ClassificationScope) -> None:
    if not target or "\\" in target or target.startswith("/") or ":" in target:
        raise ValueError("classification targets must be normalized relative POSIX paths")
    parts = target.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("classification targets must not contain empty, current, or parent segments")
    if scope is ClassificationScope.EXACT_PATH and any(character in target for character in "*?"):
        raise ValueError("exact-path classifications cannot contain glob tokens")
    if scope is ClassificationScope.PATH_GLOB:
        if not any(character in target for character in "*?"):
            raise ValueError("path-glob classifications require a supported glob token")
        if any(character in target for character in "[]{}!"):
            raise ValueError("path-glob classifications support only *, **, and ? tokens")
        if any("**" in segment and segment != "**" for segment in parts):
            raise ValueError("** must occupy a complete path segment")


def _validate_required(*values: str) -> None:
    if any(not value or not value.strip() for value in values):
        raise ValueError("classification contracts require complete provenance and scope")


def _validate_identity(value: str, label: str) -> None:
    if not value or "/" in value or "\\" in value:
        raise ValueError(f"{label} identity is required")


def _validate_fingerprint(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} fingerprint must be SHA-256")
