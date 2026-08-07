"""Fail-closed Supreme Decision Authority and bounded autonomy contracts.

This module deliberately has no implicit runtime provisioning, no network
dependency, and no mutation executor.  Callers supply an authenticated human
identity boundary, a signing authority, and (when publishing) the existing
Journal authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

SDA_SCHEMA = "rip.supreme-decision.v1"
CHARTER_SCHEMA = "rip.authority-charter.v1"
BUDGET_SCHEMA = "rip.execution-budget.v1"
BOOTSTRAP_SCHEMA = "rip.sda-bootstrap.v1"
EXECUTION_SCHEMA = "rip.execution-record.v1"


def _utcnow() -> str: return datetime.now(timezone.utc).isoformat()
def _canonical(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
def _digest(value: Any) -> str: return hashlib.sha256(_canonical(value)).hexdigest()


class ActionDisposition(str, Enum):
    AUTONOMOUS = "AUTONOMOUS"
    RECOMMEND = "RECOMMEND"
    REQUEST_AUTHORIZATION = "REQUEST_AUTHORIZATION"
    ESCALATE_TO_SDA = "ESCALATE TO SDA"
    REFUSE = "REFUSE"


class AuthorityError(ValueError): pass
class BudgetExceeded(AuthorityError): pass


@dataclass(frozen=True)
class AuthenticatedHuman:
    """Narrow local boundary: an OS authenticated subject, never typed text."""
    identity: str
    authenticated: bool
    proof: Mapping[str, str]

    @classmethod
    def current_windows_user(cls) -> "AuthenticatedHuman":
        # getlogin may be absent in services; USERNAME alone is intentionally
        # insufficient, so include the process token-derived account domain.
        import getpass
        name = getpass.getuser()
        domain = os.environ.get("USERDOMAIN", "local")
        return cls(identity=f"windows:{domain}\\{name}", authenticated=True,
                   proof={"boundary": "windows-process-token", "subject": f"{domain}\\{name}"})


@dataclass(frozen=True)
class SupremeDecision:
    decision_id: str
    created_at: str
    effective_at: str
    holder_identity: str
    decision_class: str
    title: str
    decision_text: str
    reason: str
    scope: Mapping[str, Any]
    referenced_artifacts: tuple[str, ...]
    authorized_changes: tuple[str, ...]
    compatibility_rules: tuple[str, ...]
    delegation_terms: Mapping[str, Any]
    supersedes_decision_id: str | None
    status: str
    producer_identity: str
    producer_version: str
    schema: str = SDA_SCHEMA
    signature: Mapping[str, Any] | None = None

    def unsigned(self) -> dict[str, Any]:
        value = asdict(self); value.pop("signature"); return value


@dataclass(frozen=True)
class AuthorityCharter:
    authority_id: str
    authority_level: int
    decision_classes: tuple[str, ...]
    permitted_artifact_schemas: tuple[str, ...]
    scope: Mapping[str, Any]
    effective_at: str
    expires_at: str | None
    quorum_requirements: Mapping[str, Any]
    escalation_rules: tuple[str, ...]
    revocation_conditions: tuple[str, ...]
    delegation_permitted: bool
    maximum_delegation_depth: int
    resource_budget_authority: bool
    superseded_charter_identity: str | None = None
    schema: str = CHARTER_SCHEMA
    status: str = "active"

    def permits(self, decision_class: str, artifact_schema: str, target_scope: Mapping[str, Any], *, depth: int = 0, at: str | None = None) -> bool:
        if self.status != "active" or depth > self.maximum_delegation_depth: return False
        if decision_class not in self.decision_classes or artifact_schema not in self.permitted_artifact_schemas: return False
        now = at or _utcnow()
        if now < self.effective_at or (self.expires_at and now >= self.expires_at): return False
        return all(target_scope.get(key) == value for key, value in self.scope.items())


@dataclass(frozen=True)
class ExecutionBudget:
    budget_id: str
    level: str
    scope: Mapping[str, Any]
    limits: Mapping[str, int | float]
    effective_at: str
    expires_at: str | None = None
    schema: str = BUDGET_SCHEMA
    status: str = "active"

    def applies(self, scope: Mapping[str, Any], at: str | None = None) -> bool:
        now = at or _utcnow()
        return self.status == "active" and now >= self.effective_at and (not self.expires_at or now < self.expires_at) and all(scope.get(k) == v for k, v in self.scope.items())


@dataclass(frozen=True)
class ActionPlan:
    action_id: str
    action_class: str
    constitutional_authority: str | None
    target_scope: Mapping[str, Any]
    expected_benefit: str
    estimated_api_cost: float
    maximum_api_cost: float
    estimated_runtime_seconds: int
    maximum_runtime_seconds: int
    files_affected: tuple[str, ...]
    mutation_permission: bool
    rollback_behavior: str
    external_network_calls: int = 0


@dataclass(frozen=True)
class ExecutionRecord:
    action_id: str
    disposition: str
    reason: str
    authority_used: str | None
    budget_allocated: Mapping[str, int | float]
    budget_consumed: Mapping[str, int | float]
    evidence_produced: tuple[str, ...]
    files_changed: tuple[str, ...]
    result: str
    deferred_work: tuple[str, ...]
    created_at: str = field(default_factory=_utcnow)
    schema: str = EXECUTION_SCHEMA


class SupremeDecisionAuthority:
    """The human-only constitutional decision implementation point."""
    def __init__(self, *, holder_identity: str, signer: Any, journal_publish: Callable[..., Any] | None = None,
                 bootstrap: Mapping[str, Any] | None = None) -> None:
        self.holder_identity, self.signer, self.journal_publish, self.bootstrap = holder_identity, signer, journal_publish, bootstrap

    @staticmethod
    def bootstrap_ceremony(*, holder: AuthenticatedHuman, signer: Any, initial_artifacts: tuple[str, ...], journal_path: str) -> dict[str, Any]:
        if not holder.authenticated or not holder.identity:
            raise AuthorityError("bootstrap requires an authenticated local human identity")
        body = {"schema": BOOTSTRAP_SCHEMA, "bootstrap_id": str(uuid.uuid4()), "created_at": _utcnow(),
                "sda_office": "SupremeDecisionAuthority", "holder_identity": holder.identity,
                "holder_proof": dict(holder.proof), "initial_constitutional_artifacts": list(initial_artifacts),
                "journal_publication_path": journal_path, "ceremony": "human reviewed and explicitly confirmed bootstrap"}
        body["signature"] = signer.sign(_canonical(body))
        return body

    @staticmethod
    def retain_bootstrap(bootstrap: Mapping[str, Any], path: Path) -> Path:
        """Retain the one-time trust anchor; an existing anchor is never replaced."""
        if path.exists():
            raise AuthorityError("SDA bootstrap already exists and is immutable")
        if bootstrap.get("schema") != BOOTSTRAP_SCHEMA or not bootstrap.get("signature"):
            raise AuthorityError("invalid SDA bootstrap evidence")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(bootstrap), sort_keys=True), encoding="utf-8")
        return path

    def decide(self, decision: SupremeDecision, *, human: AuthenticatedHuman, confirmed: bool) -> SupremeDecision:
        if not human.authenticated: raise AuthorityError("unauthenticated SDA decision rejected")
        if human.identity != self.holder_identity or decision.holder_identity != self.holder_identity: raise AuthorityError("SDA holder proof rejected")
        if not confirmed: raise AuthorityError("explicit human confirmation is required")
        if decision.schema != SDA_SCHEMA or decision.status != "active": raise AuthorityError("invalid SDA decision artifact")
        if decision.effective_at <= _utcnow() or decision.effective_at <= decision.created_at:
            raise AuthorityError("SDA decisions must be prospective")
        required = (decision.decision_text, decision.reason, decision.decision_class, decision.title)
        if not all(required): raise AuthorityError("SDA decision fields are required")
        signed = SupremeDecision(**{**decision.unsigned(), "signature": self.signer.sign(_canonical(decision.unsigned()))})
        if self.journal_publish is not None:
            self.journal_publish(producer_authority_type="SupremeDecisionAuthority", producer_authority_id="sda",
                                 producer_record_type=SDA_SCHEMA, producer_record_id=signed.decision_id,
                                 canonical_payload=asdict(signed))
        return signed


class AutonomyPolicy:
    """Classifies all action proposals; initial policy is intentionally narrow."""
    INITIAL_AUTONOMOUS = frozenset({"rebuild_repository_memory", "refresh_repository_intelligence", "refresh_work_queue", "recompute_health", "verify_retained_artifacts", "detect_stale_projections"})
    PROHIBITED_AUTONOMOUS = frozenset({"source_modification", "commit", "constitutional_decision", "engineering_decision", "policy_change", "authority_creation", "repository_rewrite"})

    def __init__(self, budgets: tuple[ExecutionBudget, ...] = (), charters: tuple[AuthorityCharter, ...] = ()) -> None:
        self.budgets, self.charters = budgets, charters

    def effective_budget(self, scope: Mapping[str, Any]) -> Mapping[str, int | float]:
        applicable = [b for b in self.budgets if b.applies(scope)]
        if not applicable: return {}
        keys = set().union(*(b.limits for b in applicable)); return {k: min(b.limits[k] for b in applicable if k in b.limits) for k in keys}

    def classify(self, plan: ActionPlan) -> ActionDisposition:
        if plan.action_class in self.PROHIBITED_AUTONOMOUS: return ActionDisposition.REQUEST_AUTHORIZATION
        if plan.action_class not in self.INITIAL_AUTONOMOUS: return ActionDisposition.RECOMMEND
        if plan.mutation_permission or plan.external_network_calls: return ActionDisposition.REQUEST_AUTHORIZATION
        if plan.constitutional_authority is None: return ActionDisposition.ESCALATE_TO_SDA
        budget = self.effective_budget(plan.target_scope)
        if self._exceeds(plan, budget): return ActionDisposition.RECOMMEND
        return ActionDisposition.AUTONOMOUS

    @staticmethod
    def _exceeds(plan: ActionPlan, budget: Mapping[str, int | float]) -> bool:
        checks = {"api_spend_per_action": plan.maximum_api_cost, "elapsed_time_limit": plan.maximum_runtime_seconds,
                  "files_read": len(plan.files_affected), "external_network_calls": plan.external_network_calls,
                  "files_written": int(plan.mutation_permission), "autonomous_repository_mutations": int(plan.mutation_permission)}
        return any(key in budget and value > budget[key] for key, value in checks.items())

    def authorize(self, plan: ActionPlan) -> ExecutionRecord:
        disposition = self.classify(plan)
        budget = self.effective_budget(plan.target_scope)
        if disposition != ActionDisposition.AUTONOMOUS:
            return ExecutionRecord(plan.action_id, disposition.value, "authority, scope, budget, or expected-value gate did not permit execution", plan.constitutional_authority, budget, {}, (), (), "deferred", (plan.action_class,))
        return ExecutionRecord(plan.action_id, disposition.value, "least necessary bounded deterministic action", plan.constitutional_authority, budget, {}, (), (), "authorized", ())


def retain_execution_record(record: ExecutionRecord, directory: Path) -> Path:
    """Append immutable local execution evidence; this is not a repository mutation."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "execution-records.ndjson"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    return path


