"""Read-only, deterministic organization onboarding operations."""

from __future__ import annotations

import hashlib
import json
import os
import time
import threading
import atexit
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Callable, Mapping

from ..observation import ObservationSet, observe_source_manifest
from ..paths import onboarding_run_directory, workspace_log_path
from ..mutation import MutationRule, TrustAction, interpret_mutation
from ..trust_actions import execute_trust_action
from ..architecture_metrics import record as record_architecture_metrics
from .models import (
    CapabilityReadiness,
    CapabilityValidation,
    DiscoveryFeedEvent,
    ObservationMode,
    ObservationRun,
    ObservationSummary,
    ObservationSummaryItem,
    OnboardingRunState,
    OrganizationContext,
    OrganizationWorkspace,
    ReasoningCapability,
    UnderstandingDimension,
    UnderstandingMeter,
    UnderstandingState,
    fingerprint,
)
from .source_watch import SourceChangeTracker, start_source_change_tracker


WORKSPACE_SCHEMA = "rip.organization-workspace.v1"
ONBOARDING_SCHEMA = "rip.organization-onboarding.v1"
SOURCE_MANIFEST_SCHEMA = "rip.source-manifest.v1"
INTEGRITY_DIFFERENCE_SCHEMA = "rip.source-integrity-difference.v1"
OBSERVATION_PERFORMANCE_SCHEMA = "rip.onboarding-observation-performance.v1"
SOURCE_HASH_CHUNK_BYTES = 4 * 1024 * 1024
SOURCE_HASH_WORKERS = 4
SOURCE_HASH_PENDING_MULTIPLIER = 4
OBSERVATION_PROGRESS_INTERVAL = 500


@dataclass(frozen=True, slots=True)
class _TrackedSource:
    tracker: SourceChangeTracker
    source_fingerprint: str
    metadata_fingerprint: str


_SOURCE_TRACKERS: dict[tuple[str, str, str], _TrackedSource] = {}
_SOURCE_TRACKERS_LOCK = threading.Lock()
DEFAULT_REASONING_CAPABILITIES = (
    ReasoningCapability(
        provider_id="openai",
        model="gpt-5.5",
        display_name="OpenAI guided reasoning",
        supports_governed_evidence=True,
        supports_required_context=True,
        local_configuration_present=False,
        recommendation="Recommended when OPENAI_API_KEY is configured.",
    ),
)


def recommend_reasoning_capability(
    *,
    environment: Mapping[str, str] | None = None,
    capabilities: tuple[ReasoningCapability, ...] = DEFAULT_REASONING_CAPABILITIES,
) -> ReasoningCapability:
    """Choose the first locally configured, context-capable declaration deterministically."""
    environment = os.environ if environment is None else environment
    validated = tuple(_with_configuration(item, environment) for item in capabilities)
    locally_eligible = tuple(item for item in validated if validate_reasoning_capability(item, capabilities=validated).locally_eligible_for_observation)
    if locally_eligible:
        return locally_eligible[0]
    if not validated:
        raise ValueError("at least one reasoning capability must be available")
    return validated[0]


def validate_reasoning_capability(
    capability: ReasoningCapability,
    *,
    environment: Mapping[str, str] | None = None,
    capabilities: tuple[ReasoningCapability, ...] = DEFAULT_REASONING_CAPABILITIES,
) -> CapabilityValidation:
    """Validate local configuration and declared context support; no live provider probe occurs."""
    environment = os.environ if environment is None else environment
    catalog = tuple(_with_configuration(item, environment) for item in capabilities)
    matching = next(
        (item for item in catalog if item.provider_id == capability.provider_id and item.model == capability.model),
        None,
    )
    if matching is None:
        return CapabilityValidation(capability, CapabilityReadiness.UNSUPPORTED, ("The selected provider/model is not in the approved capability catalog.",))
    reasons: list[str] = []
    if not matching.supports_governed_evidence:
        reasons.append("The selected capability cannot receive governed evidence.")
    if not matching.supports_required_context:
        reasons.append("The selected capability cannot support the required evidence context.")
    if reasons:
        return CapabilityValidation(matching, CapabilityReadiness.INSUFFICIENT_CONTEXT, tuple(reasons))
    if not matching.local_configuration_present:
        return CapabilityValidation(
            matching,
            CapabilityReadiness.LOCAL_CONFIGURATION_MISSING,
            ("Approved capability declaration found, but local configuration is not present. Live provider connectivity and model accessibility have not been verified.",),
        )
    return CapabilityValidation(
        matching,
        CapabilityReadiness.LOCAL_CONFIGURATION_PRESENT,
        ("Approved capability declaration found and local configuration is present. Live provider connectivity and model accessibility have not been verified.",),
    )


def create_organization_workspace(
    base_directory: str | Path,
    *,
    organization_id: str,
    display_name: str,
    repository_path: str | Path,
) -> OrganizationWorkspace:
    """Create or reopen one isolated RIP-controlled organization workspace."""
    base = Path(base_directory).expanduser().resolve()
    workspace = OrganizationWorkspace(organization_id, display_name, str((base / organization_id).resolve()))
    root = Path(workspace.workspace_path)
    _assert_non_overlapping(Path(repository_path).expanduser().resolve(), root)
    root.mkdir(parents=True, exist_ok=True)
    for relative in ("onboarding-runs", "audit", "Evidence", "Artifacts", "Diagnostics", "Cache", "Logs"):
        (root / relative).mkdir(exist_ok=True)
    manifest_path = root / "workspace.json"
    manifest = {"schema": WORKSPACE_SCHEMA, "organization_id": workspace.organization_id, "display_name": workspace.display_name}
    if manifest_path.exists():
        current = _read_json(manifest_path)
        if current != manifest:
            raise ValueError("organization workspace already belongs to a different organization identity")
    else:
        _write_json(manifest_path, manifest)
        _append_audit(root, "workspace-created", manifest)
    return workspace


