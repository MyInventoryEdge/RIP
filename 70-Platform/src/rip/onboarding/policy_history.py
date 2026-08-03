"""Deterministic append-only reconstruction of immutable classification policy history."""
from __future__ import annotations
from dataclasses import dataclass
from .classification import EvidenceClassification, EvidenceClassificationPolicy, create_classification_policy
from .models import fingerprint

@dataclass(frozen=True, slots=True)
class PolicyReconstruction:
    organization_id: str
    onboarding_run_id: str
    source_manifest_fingerprint: str
    history_ids: tuple[str, ...]
    effective_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    policy: EvidenceClassificationPolicy | None
    fingerprint: str

def reconstruct_policy_history(*, organization_id: str, onboarding_run_id: str, source_manifest_fingerprint: str, records: tuple[EvidenceClassification, ...]) -> PolicyReconstruction:
    """Reconstruct effective records without modifying append-only record history."""
    ordered = tuple(sorted(records, key=lambda item: item.classification_id))
    if any(item.organization_id != organization_id or item.onboarding_run_id != onboarding_run_id or item.source_manifest_fingerprint != source_manifest_fingerprint for item in ordered):
        raise ValueError("policy history records must remain organization, run, and manifest scoped")
    ids = tuple(item.classification_id for item in ordered)
    if len(ids) != len(set(ids)):
        raise ValueError("policy history contains duplicate immutable identities")
    superseded = {item.supersedes_classification_id for item in ordered if item.supersedes_classification_id}
    if not superseded.issubset(set(ids)):
        raise ValueError("policy history supersession target is absent")
    effective = tuple(item for item in ordered if item.classification_id not in superseded)
    conflicts = tuple(sorted(item.classification_id for item in effective if sum(other.target == item.target and other.scope == item.scope and (other.evidence_class != item.evidence_class or other.integrity_treatment != item.integrity_treatment) for other in effective) > 0))
    policy = None if conflicts else create_classification_policy(policy_id="effective-" + fingerprint({"records": [item.fingerprint for item in effective]})[:24], organization_id=organization_id, onboarding_run_id=onboarding_run_id, source_manifest_fingerprint=source_manifest_fingerprint, classifications=effective)
    payload={"organization_id":organization_id,"onboarding_run_id":onboarding_run_id,"source_manifest_fingerprint":source_manifest_fingerprint,"history_ids":ids,"effective_ids":tuple(item.classification_id for item in effective),"conflict_ids":conflicts,"policy_fingerprint":policy.fingerprint if policy else None}
    return PolicyReconstruction(organization_id,onboarding_run_id,source_manifest_fingerprint,ids,tuple(item.classification_id for item in effective),conflicts,policy,fingerprint(payload))
