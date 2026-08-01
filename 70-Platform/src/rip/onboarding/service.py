"""Read-only, deterministic organization onboarding operations."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Mapping

from ..observation import ObservationSet, observe_filesystem
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


WORKSPACE_SCHEMA = "rip.organization-workspace.v1"
ONBOARDING_SCHEMA = "rip.organization-onboarding.v1"
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
    for relative in ("onboarding-runs", "audit", "reports", "cache", "indexes", "references"):
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
    resolved_run_id = run_id or _next_run_id(root / "onboarding-runs")
    run_root = root / "onboarding-runs" / resolved_run_id
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
) -> ObservationRun:
    """Observe a repository without modifying it and record only onboarding-workspace outputs."""
    if context.observation_mode is not ObservationMode.READ_ONLY:
        raise ValueError("Customer sources must remain read-only during Phase 6A")
    workspace = Path(context.workspace_path).resolve()
    repository = Path(context.repository_path).resolve()
    _assert_workspace_manifest(workspace, OrganizationWorkspace(context.organization_id, "_", str(workspace)), verify_display_name=False)
    _assert_non_overlapping(repository, workspace)
    run_root = workspace / "onboarding-runs" / context.onboarding_run_id
    if not run_root.is_dir() or _read_json(run_root / "context.json") != _payload(context):
        raise ValueError("Onboarding context is not an initialized isolated run")
    if _read_json(run_root / "state.json").get("state") == OnboardingRunState.OBSERVED.value:
        raise ValueError("Onboarding run is already complete; start a new run to observe again.")

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

    emit("repository-fingerprint-started", "Repository fingerprint started.")
    before, before_count = _repository_fingerprint(
        repository,
        progress=lambda count, path: emit("repository-fingerprint-progress", f"Repository fingerprint processed {count} entries.", (), (path,), count),
    )
    emit("repository-fingerprint-completed", f"Repository fingerprint completed after {before_count} entries.", processed_entries=before_count)
    emit("repository-observation-started", "Repository observation started.")
    observations = observe_filesystem(repository)
    root_observation = next(item for item in observations.observations if item.kind == "repository_root")
    emit(
        "repository-observation-completed",
        f"Repository observation completed with {len(observations.observations)} observed entries.",
        (root_observation.observation_id,),
        (root_observation.relative_path,),
        len(observations.observations),
    )
    emit("repository-integrity-verification-started", "Repository integrity verification started.", (root_observation.observation_id,), (root_observation.relative_path,))
    after, after_count = _repository_fingerprint(
        repository,
        progress=lambda count, path: emit("repository-integrity-verification-progress", f"Repository integrity verification processed {count} entries.", (), (path,), count),
    )
    emit(
        "repository-integrity-verification-completed",
        f"Repository integrity verification completed after {after_count} entries.",
        (root_observation.observation_id,),
        (root_observation.relative_path,),
        after_count,
    )
    if before != after:
        _write_json(run_root / "state.json", {"schema": ONBOARDING_SCHEMA, "state": OnboardingRunState.INTERRUPTED.value})
        _append_audit(workspace, "repository-change-detected", {"run_id": context.onboarding_run_id})
        raise RuntimeError("Repository changed during read-only observation; no onboarding result was accepted.")

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
    _write_json(run_root / "state.json", {"schema": ONBOARDING_SCHEMA, "state": OnboardingRunState.OBSERVED.value})
    _append_audit(workspace, "repository-observed", {"run_id": context.onboarding_run_id, "repository_fingerprint": before, "audit_fingerprint": result.audit_fingerprint})
    return result


def current_repository_fingerprint(context: OrganizationContext) -> str:
    """Read-only source freshness check for a completed onboarding observation."""
    if context.observation_mode is not ObservationMode.READ_ONLY:
        raise ValueError("Customer sources must remain read-only during onboarding")
    repository = Path(context.repository_path).resolve()
    workspace = Path(context.workspace_path).resolve()
    _assert_non_overlapping(repository, workspace)
    value, _ = _repository_fingerprint(repository)
    return value


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
    entries: list[tuple[str, str, str]] = []
    count = 0
    for path in _walk_paths(root):
        relative = path.relative_to(root).as_posix()
        try:
            if path.is_symlink():
                entries.append((relative, "symlink", os.readlink(path)))
            elif path.is_file():
                entries.append((relative, "file", hashlib.sha256(path.read_bytes()).hexdigest()))
        except OSError as exc:
            entries.append((relative, "access-error", type(exc).__name__))
        count += 1
        if progress:
            progress(count, relative)
    return fingerprint(entries), count


def _walk_paths(root: Path):
    def walk(directory: Path):
        try:
            children = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError:
            return
        for path in children:
            yield path
            if path.is_dir() and not path.is_symlink():
                yield from walk(path)

    yield from walk(root)


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
    audit_path = workspace_root / "audit" / "audit.json"
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