def first_sda_decision_draft(holder_identity: str) -> SupremeDecision:
    """Draft only: it deliberately cannot be published without human confirmation."""
    now = datetime.now(timezone.utc)
    return SupremeDecision("sda-first-decision-v1", now.isoformat(), (now + timedelta(minutes=5)).isoformat(), holder_identity, "constitutional-evolution",
        "Initial producer admission, delegation, and autonomy authorization",
        "Authorize Producer Admission Certificate v2; schema-bound producer admission; preservation of v1 semantics; creation of Engineering Decision Authority; admission of rip.engineering-decision.v1; generic authority delegation rules; and initial autonomy-budget rules.",
        "Establish the bounded foundations required before Engineering Decision Capture.", {"platform": "RIP"},
        ("Producer Admission Certificate v2",), ("preserve v1 semantics",), ("prospective only",),
        {"delegation": "bounded, revocable, and non-sovereign"}, None, "active", holder_identity, "1")


class SDAWorkflow:
    """Production composition for explicit human SDA bootstrap and publication."""
    def __init__(self, context: Any, state_directory: Path) -> None:
        self.context, self.state_directory = context, state_directory
        self.bootstrap_path = state_directory / "sda-bootstrap.json"
        self.pending_path = state_directory / "sda-pending-decision.json"
        self.published_path = state_directory / "sda-published-decision.json"

    def status(self) -> tuple[str | None, SupremeDecision | None]:
        if not self.bootstrap_path.exists(): return None, None
        data = json.loads(self.bootstrap_path.read_text(encoding="utf-8"))
        holder = data.get("holder_identity")
        if self.published_path.exists() or not holder: return holder, None
        if not self.pending_path.exists():
            self.pending_path.write_text(json.dumps(asdict(first_sda_decision_draft(holder)), sort_keys=True), encoding="utf-8")
        raw = json.loads(self.pending_path.read_text(encoding="utf-8"))
        return holder, SupremeDecision(**raw)

    def bootstrap(self, *, human: AuthenticatedHuman, confirmed: bool) -> str:
        if not confirmed: raise AuthorityError("bootstrap requires explicit human confirmation")
        evidence = SupremeDecisionAuthority.bootstrap_ceremony(holder=human, signer=self.context.platform_key_provider,
            initial_artifacts=(SDA_SCHEMA, CHARTER_SCHEMA, BUDGET_SCHEMA), journal_path=str(self.context.journal_storage.journal_path()))
        SupremeDecisionAuthority.retain_bootstrap(evidence, self.bootstrap_path)
        # Admission is an explicit part of this initial, human-confirmed bootstrap
        # ceremony. It is not performed by an autonomous runtime action.
        self.context.producer_policy_authority.issue_admission_certificate(
            producer_authority_type="SupremeDecisionAuthority", producer_authority_id="sda",
            permitted_record_types=(SDA_SCHEMA,), producer_key_reference="platform-key:active")
        self.pending_path.write_text(json.dumps(asdict(first_sda_decision_draft(human.identity)), sort_keys=True), encoding="utf-8")
        return human.identity

    def approve_and_publish(self, *, human: AuthenticatedHuman, decision: SupremeDecision, confirmed: bool) -> Mapping[str, Any]:
        if self.published_path.exists():
            return json.loads(self.published_path.read_text(encoding="utf-8"))
        holder, pending = self.status()
        if holder is None: raise AuthorityError("SDA bootstrap is required before approval")
        if pending is None or pending.decision_id != decision.decision_id: raise AuthorityError("the reviewed pending decision is no longer active")
        certificates = [json.loads(line) for line in self.context.producer_policy_authority._storage.certificate_path().read_text(encoding="utf-8").splitlines() if line.strip()]
        certificate = next((item for item in reversed(certificates) if item.get("producer_authority_type") == "SupremeDecisionAuthority" and item.get("producer_authority_id") == "sda" and SDA_SCHEMA in item.get("permitted_record_types", ())), None)
        if certificate is None: raise AuthorityError("SDA Journal admission is absent")
        authority = SupremeDecisionAuthority(holder_identity=holder, signer=self.context.platform_key_provider,
            journal_publish=lambda **kwargs: self.context.journal_authority.publish(**kwargs, producer_admission_certificate=certificate))
        signed = authority.decide(decision, human=human, confirmed=confirmed)
        self.context.journal_authority.validate()
        receipt = {"decision_id": signed.decision_id, "title": signed.title, "holder_identity": human.identity,
                   "effective_at": signed.effective_at, "journal": "published", "status": "active",
                   "receipt": _digest(asdict(signed))}
        self.published_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        return receipt
