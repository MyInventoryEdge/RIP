"""Deterministic evaluation of immutable evidence-classification policies.

The engine consumes an already-complete source manifest.  It never reads the
customer repository, changes onboarding state, or applies an execution action.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .classification import ClassificationScope, EvidenceClass, EvidenceClassification, EvidenceClassificationPolicy, IntegrityTreatment, _to_json
from .models import fingerprint


CLASSIFICATION_EVALUATION_SCHEMA = "rip.evidence-classification-evaluation.v1"


@dataclass(frozen=True, slots=True)
class ClassificationConflict:
    path: str
    classification_ids: tuple[str, ...]
    reason: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class EvaluatedEvidenceEntry:
    path: str
    kind: str
    value: str | None
    size: int | None
    evidence_class: EvidenceClass
    integrity_treatment: IntegrityTreatment
    classification_id: str | None
    conflict_ids: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ClassificationSummary:
    total_entries: int
    organizational_evidence_entries: int
    unknown_entries: int
    operational_state_entries: int
    generated_blocking_entries: int
    generated_non_blocking_reported_entries: int
    inventory_only_entries: int
    conflicted_entries: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ClassificationEvaluation:
    schema: str
    organization_id: str
    onboarding_run_id: str
    source_manifest_fingerprint: str
    policy_fingerprint: str
    complete_source_fingerprint: str
    organizational_evidence_fingerprint: str
    entries: tuple[EvaluatedEvidenceEntry, ...]
    conflicts: tuple[ClassificationConflict, ...]
    summary: ClassificationSummary
    fingerprint: str


def evaluate_classification_policy(manifest: dict[str, object], policy: EvidenceClassificationPolicy) -> ClassificationEvaluation:
    """Resolve one immutable policy against one existing manifest deterministically."""
    entries = _validate_manifest(manifest)
    manifest_fingerprint = str(manifest["manifest_fingerprint"])
    if policy.source_manifest_fingerprint != manifest_fingerprint:
        raise ValueError("classification policy source manifest fingerprint is stale")
    _validate_policy(policy)

    evaluated: list[EvaluatedEvidenceEntry] = []
    conflicts: list[ClassificationConflict] = []
    for source in entries:
        applicable = [item for item in policy.classifications if _matches(item, source["path"])]
        selected, conflict = _resolve(source["path"], applicable)
        if conflict:
            conflicts.append(conflict)
        evidence_class = selected.evidence_class if selected else EvidenceClass.UNKNOWN
        treatment = selected.integrity_treatment if selected else IntegrityTreatment.BLOCKING
        value = source["value"]
        payload = {"path": source["path"], "kind": source["kind"], "value": value, "size": source["size"], "evidence_class": evidence_class, "integrity_treatment": treatment, "classification_id": selected.classification_id if selected else None, "conflict_ids": conflict.classification_ids if conflict else ()}
        evaluated.append(EvaluatedEvidenceEntry(**payload, fingerprint=fingerprint(_to_json(payload))))

    complete = fingerprint([_complete_item(item) for item in evaluated])
    organizational = fingerprint([_complete_item(item) for item in evaluated if _participates_in_organizational_fingerprint(item)])
    summary = _summary(tuple(evaluated), tuple(conflicts))
    payload = {"schema": CLASSIFICATION_EVALUATION_SCHEMA, "organization_id": policy.organization_id, "onboarding_run_id": policy.onboarding_run_id, "source_manifest_fingerprint": manifest_fingerprint, "policy_fingerprint": policy.fingerprint, "complete_source_fingerprint": complete, "organizational_evidence_fingerprint": organizational, "entries": tuple(evaluated), "conflicts": tuple(conflicts), "summary": summary}
    return ClassificationEvaluation(**payload, fingerprint=fingerprint(_to_json(payload)))


def _validate_manifest(manifest: dict[str, object]) -> tuple[dict[str, Any], ...]:
    if not isinstance(manifest.get("manifest_fingerprint"), str):
        raise ValueError("source manifest fingerprint is required")
    raw = manifest.get("entries")
    if not isinstance(raw, list):
        raise ValueError("source manifest entries are required")
    entries: list[dict[str, Any]] = []
    paths: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("kind"), str):
            raise ValueError("source manifest entries must be complete")
        path = item["path"]
        if path in paths or not path or path.startswith("/") or "\\" in path or ".." in path.split("/"):
            raise ValueError("source manifest paths must be unique normalized relative paths")
        paths.add(path)
        entries.append({"path": path, "kind": item["kind"], "value": item.get("value"), "size": item.get("size")})
    if entries != sorted(entries, key=lambda item: item["path"]):
        raise ValueError("source manifest entries must be path sorted")
    return tuple(entries)


def _validate_policy(policy: EvidenceClassificationPolicy) -> None:
    for item in policy.classifications:
        if item.source_manifest_fingerprint != policy.source_manifest_fingerprint:
            raise ValueError("classification record source manifest fingerprint does not match policy")


def _resolve(path: str, classifications: list[EvidenceClassification]) -> tuple[EvidenceClassification | None, ClassificationConflict | None]:
    if not classifications:
        return None, None
    ordered = sorted(classifications, key=lambda item: (_precedence(item), item.classification_id), reverse=True)
    winner = ordered[0]
    equivalent = [item for item in ordered if _precedence(item) == _precedence(winner)]
    semantic = {(item.evidence_class, item.integrity_treatment) for item in equivalent}
    if len(semantic) == 1:
        return winner, None
    ids = tuple(sorted(item.classification_id for item in equivalent))
    conflict_payload = {"path": path, "classification_ids": ids, "reason": "equivalent-precedence classifications disagree"}
    return None, ClassificationConflict(**conflict_payload, fingerprint=fingerprint(conflict_payload))


def _precedence(item: EvidenceClassification) -> tuple[int, int, int, int]:
    if item.scope is ClassificationScope.EXACT_PATH:
        return (2, len(item.target.split("/")), len(item.target), 0)
    parts = item.target.split("/")
    literals = sum(len(part.replace("*", "").replace("?", "")) for part in parts)
    wildcards = sum(part.count("*") + part.count("?") for part in parts)
    return (1, literals, len(parts), -wildcards)


def _matches(item: EvidenceClassification, path: str) -> bool:
    return item.target == path if item.scope is ClassificationScope.EXACT_PATH else _glob_matches(item.target.split("/"), path.split("/"))


def _glob_matches(pattern: list[str], path: list[str]) -> bool:
    if not pattern:
        return not path
    head, tail = pattern[0], pattern[1:]
    if head == "**":
        return _glob_matches(tail, path) or bool(path) and _glob_matches(pattern, path[1:])
    return bool(path) and _segment_matches(head, path[0]) and _glob_matches(tail, path[1:])


def _segment_matches(pattern: str, text: str) -> bool:
    row = [True] + [False] * len(text)
    for token in pattern:
        next_row = [False] * (len(text) + 1)
        if token == "*":
            next_row[0] = row[0]
            for index in range(1, len(text) + 1):
                next_row[index] = row[index] or next_row[index - 1]
        elif token == "?":
            for index in range(1, len(text) + 1):
                next_row[index] = row[index - 1]
        else:
            for index in range(1, len(text) + 1):
                next_row[index] = row[index - 1] and token == text[index - 1]
        row = next_row
    return row[-1]


def _participates_in_organizational_fingerprint(item: EvaluatedEvidenceEntry) -> bool:
    return item.evidence_class in {EvidenceClass.ORGANIZATIONAL_EVIDENCE, EvidenceClass.UNKNOWN} or (item.evidence_class is EvidenceClass.GENERATED_ARTIFACT and item.integrity_treatment is IntegrityTreatment.BLOCKING)


def _complete_item(item: EvaluatedEvidenceEntry) -> dict[str, object]:
    return {"path": item.path, "kind": item.kind, "value": item.value, "size": item.size}


def _summary(entries: tuple[EvaluatedEvidenceEntry, ...], conflicts: tuple[ClassificationConflict, ...]) -> ClassificationSummary:
    payload = {"total_entries": len(entries), "organizational_evidence_entries": sum(item.evidence_class is EvidenceClass.ORGANIZATIONAL_EVIDENCE for item in entries), "unknown_entries": sum(item.evidence_class is EvidenceClass.UNKNOWN for item in entries), "operational_state_entries": sum(item.evidence_class is EvidenceClass.OPERATIONAL_STATE for item in entries), "generated_blocking_entries": sum(item.evidence_class is EvidenceClass.GENERATED_ARTIFACT and item.integrity_treatment is IntegrityTreatment.BLOCKING for item in entries), "generated_non_blocking_reported_entries": sum(item.evidence_class is EvidenceClass.GENERATED_ARTIFACT and item.integrity_treatment is IntegrityTreatment.NON_BLOCKING_REPORTED for item in entries), "inventory_only_entries": sum(item.evidence_class is EvidenceClass.INVENTORY_ONLY for item in entries), "conflicted_entries": len(conflicts)}
    return ClassificationSummary(**payload, fingerprint=fingerprint(payload))
