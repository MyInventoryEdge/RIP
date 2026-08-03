"""Non-UI governed acceptance of immutable classification decisions."""

from __future__ import annotations

import json
from pathlib import Path

from .classification import (
    ClassificationDecision,
    ClassificationRequest,
    ClassificationRequestStatus,
    EvidenceClass,
    EvidenceClassification,
    IntegrityTreatment,
    create_classification_decision,
    create_evidence_classification,
    load_contract_payload,
    persist_contract,
    serialize_contract,
)
from .models import fingerprint
from .scope_preview import ScopePreview, validate_preview


def load_persisted_contracts(workspace: str, run_id: str, kind: str) -> tuple[dict[str, object], ...]:
    """Load immutable contract envelopes deterministically; never mutate history."""
    directory = Path(workspace) / "onboarding-runs" / run_id / "classifications" / kind
    if not directory.is_dir():
        return ()
    return tuple(load_contract_payload(path)["contract"] for path in sorted(directory.glob("*.json")))


def accept_decision(
    *,
    workspace: str,
    manifest: dict[str, object],
    request: ClassificationRequest,
    preview: ScopePreview,
    evidence_class: EvidenceClass,
    integrity_treatment: IntegrityTreatment,
    reviewer_identity: str,
    reviewer_role: str,
    authority_claim: str,
    rationale: str,
    supersedes: str | None = None,
) -> tuple[ClassificationDecision, EvidenceClassification]:
    """Append one approved decision and record after validating retained evidence only."""
    if not all(value.strip() for value in (reviewer_identity, reviewer_role, authority_claim)):
        raise ValueError("accepted decisions require respondent identity, role, and authority claim")
    root = Path(workspace)
    _validate_workspace_and_run(root, request)
    retained_manifest = _load_retained_manifest(root, request.onboarding_run_id)
    if manifest != retained_manifest:
        raise ValueError("provided manifest does not match the actual retained manifest")
    if request.source_manifest_fingerprint != retained_manifest.get("manifest_fingerprint"):
        raise ValueError("classification request is stale for the retained manifest")
    _validate_persisted_unresolved_request(root, request)
    _validate_request_preview(request, preview)
    if preview.requires_large_scope_acknowledgment:
        raise ValueError("large-scope acknowledgment is required")
    validate_preview(preview, retained_manifest)

    seed = {
        "request": request.fingerprint,
        "preview": preview.fingerprint,
        "class": evidence_class.value,
        "treatment": integrity_treatment.value,
        "authority": authority_claim,
    }
    decision = create_classification_decision(
        decision_id="decision-" + fingerprint(seed)[:24],
        request_id=request.request_id,
        request_fingerprint=request.fingerprint,
        organization_id=request.organization_id,
        onboarding_run_id=request.onboarding_run_id,
        status=ClassificationRequestStatus.APPROVED,
        decided_evidence_class=evidence_class,
        decided_integrity_treatment=integrity_treatment,
        reviewer_identity=reviewer_identity,
        reviewer_role=reviewer_role,
        authority_claim=authority_claim,
        rationale=rationale,
        supersedes_decision_id=None,
        decided_at=None,
    )
    record = create_evidence_classification(
        classification_id="record-" + decision.fingerprint[:24],
        organization_id=request.organization_id,
        onboarding_run_id=request.onboarding_run_id,
        target=request.target,
        scope=request.scope,
        evidence_class=evidence_class,
        integrity_treatment=integrity_treatment,
        source_manifest_fingerprint=request.source_manifest_fingerprint,
        decision_id=decision.decision_id,
        decision_fingerprint=decision.fingerprint,
        supersedes_classification_id=supersedes,
    )
    persist_contract(root, decision)
    persist_contract(root, record)
    return decision, record


def _validate_workspace_and_run(root: Path, request: ClassificationRequest) -> None:
    workspace = _load_json(root / "workspace.json", "organization workspace")
    if workspace.get("organization_id") != request.organization_id:
        raise ValueError("classification request organization does not match workspace")
    context = _load_json(root / "onboarding-runs" / request.onboarding_run_id / "context.json", "onboarding run")
    if context.get("organization_id") != request.organization_id or context.get("onboarding_run_id") != request.onboarding_run_id:
        raise ValueError("classification request does not match the retained onboarding run")


def _load_retained_manifest(root: Path, run_id: str) -> dict[str, object]:
    manifest = _load_json(root / "onboarding-runs" / run_id / "final-source-manifest.json", "retained manifest")
    if not isinstance(manifest.get("manifest_fingerprint"), str):
        raise ValueError("retained manifest has no manifest fingerprint")
    return manifest


def _validate_persisted_unresolved_request(root: Path, request: ClassificationRequest) -> None:
    persisted = load_persisted_contracts(str(root), request.onboarding_run_id, "requests")
    same_id = tuple(item for item in persisted if item.get("request_id") == request.request_id)
    if not same_id:
        raise ValueError("classification request is missing or not persisted")
    if len(same_id) != 1 or same_id[0].get("fingerprint") != request.fingerprint:
        raise ValueError("classification request fingerprint does not match its persisted request")
    if same_id[0] != serialize_contract(request)["contract"]:
        raise ValueError("classification request does not match its persisted immutable envelope")
    decisions = load_persisted_contracts(str(root), request.onboarding_run_id, "decisions")
    if any(item.get("request_fingerprint") == request.fingerprint and item.get("status") != "pending" for item in decisions):
        raise ValueError("classification request is already resolved")


def _validate_request_preview(request: ClassificationRequest, preview: ScopePreview) -> None:
    if request.source_manifest_fingerprint != preview.manifest_fingerprint:
        raise ValueError("approved source does not match the requested source manifest")
    if request.target != preview.target or request.scope is not preview.scope:
        raise ValueError("request and preview do not agree")


def _load_json(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"{label} is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is invalid")
    return payload
