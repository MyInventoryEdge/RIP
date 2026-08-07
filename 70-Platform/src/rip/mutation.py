"""Reusable governed interpretation of retained filesystem mutation evidence.

This module consumes a retained difference; it never walks or reads a source.
Policies may prove a safe action. Absent such proof it returns a scoped pause,
not a filename exception or an unexplained global interruption.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from fnmatch import fnmatchcase


class SourceRole(str, Enum):
    STABLE_AUTHORITATIVE = "stable-authoritative-evidence"
    MUTABLE_OPERATIONAL = "expected-mutable-operational-state"
    APPEND_ONLY = "append-only-evidence"
    TRANSACTIONAL = "transactional-live-state"
    GENERATED = "generated-derived-state"
    UNRESOLVED = "unresolved"


class TrustAction(str, Enum):
    CONTINUE = "continue"
    PAUSE_AFFECTED_SCOPE = "pause-affected-scope"
    PAUSE_SCOPE = "pause-affected-scope" # compatibility alias
    GOVERNED_REVIEW = "governed-review"
    FULL_VERIFICATION = "full-verification"
    TERMINATE = "terminate"
    PAUSE_GLOBAL = "pause-global" # legacy only; new policies use explicit actions


@dataclass(frozen=True, slots=True)
class MutationRule:
    target: str
    role: SourceRole
    owner: str
    writer: str | None
    expected_mutability: bool
    affected_scope: tuple[str, ...]
    confidence: str


@dataclass(frozen=True, slots=True)
class MutationReasoning:
    path: str
    change_kind: str
    source_role: SourceRole
    owner: str | None
    writer: str | None
    expected_mutability: bool | None
    confidence: str
    material: bool | None
    affected_scope: tuple[str, ...]
    required_trust_action: TrustAction
    explanation: str


@dataclass(frozen=True, slots=True)
class MutationInterpretation:
    reasonings: tuple[MutationReasoning, ...]
    required_trust_action: TrustAction
    explanation: str
    fingerprint: str


def interpret_mutation(difference: dict[str, object], *, rules: tuple[MutationRule, ...] = ()) -> MutationInterpretation:
    """Interpret exact retained differences under declared, deterministic rules."""
    changes: list[tuple[str, str]] = []
    for key, kind in (("modified_content_paths", "modified"), ("added_paths", "added"), ("removed_paths", "removed"), ("kind_changed_paths", "kind-changed"), ("access_state_changed_paths", "access-state-changed")):
        changes.extend((str(path), kind) for path in difference.get(key, ()) if isinstance(path, str))
    reasonings = tuple(_reason(path, kind, rules) for path, kind in sorted(changes, key=lambda item: item[0].casefold()))
    action = TrustAction.PAUSE_GLOBAL if any(item.required_trust_action is TrustAction.PAUSE_GLOBAL for item in reasonings) else (TrustAction.PAUSE_SCOPE if any(item.required_trust_action is TrustAction.PAUSE_SCOPE for item in reasonings) else TrustAction.CONTINUE)
    explanation = "All mutations are governed expected mutable operational evidence; organizational understanding remains trustworthy." if action is TrustAction.CONTINUE else "At least one mutation lacks sufficient governed evidence for automatic continuation; only the stated scope is paused."
    payload = {"reasonings": [_json(item) for item in reasonings], "required_trust_action": action.value, "explanation": explanation}
    return MutationInterpretation(reasonings, action, explanation, hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest())


def _reason(path: str, kind: str, rules: tuple[MutationRule, ...]) -> MutationReasoning:
    rule = next((item for item in rules if fnmatchcase(path, item.target)), None)
    if rule and rule.role is SourceRole.MUTABLE_OPERATIONAL and rule.expected_mutability and kind == "modified":
        return MutationReasoning(path, kind, rule.role, rule.owner, rule.writer, True, rule.confidence, False, rule.affected_scope, TrustAction.CONTINUE, f"{path} is governed mutable operational state owned by {rule.owner}; its expected content mutation does not materially invalidate the declared organizational scope.")
    scope = rule.affected_scope if rule else (path,)
    return MutationReasoning(path, kind, rule.role if rule else SourceRole.UNRESOLVED, rule.owner if rule else None, rule.writer if rule else None, rule.expected_mutability if rule else None, rule.confidence if rule else "unproven", None, scope, TrustAction.PAUSE_SCOPE, f"{path} changed as {kind}, but RIP has no governed rule proving its role, expected mutability, or materiality. The affected scope is paused for interpretation.")


def _json(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum): return value.value
    if isinstance(value, tuple): return [_json(item) for item in value]
    return value