def restart_onboarding_run(
    workspace: OrganizationWorkspace,
    *,
    repository_path: str | Path,
    reasoning_capability: ReasoningCapability,
    run_id: str | None = None,
    environment: Mapping[str, str] | None = None,
    capabilities: tuple[ReasoningCapability, ...] = DEFAULT_REASONING_CAPABILITIES,
) -> OrganizationContext:
    """Start a new, isolated run; existing runs remain immutable audit history."""
    validation = validate_reasoning_capability(
        reasoning_capability, environment=environment, capabilities=capabilities
    )
    if not validation.locally_eligible_for_observation:
        raise ValueError("Reasoning capability is not locally configured and context-capable: " + " ".join(validation.reasons))
    root = Path(workspace.workspace_path).resolve()
    _assert_workspace_manifest(root, workspace)
    repository = Path(repository_path).expanduser().resolve()
    if not repository.is_dir():
        raise FileNotFoundError(f"Repository observation target is not a directory: {repository}")
    _assert_non_overlapping(repository, root)
    runs_root = onboarding_run_directory(root, "run-placeholder").parent
    resolved_run_id = run_id or _next_run_id(runs_root)
    run_root = onboarding_run_directory(root, resolved_run_id)
    if run_root.exists():
        raise ValueError(f"Onboarding run already exists: {resolved_run_id}")
    context = OrganizationContext(
        workspace.organization_id,
        resolved_run_id,
        str(repository),
        str(root),
        ObservationMode.READ_ONLY,
        validation.capability,
    )
    run_root.mkdir(parents=True)
    _write_json(run_root / "context.json", _payload(context))
    _write_json(run_root / "state.json", {"schema": ONBOARDING_SCHEMA, "state": OnboardingRunState.CREATED.value})
    _append_audit(root, "onboarding-run-created", _payload(context))
    return context


