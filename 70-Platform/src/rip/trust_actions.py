"""Authenticated execution of one governed trust decision.

The decision envelope is the sole continuation contract.  The small legacy
views are retained only for human diagnostics; they are never authoritative.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .mutation import MutationInterpretation, TrustAction
from .lifecycle import apply_executor_transition

TRUST_ENVELOPE_SCHEMA = "rip.trust-decision-envelope.v1"
TRUST_EXECUTION_SCHEMA = "rip.trust-execution-receipt.v1"
TRUST_ACTION_SCHEMA = "rip.trust-action.v1"  # diagnostic compatibility only
_ENVELOPE_FIELDS = frozenset({"schema", "organization_id", "run_id", "observation_identifier", "reasoning_fingerprint", "trust_action", "affected_scope", "governing_policy", "evidence_identifiers", "manifest_fingerprint", "source_root_identity", "baseline_fingerprint", "decision_sequence", "operation_id", "reasoning_record_fingerprint", "created_at", "execution_status", "fingerprint", "journal_record_hash"})


def execute_trust_action(*, run_directory: str | Path, interpretation: MutationInterpretation,
                         target_state: str | None = None, expected_state: str | None = None, notify: Callable[[str], None] | None = None,
                         full_verification: Callable[[], None] | None = None,
                         observation_identifier: str = "retained-observation",
                         evidence_identifiers: tuple[str, ...] = (),
                         policy: dict[str, object] | None = None,
                         governed_source_root: str | Path | None = None,
                         organization_id: str | None = None, run_id: str | None = None, journal_context: dict | None = None) -> dict[str, object]:
    """Persist immutable intent, execute once, then seal completion.

    Replays of the same envelope are idempotent.  A different decision for the
    same run is rejected: a new reasoning run must use a new onboarding run.
    """
    root = Path(run_directory).resolve(); root.mkdir(parents=True, exist_ok=True)
    action = interpretation.required_trust_action
    scope = tuple(sorted({p for item in interpretation.reasonings for p in item.affected_scope}, key=str.casefold))
    manifest = _optional_json(root / "final-source-manifest.json")
    policy = policy or _optional_json(root / "mutation-policy.json") or {
        "policy_identifier": "local-runtime-contract", "version": "1", "authority": "RIP runtime", "precedence": 0,
    }
    reasoning = _optional_json(root / "mutation-reasoning.json") or {"mutation_identifier": interpretation.fingerprint}
    baseline = _optional_json(root / "trusted-baseline.json") or {}
    envelope = {
        "schema": TRUST_ENVELOPE_SCHEMA,
        "organization_id": organization_id or str(reasoning.get("organization_id", "unbound-test-organization")),
        "run_id": run_id or str(reasoning.get("onboarding_run_id", root.name)),
        "observation_identifier": observation_identifier,
        "reasoning_fingerprint": interpretation.fingerprint,
        "trust_action": action.value,
        "affected_scope": list(scope),
        "governing_policy": policy,
        "evidence_identifiers": sorted(set(evidence_identifiers)),
        "manifest_fingerprint": manifest.get("manifest_fingerprint") if manifest else None,
        "source_root_identity": _source_identity(governed_source_root) if governed_source_root is not None else None,
        "baseline_fingerprint": baseline.get("source_fingerprint"),
        "decision_sequence": 1,
        "operation_id": "operation-" + secrets.token_hex(16),
        "reasoning_record_fingerprint": _fingerprint(reasoning),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "execution_status": "intent-persisted",
    }
    envelope["fingerprint"] = _fingerprint({k: v for k, v in envelope.items() if k not in {"created_at", "execution_status", "journal_record_hash"}})
    existing = _optional_json(root / "trust-decision-envelope.json")
    if existing:
        _validate_envelope(existing, root)
        if existing["fingerprint"] != envelope["fingerprint"]:
            raise ValueError("conflicting trust decision already exists for this run")
        envelope = existing
    else:
        if journal_context is None: raise RuntimeError("certificate-bound Journal Authority context is required")
        context = _require_journal_context(journal_context)
        publication = context["journal_authority"].publish(
            producer_authority_type="trust-authority", producer_authority_id="trust-v1",
            producer_record_type="trust-decision-envelope", producer_record_id=str(envelope["operation_id"]),
            canonical_payload=envelope, producer_admission_certificate=context["producer_admission_certificate"],
        )
        envelope["journal_record_hash"] = publication["record_hash"]
        _atomic_write(root / "trust-decision-envelope.json", envelope)
    # Diagnostic projections cannot be consumed for execution.
    _atomic_write(root / "trust-action.json", {"schema": TRUST_ACTION_SCHEMA, "action": {"action": action.value, "reasoning_fingerprint": interpretation.fingerprint}})
    _atomic_write(root / "trust-scope.json", {"schema": TRUST_ACTION_SCHEMA, "affected_scope": list(scope), "reasoning_fingerprint": interpretation.fingerprint})
    receipt = _optional_json(root / "trust-execution-receipt.json")
    if receipt and receipt.get("envelope_fingerprint") == envelope["fingerprint"] and receipt.get("status") == "completed":
        return receipt
    _atomic_write(root / "trust-execution-receipt.json", {"schema": TRUST_EXECUTION_SCHEMA, "envelope_fingerprint": envelope["fingerprint"], "status": "executing", "started_at": datetime.now(timezone.utc).isoformat()})
    if action is TrustAction.FULL_VERIFICATION:
        if full_verification is None:
            raise ValueError("full verification requires an explicit executor callback")
        full_verification()
    if target_state is not None:
        if expected_state is None: raise ValueError("typed lifecycle execution requires expected state")
        apply_executor_transition(run_directory=root, expected_state=expected_state, target_state=target_state, operation_id=str(envelope["operation_id"]))
    message = f"RIP selected {action.value} for {len(scope)} governed scope path(s)."
    completed = {"schema": TRUST_EXECUTION_SCHEMA, "envelope_fingerprint": envelope["fingerprint"], "status": "completed", "action": action.value, "completed_at": datetime.now(timezone.utc).isoformat(), "notification": message}
    _atomic_write(root / "trust-execution-receipt.json", completed)
    if notify:
        notify(message)
    return completed


def verify_declared_scope(*, source_root: str | Path, expected_entries: tuple[dict[str, object], ...], affected_scope: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    """Hash only retained, contained manifest file paths."""
    root = Path(source_root).resolve(); expected = {str(i["path"]): i for i in expected_entries}
    verified = []
    for path in affected_scope:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or path not in expected:
            raise ValueError(f"invalid governed scope path: {path}")
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"scope escapes governed source root: {path}") from exc
        item = expected[path]
        if item.get("kind") != "file" or not candidate.is_file():
            raise RuntimeError(f"scoped verification failed: {path}")
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        verified.append({"path": path, "expected": item.get("value"), "actual": digest, "matches": digest == item.get("value")})
    return tuple(verified)


def execute_persisted_continuation(*, run_directory: str | Path, source_root: str | Path, journal_context: dict | None = None) -> dict[str, object]:
    """Replay an authenticated decision without reinterpreting a mutation.

    A pause is intentionally never promoted by byte equality; only a newly
    produced, separately authenticated decision may resolve it.
    """
    root = Path(run_directory).resolve()
    envelope = _read(root / "trust-decision-envelope.json")
    _validate_envelope(envelope, root)
    context = _require_journal_context(journal_context)
    context["journal_authority"].validate()
    storage = context["journal_storage"]
    records = [json.loads(line) for line in storage.journal_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    record = next((item for item in records if item.get("record_hash") == envelope.get("journal_record_hash")), None)
    if record is None or record.get("producer_authority_type") != "trust-authority" or record.get("canonical_payload", {}).get("fingerprint") != envelope["fingerprint"]:
        raise ValueError("trust decision journal publication is missing or contradictory")
    receipt = _read(root / "trust-execution-receipt.json")
    if set(receipt) - {"schema", "envelope_fingerprint", "status", "action", "completed_at", "notification", "started_at"} or receipt.get("schema") != TRUST_EXECUTION_SCHEMA or receipt.get("envelope_fingerprint") != envelope["fingerprint"] or receipt.get("status") != "completed":
        raise ValueError("trust execution receipt is missing, partial, or contradictory")
    if envelope.get("source_root_identity") is not None and envelope["source_root_identity"] != _source_identity(source_root):
        raise ValueError("trust decision source identity does not match the governed observation")
    action = TrustAction(envelope["trust_action"])
    if action is TrustAction.FULL_VERIFICATION:
        raise RuntimeError("FULL_VERIFICATION may only be initiated by the Trust Action Executor")
    if action in {TrustAction.PAUSE_AFFECTED_SCOPE, TrustAction.GOVERNED_REVIEW, TrustAction.TERMINATE, TrustAction.PAUSE_GLOBAL}:
        return {"action": action.value, "continued": False, "verified": (), "envelope_fingerprint": envelope["fingerprint"]}
    return {"action": action.value, "continued": True, "verified": (), "envelope_fingerprint": envelope["fingerprint"]}


def _validate_envelope(envelope: dict[str, object], root: Path) -> None:
    if set(envelope) != _ENVELOPE_FIELDS or envelope.get("schema") != TRUST_ENVELOPE_SCHEMA:
        raise ValueError("trust decision envelope is partial or invalid")
    expected = _fingerprint({k: v for k, v in envelope.items() if k not in {"created_at", "execution_status", "fingerprint", "journal_record_hash"}})
    if envelope.get("fingerprint") != expected:
        raise ValueError("trust decision envelope fingerprint mismatch")
    policy = envelope["governing_policy"]
    if not isinstance(policy, dict) or not {"policy_identifier", "version", "authority", "precedence"}.issubset(policy):
        raise ValueError("trust decision envelope lacks governed policy contract")
    reasoning = _optional_json(root / "mutation-reasoning.json")
    if reasoning and _fingerprint(reasoning) != envelope["reasoning_record_fingerprint"]:
        raise ValueError("trust decision reasoning record does not match envelope")
    if reasoning and (reasoning.get("mutation_identifier") != envelope["reasoning_fingerprint"] or reasoning.get("observation_identifier") != envelope["observation_identifier"]):
        raise ValueError("trust decision observation identity does not match reasoning")
    manifest = _optional_json(root / "final-source-manifest.json")
    if envelope["manifest_fingerprint"] is not None and (not manifest or manifest.get("manifest_fingerprint") != envelope["manifest_fingerprint"]):
        raise ValueError("trust decision manifest does not match envelope")


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
def _read(path: Path) -> dict[str, object]: return json.loads(path.read_text(encoding="utf-8"))
def _source_identity(root: str | Path) -> str: return _fingerprint({"governed_source_root": str(Path(root).resolve())})
def _optional_json(path: Path) -> dict[str, object] | None: return _read(path) if path.is_file() else None
def _atomic_write(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def _require_journal_context(journal_context: dict | None) -> dict[str, object]:
    if journal_context is None:
        raise RuntimeError("injected PlatformKeyProvider, Producer Policy Authority, immutable Producer Admission Certificate, Journal Authority, and Journal storage are required")
    required = {"platform_key_provider", "producer_policy_authority", "producer_admission_certificate", "journal_authority", "journal_storage"}
    if set(journal_context) != required or any(journal_context[name] is None for name in required):
        raise RuntimeError("incomplete authoritative Trust dependency context")
    journal = journal_context["journal_authority"]
    if (getattr(journal, "_storage", None) is not journal_context["journal_storage"]
            or getattr(journal, "_key_provider", None) is not journal_context["platform_key_provider"]
            or getattr(journal, "_policy_authority", None) is not journal_context["producer_policy_authority"]):
        raise RuntimeError("alternate or contradictory Journal Authority context")
    return journal_context
