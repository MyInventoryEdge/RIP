"""Safe post-classification onboarding continuation orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .classification_lifecycle import ClassificationReadiness, ClassificationRecoveryState, resume_after_classification
from .classification_integration import ClassificationIntegrationResult, integrate_persisted_classifications
from .decision_service import load_persisted_classification_decisions
from .models import ObservationMode, OrganizationContext, ReasoningCapability


@dataclass(frozen=True, slots=True)
class ResumeOrchestrationResult:
    organization_id: str
    onboarding_run_id: str
    readiness: ClassificationReadiness
    continued: bool
    message: str
    recovery: ClassificationRecoveryState | None
    integration_fingerprint: str


def resume_governed_onboarding(*, workspace: str | Path, onboarding_run_id: str) -> ResumeOrchestrationResult:
    """Consume readiness, then delegate fresh verification and advancement to lifecycle.

    No policy reconstruction, classification, or readiness evaluation occurs here.
    """
    root = Path(workspace)
    integration = integrate_persisted_classifications(workspace=root, onboarding_run_id=onboarding_run_id)
    if integration.readiness is not ClassificationReadiness.READY:
        return _result(integration, False, f"Onboarding remains paused: readiness is {integration.readiness.value}.", None)
    policy = integration.policy_history.policy
    if policy is None:
        raise ValueError("ready classification integration has no effective policy")
    context = _load_context(root, onboarding_run_id)
    decisions = load_persisted_classification_decisions(str(root), onboarding_run_id)
    try:
        recovery = resume_after_classification(context, policy, decisions=decisions)
    except RuntimeError as exc:
        return _result(
            integration, False,
            "Fresh source verification failed; completed onboarding artifacts were preserved. " + str(exc),
            None, readiness=ClassificationReadiness.STALE_SOURCE,
        )
    return _result(integration, recovery.readiness is ClassificationReadiness.READY,
                   "Fresh source verification succeeded; onboarding safely advanced." if recovery.readiness is ClassificationReadiness.READY else "Onboarding remains paused after lifecycle verification.", recovery,
                   readiness=recovery.readiness)


def _load_context(root: Path, run_id: str) -> OrganizationContext:
    path = root / "onboarding-runs" / run_id / "context.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        capability = raw["reasoning_capability"]
        return OrganizationContext(
            organization_id=raw["organization_id"], onboarding_run_id=raw["onboarding_run_id"],
            repository_path=raw["repository_path"], workspace_path=raw["workspace_path"],
            observation_mode=ObservationMode(raw["observation_mode"]),
            reasoning_capability=ReasoningCapability(**capability),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("retained onboarding context is invalid") from exc


def _result(
    integration: ClassificationIntegrationResult, continued: bool, message: str,
    recovery: ClassificationRecoveryState | None, *, readiness: ClassificationReadiness | None = None,
) -> ResumeOrchestrationResult:
    return ResumeOrchestrationResult(
        organization_id=integration.organization_id, onboarding_run_id=integration.onboarding_run_id,
        readiness=integration.readiness if readiness is None else readiness,
        continued=continued, message=message, recovery=recovery,
        integration_fingerprint=integration.fingerprint,
    )