def observe_organization(
    context: OrganizationContext,
    *,
    progress_callback: Callable[[DiscoveryFeedEvent], None] | None = None,
    mutation_rules: tuple[MutationRule, ...] = (),
    journal_context: dict[str, object] | None = None,
) -> ObservationRun:
    """Observe a repository without modifying it and record only onboarding-workspace outputs."""
    if context.observation_mode is not ObservationMode.READ_ONLY:
        raise ValueError("Customer sources must remain read-only during Phase 6A")
    workspace = Path(context.workspace_path).resolve()
    repository = Path(context.repository_path).resolve()
    _assert_workspace_manifest(workspace, OrganizationWorkspace(context.organization_id, "_", str(workspace)), verify_display_name=False)
    _assert_non_overlapping(repository, workspace)
    run_root = onboarding_run_directory(workspace, context.onboarding_run_id)
    if not run_root.is_dir() or _read_json(run_root / "context.json") != _payload(context):
        raise ValueError("Onboarding context is not an initialized isolated run")
    current_state = _read_json(run_root / "state.json").get("state")
    if current_state == OnboardingRunState.OBSERVED.value:
        raise ValueError("Onboarding run is already complete; start a new run to observe again.")
    if current_state != OnboardingRunState.CREATED.value:
        raise ValueError("Onboarding run is not ready for observation; completed, interrupted, and awaiting-classification runs must not be observed again.")

    performance_started = time.perf_counter()
    events: list[DiscoveryFeedEvent] = []

    def emit(
        event_type: str,
        message: str,
        observation_ids: tuple[str, ...] = (),
        evidence_paths: tuple[str, ...] = (),
        processed_entries: int = 0,
    ) -> None:
        event = DiscoveryFeedEvent(len(events), event_type, message, observation_ids, evidence_paths, processed_entries)
        events.append(event)
        if progress_callback:
            progress_callback(event)

    emit("repository-fingerprint-started", "Approved source baseline started.")
    _append_stage(workspace, context, "initial-fingerprint", "started", 0, ())
    initial_started = time.perf_counter()
    before_manifest = _source_manifest(
        repository,
        progress=_coalesced_manifest_progress(
            lambda count, path: emit("repository-fingerprint-progress", f"Repository fingerprint processed {count} entries. Current path: {path}", (), (path,), count)
        ),
    )
    record_architecture_metrics(run_root, traversals=1, source_reads=int(before_manifest["entry_count"]), hashes=int(before_manifest["entry_count"]), artifact_writes=1)
    initial_seconds = time.perf_counter() - initial_started
    _write_json(run_root / "initial-source-manifest.json", before_manifest)
    before, before_count = before_manifest["aggregate_fingerprint"], before_manifest["entry_count"]
    _append_stage(workspace, context, "initial-fingerprint", "completed", before_count, (before,))
    emit("repository-fingerprint-completed", f"Approved source baseline completed after {before_count} entries.", processed_entries=before_count)
    emit("repository-observation-started", "Repository observation started.")
    observation_started = time.perf_counter()
    observations = observe_source_manifest(repository, before_manifest["entries"])
    observation_seconds = time.perf_counter() - observation_started
    root_observation = next(item for item in observations.observations if item.kind == "repository_root")
    emit(
        "repository-observation-completed",
        f"Repository observation completed with {len(observations.observations)} observed entries.",
        (root_observation.observation_id,),
        (root_observation.relative_path,),
        len(observations.observations),
    )
    emit("repository-integrity-verification-started", "Source integrity verification started.", (root_observation.observation_id,), (root_observation.relative_path,))
    _append_stage(workspace, context, "integrity-verification", "started", 0, (before,))
    source_tracker = start_source_change_tracker(repository)
    verification_started = time.perf_counter()
    try:
        after_manifest = _source_manifest(
            repository,
            progress=_coalesced_manifest_progress(
                lambda count, path: emit("repository-integrity-verification-progress", f"Repository integrity verification processed {count} entries. Current path: {path}", (), (path,), count)
            ),
        )
    except BaseException:
        if source_tracker is not None:
            source_tracker.close()
        raise
    verification_seconds = time.perf_counter() - verification_started
    _write_json(run_root / "final-source-manifest.json", after_manifest)
    record_architecture_metrics(run_root, traversals=1, source_reads=int(after_manifest["entry_count"]), hashes=int(after_manifest["entry_count"]), artifact_writes=1)
    after, after_count = after_manifest["aggregate_fingerprint"], after_manifest["entry_count"]
    _append_stage(workspace, context, "integrity-verification", "completed", after_count, (after,))
    emit(
        "repository-integrity-verification-completed",
        f"Repository integrity verification completed after {after_count} entries.",
        (root_observation.observation_id,),
        (root_observation.relative_path,),
        after_count,
    )
    record_architecture_metrics(run_root, traversals=1, source_reads=int(after_manifest["entry_count"]), hashes=int(after_manifest["entry_count"]), artifact_writes=1)
    if before != after:
        if source_tracker is not None:
            source_tracker.close()
        difference = _manifest_difference(before_manifest, after_manifest)
        _write_json(run_root / "integrity-difference.json", difference)
        interpretation = interpret_mutation(difference, rules=mutation_rules)
        # This onboarding entry point is a production composition root.  The
        # context is provisioned outside Trust and passed unchanged to it.
        if journal_context is None:
            from ..platform_provisioning import load_trust_authority_context
            journal_context = load_trust_authority_context().journal_context()
        record_architecture_metrics(run_root, mutation_evaluations=1, policy_evaluations=1, trust_decisions=1, pauses=0 if interpretation.required_trust_action is TrustAction.CONTINUE else 1, automatic_continuations=1 if interpretation.required_trust_action is TrustAction.CONTINUE else 0)
        policy_contract = _mutation_policy_contract(mutation_rules)
        _write_json(run_root / "mutation-policy.json", policy_contract)
        reasoning_record = {
            "schema": "rip.mutation-reasoning.v1",
            "observation_identifier": root_observation.observation_id,
            "evidence_identifier": difference["difference_fingerprint"],
            "mutation_identifier": interpretation.fingerprint,
            "governing_policy": policy_contract,
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
            "interpretation": _payload(interpretation),
        }
        _write_json(run_root / "mutation-reasoning.json", reasoning_record)
        if interpretation.required_trust_action is TrustAction.CONTINUE:
            execute_trust_action(run_directory=run_root, interpretation=interpretation, expected_state=OnboardingRunState.CREATED.value, target_state=OnboardingRunState.OBSERVED.value,
                                 observation_identifier=root_observation.observation_id,
                                 evidence_identifiers=(str(difference["difference_fingerprint"]),), policy=policy_contract,
                                 governed_source_root=repository, organization_id=context.organization_id, run_id=context.onboarding_run_id,
                                 journal_context=journal_context)
            _append_stage(workspace, context, "mutation-interpretation", "continued", after_count, (interpretation.fingerprint, difference["difference_fingerprint"]))
            _append_audit(workspace, "mutation-interpreted", {"run_id": context.onboarding_run_id, "mutation_identifier": interpretation.fingerprint, "trust_action": interpretation.required_trust_action.value})
        else:
            execute_trust_action(run_directory=run_root, interpretation=interpretation, expected_state=OnboardingRunState.CREATED.value, target_state=OnboardingRunState.PAUSED_AFFECTED_SCOPE.value,
                                 observation_identifier=root_observation.observation_id,
                                 evidence_identifiers=(str(difference["difference_fingerprint"]),), policy=policy_contract,
                                 governed_source_root=repository, organization_id=context.organization_id, run_id=context.onboarding_run_id,
                                 journal_context=journal_context)
            _append_stage(workspace, context, "mutation-interpretation", "pause-affected-scope", after_count, (interpretation.fingerprint, difference["difference_fingerprint"]))
            _append_audit(workspace, "repository-change-detected", {"run_id": context.onboarding_run_id, "difference_fingerprint": difference["difference_fingerprint"], "mutation_identifier": interpretation.fingerprint})
            _write_observation_performance(
                run_root,
                outcome="interrupted",
                initial_seconds=initial_seconds,
                observation_seconds=observation_seconds,
                verification_seconds=verification_seconds,
                total_seconds=time.perf_counter() - performance_started,
                before_manifest=before_manifest,
                after_manifest=after_manifest,
                progress_event_count=len(events),
            )
            from .recovery import preserve_interrupted_run
            preserve_interrupted_run(workspace_root=workspace, organization_id=context.organization_id, interrupted_run_id=context.onboarding_run_id)
            raise RuntimeError("source changed; observation paused for governed review of the affected source scope. RIP preserved the exact difference and mutation reasoning.")

    if source_tracker is not None and source_tracker.healthy and not source_tracker.changed:
        metadata_fingerprint = _source_metadata_fingerprint(repository)
        if source_tracker.healthy and not source_tracker.changed:
            _register_source_tracker(context, source_tracker, str(after), metadata_fingerprint)
        else:
            source_tracker.close()
    elif source_tracker is not None:
        source_tracker.close()

    emit("evidence-classification-summary-construction", "Evidence classification and observation-summary construction started.", (root_observation.observation_id,), (root_observation.relative_path,))
    feed = _discovery_feed(observations, start_sequence=len(events))
    for event in feed:
        events.append(event)
        if progress_callback:
            progress_callback(event)
    meter = _understanding_meter(observations)
    summary = _observation_summary(observations, tuple(events), meter)
    emit("observation-run-completed", "Observation run completed; no customer-source modifications occurred.", (root_observation.observation_id,), (root_observation.relative_path,))
    result = ObservationRun(
        context,
        OnboardingRunState.OBSERVED,
        tuple(events),
        meter,
        summary,
        before,
        fingerprint({"context": _payload(context), "feed": _payload(events), "meter": _payload(meter), "summary": _payload(summary), "repository": before}),
    )
    _write_json(run_root / "observation.json", _payload(result))
    _write_json(run_root / "trusted-baseline.json", {"schema": "rip.trusted-baseline.v1", "source_fingerprint": after, "manifest_fingerprint": after_manifest["manifest_fingerprint"], "observation_fingerprint": result.audit_fingerprint})
    record_architecture_metrics(run_root, artifact_writes=2)
    # The executor already owns a mutation continuation transition.  Clean
    # observations have no trust action and complete directly.
    if before == after:
        _write_json(run_root / "state.json", {"schema": ONBOARDING_SCHEMA, "state": OnboardingRunState.OBSERVED.value})
    _append_audit(workspace, "repository-observed", {"run_id": context.onboarding_run_id, "repository_fingerprint": before, "audit_fingerprint": result.audit_fingerprint})
    _write_observation_performance(
        run_root,
        outcome="completed",
        initial_seconds=initial_seconds,
        observation_seconds=observation_seconds,
        verification_seconds=verification_seconds,
        total_seconds=time.perf_counter() - performance_started,
        before_manifest=before_manifest,
        after_manifest=after_manifest,
        progress_event_count=len(events),
    )
    return result


def continue_retained_post_integrity_run(context: OrganizationContext, *, journal_context: dict[str, object] | None = None) -> dict[str, object]:
    """Complete the one missing governed decision from retained post-integrity evidence.

    This never traverses the source, recreates a run, or overwrites retained
    manifests.  It is available only when the original observation stopped
    after persisting an integrity difference and before issuing a Trust action.
    """
    run = onboarding_run_directory(context.workspace_path, context.onboarding_run_id)
    if _read_json(run / "state.json").get("state") != OnboardingRunState.CREATED.value:
        raise ValueError("retained post-integrity continuation requires a created run")
    difference = _read_json(run / "integrity-difference.json")
    if not isinstance(difference, dict) or not isinstance(difference.get("difference_fingerprint"), str):
        raise ValueError("retained post-integrity continuation requires an integrity difference")
    interpretation = interpret_mutation(difference)
    policy_path, reasoning_path = run / "mutation-policy.json", run / "mutation-reasoning.json"
    if reasoning_path.is_file() and not policy_path.is_file():
        raise ValueError("retained mutation reasoning lacks its governing policy")
    policy = _read_json(policy_path) if policy_path.is_file() else _mutation_policy_contract(())
    if not isinstance(policy, dict) or policy.get("fingerprint") != _mutation_policy_contract(()).get("fingerprint"):
        raise ValueError("retained mutation policy is invalid or contradictory")
    root_observation_id = "obs-" + hashlib.sha256(b"filesystem\0repository_root\0.").hexdigest()[:16]
    reasoning = {
        "schema": "rip.mutation-reasoning.v1", "observation_identifier": root_observation_id,
        "evidence_identifier": difference["difference_fingerprint"], "mutation_identifier": interpretation.fingerprint,
        "governing_policy": policy, "timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "interpretation": _payload(interpretation),
    }
    if reasoning_path.is_file():
        retained_reasoning = _read_json(reasoning_path)
        if (not isinstance(retained_reasoning, dict) or retained_reasoning.get("schema") != "rip.mutation-reasoning.v1"
                or retained_reasoning.get("evidence_identifier") != difference["difference_fingerprint"]
                or retained_reasoning.get("mutation_identifier") != interpretation.fingerprint
                or retained_reasoning.get("governing_policy", {}).get("fingerprint") != policy.get("fingerprint")):
            raise ValueError("retained mutation reasoning is invalid or contradictory")
    else:
        if policy_path.is_file():
            _write_json(reasoning_path, reasoning)
        else:
            _write_json(policy_path, policy); _write_json(reasoning_path, reasoning)
    if journal_context is None:
        from ..platform_provisioning import load_trust_authority_context
        journal_context = load_trust_authority_context().journal_context()
    target = OnboardingRunState.OBSERVED.value if interpretation.required_trust_action is TrustAction.CONTINUE else OnboardingRunState.PAUSED_AFFECTED_SCOPE.value
    execute_trust_action(run_directory=run, interpretation=interpretation, expected_state=OnboardingRunState.CREATED.value,
                         target_state=target, observation_identifier=root_observation_id,
                         evidence_identifiers=(str(difference["difference_fingerprint"]),), policy=policy,
                         governed_source_root=context.repository_path, organization_id=context.organization_id,
                         run_id=context.onboarding_run_id, journal_context=journal_context)
    _append_stage(Path(context.workspace_path), context, "mutation-interpretation",
                  "continued" if target == OnboardingRunState.OBSERVED.value else "pause-affected-scope",
                  0, (interpretation.fingerprint, str(difference["difference_fingerprint"])))
    _append_audit(Path(context.workspace_path), "mutation-interpreted", {"run_id": context.onboarding_run_id, "mutation_identifier": interpretation.fingerprint, "trust_action": interpretation.required_trust_action.value})
    return {"run_id": context.onboarding_run_id, "state": target, "trust_action": interpretation.required_trust_action.value}


def current_repository_fingerprint(context: OrganizationContext) -> str:
    """Return only a freshness-authorized baseline fingerprint.

    This is the single freshness authority used by downstream consumers.  A
    missing live watcher is an explicit full-verification condition.
    """
    if context.observation_mode is not ObservationMode.READ_ONLY:
        raise ValueError("Customer sources must remain read-only during onboarding")
    run = onboarding_run_directory(context.workspace_path, context.onboarding_run_id)
    baseline = _read_json(run / "trusted-baseline.json")
    if baseline.get("schema") != "rip.trusted-baseline.v1" or not isinstance(baseline.get("source_fingerprint"), str):
        raise ValueError("no promoted trusted baseline is available")
    source = Path(context.repository_path).resolve()
    current = _source_manifest(source)
    accepted = current.get("aggregate_fingerprint") == baseline["source_fingerprint"] and current.get("manifest_fingerprint") == baseline.get("manifest_fingerprint")
    decision = {"schema": "rip.freshness-decision.v1", "organization_id": context.organization_id, "onboarding_run_id": context.onboarding_run_id, "source_root": str(source), "baseline_fingerprint": baseline["source_fingerprint"], "current_fingerprint": current.get("aggregate_fingerprint"), "accepted": accepted, "reason": "full-content-verification-required-without-healthy-watcher"}
    decision["fingerprint"] = fingerprint(decision)
    _write_json(run / "freshness-decision.json", decision)
    record_architecture_metrics(run, baseline_consumptions=1, traversals=1, source_reads=int(current["entry_count"]), hashes=int(current["entry_count"]), manifests_created=1, artifact_writes=1)
    if not accepted:
        raise RuntimeError("source changed since the governed trusted baseline; downstream work is paused")
    return str(baseline["source_fingerprint"])


def resolve_organization_workspace(workspace_root: str | Path, organization_id: str) -> Path:
    """Resolve one validated organization workspace without scanning sibling workspaces."""
    root = Path(workspace_root).expanduser().resolve()
    candidates = (root, root / organization_id)
    for candidate in candidates:
        manifest_path = candidate / "workspace.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = _read_json(manifest_path)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Organization workspace metadata is unreadable.") from exc
        if manifest.get("schema") == WORKSPACE_SCHEMA and manifest.get("organization_id") == organization_id:
            return candidate
    raise ValueError(f"Organization workspace '{organization_id}' was not found beneath the selected RIP workspace root.")


def resolve_onboarding_run_directory(
    workspace_root: str | Path, organization_id: str, onboarding_run_id: str,
) -> Path:
    """Return one retained organization-scoped onboarding run directory.

    The resolver deliberately does not discover organizations or create paths.
    It accepts either the parent workspace root or the already-scoped workspace.
    """
    if not onboarding_run_id or any(token in onboarding_run_id for token in ("/", "\\", "..")):
        raise ValueError("Onboarding run ID is invalid.")
    run = onboarding_run_directory(resolve_organization_workspace(workspace_root, organization_id), onboarding_run_id)
    if not run.is_dir():
        raise ValueError(f"Onboarding run '{onboarding_run_id}' was not found for organization '{organization_id}'.")
    return run


def _source_tracker_key(context: OrganizationContext) -> tuple[str, str, str]:
    return (
        str(Path(context.workspace_path).resolve()),
        context.onboarding_run_id,
        str(Path(context.repository_path).resolve()),
    )


def _register_source_tracker(
    context: OrganizationContext,
    tracker: SourceChangeTracker,
    source_fingerprint: str,
    metadata_fingerprint: str,
) -> None:
    key = _source_tracker_key(context)
    with _SOURCE_TRACKERS_LOCK:
        previous = _SOURCE_TRACKERS.pop(key, None)
        _SOURCE_TRACKERS[key] = _TrackedSource(tracker, source_fingerprint, metadata_fingerprint)
    if previous is not None and previous.tracker is not tracker:
        previous.tracker.close()


def _tracked_source_fingerprint(context: OrganizationContext) -> str | None:
    key = _source_tracker_key(context)
    with _SOURCE_TRACKERS_LOCK:
        tracked = _SOURCE_TRACKERS.get(key)
    if tracked is None:
        return None
    if tracked.tracker.healthy and not tracked.tracker.changed:
        current_metadata = _source_metadata_fingerprint(Path(context.repository_path).resolve())
        if (
            tracked.tracker.healthy
            and not tracked.tracker.changed
            and current_metadata == tracked.metadata_fingerprint
        ):
            return tracked.source_fingerprint
    with _SOURCE_TRACKERS_LOCK:
        if _SOURCE_TRACKERS.get(key) is tracked:
            _SOURCE_TRACKERS.pop(key, None)
    tracked.tracker.close()
    return None


def _close_source_trackers() -> None:
    with _SOURCE_TRACKERS_LOCK:
        tracked = tuple(_SOURCE_TRACKERS.values())
        _SOURCE_TRACKERS.clear()
    for item in tracked:
        item.tracker.close()


atexit.register(_close_source_trackers)


def _with_configuration(capability: ReasoningCapability, environment: Mapping[str, str]) -> ReasoningCapability:
    if capability.provider_id != "openai":
        return capability
    return ReasoningCapability(
        capability.provider_id,
        capability.model,
        capability.display_name,
        capability.supports_governed_evidence,
        capability.supports_required_context,
        bool(environment.get("OPENAI_API_KEY")),
        capability.recommendation,
    )


def _discovery_feed(observations: ObservationSet, *, start_sequence: int) -> tuple[DiscoveryFeedEvent, ...]:
    files = tuple(item for item in observations.observations if item.kind not in {"directory", "repository_root"})
    root = next(item for item in observations.observations if item.kind == "repository_root")
    events: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = [
        ("repository-discovered", "Repository observation scope established.", (root.observation_id,), (root.relative_path,)),
    ]
    _event_for_matches(events, "architecture-signals-detected", "Architecture signals detected from source and project artifacts; organizational architecture requires confirmation.", files, lambda item: item.kind in {"python_source_file", "python_project_manifest", "project_manifest", "solution_manifest"})
    _event_for_matches(events, "product-signals-detected", "Project manifest signals detected; product identity requires confirmation.", files, lambda item: item.kind in {"python_project_manifest", "project_manifest", "solution_manifest"})
    _event_for_matches(events, "documentation-located", "Documentation artifacts located.", files, lambda item: item.kind == "markdown_file")
    _event_for_matches(events, "decision-record-signals-detected", "Decision or ADR filename signals detected; decision authority requires confirmation.", files, lambda item: any(token in item.relative_path.casefold() for token in ("adr", "decision", "evolution")))
    _event_for_matches(events, "deployment-manifest-signals-detected", "Deployment manifest signals detected; deployment meaning requires confirmation.", files, lambda item: item.kind == "container_build_file" or any(token in item.relative_path.casefold() for token in ("deploy", "docker", "compose", "kubernetes")))
    governance = tuple(item for item in files if any(token in item.relative_path.casefold() for token in ("governance", "constitution", "policy")))
    if not governance:
        events.append(("unknown-governance", "No governance-related artifact names were detected; organizational authority remains unknown.", (root.observation_id,), (root.relative_path,)))
    return tuple(DiscoveryFeedEvent(start_sequence + index, *event) for index, event in enumerate(events))


def _event_for_matches(events, event_type: str, message: str, files, predicate) -> None:
    matches = tuple(item for item in files if predicate(item))
    if matches:
        events.append((event_type, message, tuple(item.observation_id for item in matches), tuple(item.relative_path for item in matches)))


def _understanding_meter(observations: ObservationSet) -> UnderstandingMeter:
    files = tuple(item for item in observations.observations if item.kind not in {"directory", "repository_root"})
    root = next(item for item in observations.observations if item.kind == "repository_root")
    dimensions = (
        _dimension("Repositories", "Repository observation scope is established.", (root,), UnderstandingState.OBSERVED),
        _dimension("Products", "Project-manifest signals were detected; product identity requires customer confirmation.", tuple(item for item in files if item.kind in {"python_project_manifest", "project_manifest", "solution_manifest"}), UnderstandingState.SIGNALS_DETECTED),
        _dimension("Architecture", "Source and project-artifact signals were detected; organizational architecture requires customer confirmation.", tuple(item for item in files if item.kind in {"python_source_file", "python_project_manifest", "project_manifest", "solution_manifest"}), UnderstandingState.SIGNALS_DETECTED),
        _dimension("Documentation", "Documentation artifacts were observed.", tuple(item for item in files if item.kind == "markdown_file"), UnderstandingState.OBSERVED),
        _dimension("Mission", "Mission-related filename signals were detected; organizational mission requires customer confirmation.", tuple(item for item in files if "mission" in item.relative_path.casefold()), UnderstandingState.SIGNALS_DETECTED),
        _dimension("Authority", "Governance-related filename signals were detected; organizational authority requires customer confirmation.", tuple(item for item in files if any(token in item.relative_path.casefold() for token in ("governance", "constitution", "policy"))), UnderstandingState.SIGNALS_DETECTED),
        _dimension("Decision History", "Decision or ADR filename signals were detected; decision history requires customer confirmation.", tuple(item for item in files if any(token in item.relative_path.casefold() for token in ("adr", "decision", "evolution"))), UnderstandingState.SIGNALS_DETECTED),
        _dimension("Knowledge Domains", "Knowledge or reference filename signals were detected; domain meaning requires customer confirmation.", tuple(item for item in files if any(token in item.relative_path.casefold() for token in ("knowledge", "reference", "archive"))), UnderstandingState.SIGNALS_DETECTED),
    )
    return UnderstandingMeter(dimensions, fingerprint(_payload(dimensions)))


def _dimension(name: str, explanation: str, evidence, found_state: UnderstandingState) -> UnderstandingDimension:
    if evidence:
        return UnderstandingDimension(name, found_state, tuple(item.observation_id for item in evidence), tuple(item.relative_path for item in evidence), explanation)
    return UnderstandingDimension(name, UnderstandingState.UNKNOWN, (), (), f"{name} remains unknown from the approved repository observation scope.")


def _observation_summary(observations: ObservationSet, feed: tuple[DiscoveryFeedEvent, ...], meter: UnderstandingMeter) -> ObservationSummary:
    root = next(item for item in observations.observations if item.kind == "repository_root")
    observed = (ObservationSummaryItem(UnderstandingState.OBSERVED, f"Repository observation completed: {len(observations.observations)} deterministic observations recorded.", (root.observation_id,), (root.relative_path,)),)
    discovered = tuple(ObservationSummaryItem(UnderstandingState.SIGNALS_DETECTED, event.message, event.observation_ids, event.evidence_paths) for event in feed if event.event_type.endswith("signals-detected"))
    unknown = tuple(ObservationSummaryItem(UnderstandingState.UNKNOWN, dimension.explanation, dimension.observation_ids, dimension.evidence_paths) for dimension in meter.dimensions if dimension.state is UnderstandingState.UNKNOWN)
    unknown += tuple(ObservationSummaryItem(UnderstandingState.UNKNOWN, event.message, event.observation_ids, event.evidence_paths) for event in feed if event.event_type == "unknown-governance")
    confirmation = tuple(ObservationSummaryItem(UnderstandingState.REQUIRES_CONFIRMATION, dimension.explanation, dimension.observation_ids, dimension.evidence_paths) for dimension in meter.dimensions if dimension.state is UnderstandingState.SIGNALS_DETECTED)
    payload = {"observed": _payload(observed), "discovered": _payload(discovered), "unknown": _payload(unknown), "requires_confirmation": _payload(confirmation)}
    return ObservationSummary(observed, discovered, unknown, confirmation, fingerprint(payload))


def _repository_fingerprint(root: Path, *, progress: Callable[[int, str], None] | None = None) -> tuple[str, int]:
    manifest = _source_manifest(root, progress=progress)
    return str(manifest["aggregate_fingerprint"]), int(manifest["entry_count"])


def _source_manifest(
    root: Path,
    *,
    progress: Callable[[int, str], None] | None = None,
    activity: Callable[[str], None] | None = None,
) -> dict[str, object]:
    paths = _walk_paths(root)
    entries: list[dict[str, object]] = []
    counts = {"file": 0, "directory": 0, "symlink": 0, "reparse-point": 0, "access-error": 0}
    total_bytes = 0
    entry_reader = partial(_source_manifest_entry, root, activity=activity)
    for count, (path, entry) in enumerate(
        _bounded_ordered_map(entry_reader, paths, max_workers=SOURCE_HASH_WORKERS),
        1,
    ):
        size = entry["size"]
        if entry["kind"] == "file" and isinstance(size, int):
            total_bytes += size
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
        entries.append(entry)
        if progress:
            progress(count, path.relative_to(root).as_posix())
    semantic = {"schema": SOURCE_MANIFEST_SCHEMA, "entries": entries, "counts": counts, "total_readable_bytes": total_bytes}
    aggregate_entries = [(item["path"], item["kind"], item["value"]) for item in entries if item["kind"] != "directory"]
    return {**semantic, "entry_count": len(entries), "aggregate_fingerprint": fingerprint(aggregate_entries), "manifest_fingerprint": fingerprint(semantic)}


def _source_manifest_entry(
    root: Path,
    path: Path,
    *,
    activity: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, object]]:
    relative = path.relative_to(root).as_posix()
    if activity is not None:
        activity(relative)
    try:
        if _is_reparse_point(path):
            target = os.readlink(path) if path.is_symlink() else "windows-reparse-point"
            entry = {"path": relative, "kind": "reparse-point", "value": target, "size": None}
        elif path.is_symlink():
            entry = {"path": relative, "kind": "symlink", "value": os.readlink(path), "size": None}
        elif path.is_file():
            size = path.stat().st_size
            entry = {"path": relative, "kind": "file", "value": _sha256_file(path), "size": size}
        elif path.is_dir():
            entry = {"path": relative, "kind": "directory", "value": None, "size": None}
        else:
            entry = {"path": relative, "kind": "access-error", "value": "unsupported", "size": None}
    except OSError as exc:
        entry = {"path": relative, "kind": "access-error", "value": type(exc).__name__, "size": None}
    return path, entry


def _source_metadata_fingerprint(root: Path) -> str:
    """Create a fast deterministic state signal; content trust remains SHA-256."""
    entries: list[tuple[object, ...]] = []
    for path in _walk_paths(root):
        relative = path.relative_to(root).as_posix()
        try:
            stat = path.stat(follow_symlinks=False)
            if path.is_symlink():
                entries.append((relative, "symlink", os.readlink(path), stat.st_mtime_ns, stat.st_ino))
            elif path.is_file():
                entries.append((relative, "file", stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino))
            elif path.is_dir():
                entries.append((relative, "directory", stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino))
            else:
                entries.append((relative, "unsupported", stat.st_mtime_ns, stat.st_ino))
        except OSError as exc:
            entries.append((relative, "access-error", type(exc).__name__))
    return fingerprint(entries)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    buffer = bytearray(SOURCE_HASH_CHUNK_BYTES)
    view = memoryview(buffer)
    with path.open("rb", buffering=0) as source:
        while count := source.readinto(buffer):
            digest.update(view[:count])
    return digest.hexdigest()


def _bounded_ordered_map(function, values, *, max_workers: int):
    """Yield bounded parallel results in input order for deterministic manifests."""
    iterator = iter(values)
    pending = deque()
    limit = max_workers * SOURCE_HASH_PENDING_MULTIPLIER
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="rip-source-hash") as executor:
        for _ in range(limit):
            try:
                pending.append(executor.submit(function, next(iterator)))
            except StopIteration:
                break
        while pending:
            yield pending.popleft().result()
            try:
                pending.append(executor.submit(function, next(iterator)))
            except StopIteration:
                pass


def _coalesced_manifest_progress(
    callback: Callable[[int, str], None],
) -> Callable[[int, str], None]:
    """Keep truthful progress visible without retaining one event per path."""
    def report(count: int, path: str) -> None:
        if count == 1 or count % OBSERVATION_PROGRESS_INTERVAL == 0:
            callback(count, path)

    return report


def _write_observation_performance(
    run_root: Path,
    *,
    outcome: str,
    initial_seconds: float,
    observation_seconds: float,
    verification_seconds: float,
    total_seconds: float,
    before_manifest: Mapping[str, object],
    after_manifest: Mapping[str, object],
    progress_event_count: int,
) -> None:
    """Persist operational timing separately from deterministic evidence."""
    payload = {
        "schema": OBSERVATION_PERFORMANCE_SCHEMA,
        "outcome": outcome,
        "hash_algorithm": "sha256",
        "hash_chunk_bytes": SOURCE_HASH_CHUNK_BYTES,
        "hash_workers": SOURCE_HASH_WORKERS,
        "progress_interval_entries": OBSERVATION_PROGRESS_INTERVAL,
        "verification_method": "independent-full-content-before-and-after",
        "initial_manifest_seconds": round(initial_seconds, 6),
        "observation_projection_seconds": round(observation_seconds, 6),
        "integrity_verification_seconds": round(verification_seconds, 6),
        "total_seconds": round(total_seconds, 6),
        "initial_entry_count": before_manifest["entry_count"],
        "final_entry_count": after_manifest["entry_count"],
        "initial_readable_bytes": before_manifest["total_readable_bytes"],
        "final_readable_bytes": after_manifest["total_readable_bytes"],
        "progress_event_count": progress_event_count,
    }
    _write_json(run_root / "observation-performance.json", payload)


def _manifest_difference(before: dict[str, object], after: dict[str, object]) -> dict[str, object]:
    left = {item["path"]: item for item in before["entries"]}; right = {item["path"]: item for item in after["entries"]}
    added = tuple(sorted(set(right) - set(left))); removed = tuple(sorted(set(left) - set(right)))
    modified = tuple(sorted(path for path in set(left) & set(right) if left[path]["kind"] == right[path]["kind"] == "file" and left[path]["value"] != right[path]["value"]))
    kind_changed = tuple(sorted(path for path in set(left) & set(right) if left[path]["kind"] != right[path]["kind"]))
    access_changed = tuple(sorted(path for path in set(left) & set(right) if "access-error" in {left[path]["kind"], right[path]["kind"]} and left[path] != right[path]))
    payload = {"schema": INTEGRITY_DIFFERENCE_SCHEMA, "added_paths": added, "removed_paths": removed, "modified_content_paths": modified, "kind_changed_paths": kind_changed, "access_state_changed_paths": access_changed, "initial_entry_count": before["entry_count"], "final_entry_count": after["entry_count"], "initial_fingerprint": before["aggregate_fingerprint"], "final_fingerprint": after["aggregate_fingerprint"]}
    return {**payload, "difference_fingerprint": fingerprint(payload)}


def _mutation_policy_contract(rules: tuple[MutationRule, ...]) -> dict[str, object]:
    """Persist the runtime policy that authorized a mutation decision."""
    declared = _payload(rules)
    body = {"rules": declared, "authority": "RIP platform runtime", "precedence": 100}
    return {"policy_identifier": "mutation-policy-" + fingerprint(body)[:24], "version": "1", **body, "fingerprint": fingerprint(body)}


def _append_stage(workspace: Path, context: OrganizationContext, stage: str, state: str, processed: int, references: tuple[str, ...]) -> None:
    path = onboarding_run_directory(workspace, context.onboarding_run_id) / "stages.json"
    records = _read_json(path) if path.exists() else []
    record = {"run_id": context.onboarding_run_id, "stage": stage, "state": state, "operational_timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(), "processed_entry_count": processed, "references": list(references)}
    _write_json(path, [*records, record])


def _walk_paths(root: Path):
    root = root.resolve()
    def walk(directory: Path):
        try:
            with os.scandir(directory) as entries:
                classified = tuple(
                    (Path(entry.path), entry.is_dir(follow_symlinks=False), _is_reparse_point(Path(entry.path)))
                    for entry in entries
                )
            children = sorted(classified, key=lambda item: (not item[1], item[0].name.casefold()))
        except OSError:
            return
        for path, is_directory, is_reparse in children:
            yield path
            if is_directory and not is_reparse:
                yield from walk(path)

    yield from walk(root)


def _is_reparse_point(path: Path) -> bool:
    """Windows junctions are reparse points even when Path.is_symlink is false."""
    try:
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
        return path.is_symlink() or bool(attributes & 0x400)
    except OSError:
        return True


def _assert_non_overlapping(repository: Path, workspace: Path) -> None:
    if repository == workspace or repository in workspace.parents or workspace in repository.parents:
        raise ValueError("Organization workspace must not be inside, contain, or equal the observed repository.")


def _next_run_id(runs_root: Path) -> str:
    existing = {path.name for path in runs_root.iterdir() if path.is_dir()} if runs_root.is_dir() else set()
    index = 1
    while f"run-{index:03d}" in existing:
        index += 1
    return f"run-{index:03d}"


def _assert_workspace_manifest(root: Path, workspace: OrganizationWorkspace, *, verify_display_name: bool = True) -> None:
    manifest = _read_json(root / "workspace.json")
    if manifest.get("schema") != WORKSPACE_SCHEMA or manifest.get("organization_id") != workspace.organization_id:
        raise ValueError("Organization workspace identity could not be verified")
    if verify_display_name and manifest.get("display_name") != workspace.display_name:
        raise ValueError("Organization workspace display name does not match its established identity")


def _append_audit(workspace_root: Path, operation: str, payload: object) -> None:
    audit_path = workspace_log_path(workspace_root)
    existing = _read_json(audit_path) if audit_path.exists() else []
    record = {"sequence": len(existing), "operation": operation, "payload": payload, "fingerprint": fingerprint(payload)}
    _write_json(audit_path, [*existing, record])


def _payload(value: object) -> object:
    if isinstance(value, tuple):
        return [_payload(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _payload(asdict(value))
    if isinstance(value, dict):
        return {key: _payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_payload(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)
