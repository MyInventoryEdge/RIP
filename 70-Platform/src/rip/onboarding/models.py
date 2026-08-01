"""Immutable contracts for trust-first, read-only organization onboarding."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import Enum


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class ObservationMode(str, Enum):
    READ_ONLY = "read-only"


class OnboardingRunState(str, Enum):
    CREATED = "created"
    OBSERVED = "observed"
    INTERRUPTED = "interrupted"


class CapabilityReadiness(str, Enum):
    LOCAL_CONFIGURATION_PRESENT = "local-configuration-present"
    LOCAL_CONFIGURATION_MISSING = "local-configuration-missing"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_CONTEXT = "insufficient-context"


class UnderstandingState(str, Enum):
    OBSERVED = "observed"
    SIGNALS_DETECTED = "signals-detected"
    UNKNOWN = "unknown"
    REQUIRES_CONFIRMATION = "requires-confirmation"


class GuidedQuestionType(str, Enum):
    CONFIRM_INTERPRETATION = "confirm-interpretation"
    IDENTIFY_AUTHORITY = "identify-authority"
    RESOLVE_CONTRADICTION = "resolve-contradiction"


class GuidedQuestionPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    STANDARD = "standard"


class GuidedAnswerDisposition(str, Enum):
    ANSWERED = "answered"
    DEFERRED = "deferred"
    UNKNOWN = "unknown"
    NOT_AUTHORIZED = "not-authorized"


class GuidedUnderstandingStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class GuidedQuestion:
    """An evidence-backed uncertainty; it is not a governance request or conclusion."""

    question_id: str
    dimension: str
    question_type: GuidedQuestionType
    priority: GuidedQuestionPriority
    prompt: str
    observed: str
    why_this_question: str
    uncertainty_resolved: str
    understanding_change: str
    evidence_paths: tuple[str, ...]
    observation_ids: tuple[str, ...]
    resolution_key: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not all((self.question_id, self.dimension, self.prompt, self.observed, self.why_this_question, self.uncertainty_resolved, self.understanding_change, self.resolution_key)):
            raise ValueError("guided questions require explicit evidence, uncertainty, and resolution purpose")


@dataclass(frozen=True, slots=True)
class GuidedAnswerRecord:
    """Immutable supplied knowledge, retained separately from governance and memory."""

    answer_id: str
    question_id: str
    sequence: int
    respondent_identity: str
    respondent_role: str
    authority_claim: str
    disposition: GuidedAnswerDisposition
    answer: str
    supersedes_answer_id: str | None
    source_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        if self.sequence < 0 or not all((self.answer_id, self.question_id, self.respondent_identity, self.authority_claim, self.source_fingerprint, self.fingerprint)):
            raise ValueError("guided answer records require immutable identity, source, and respondent provenance")
        if self.disposition is GuidedAnswerDisposition.ANSWERED and not self.answer.strip():
            raise ValueError("answered guided records require supplied answer text")


@dataclass(frozen=True, slots=True)
class GuidedUnderstandingSummary:
    total_questions: int
    answered_questions: int
    unresolved_questions: int
    authority_gaps: int
    contradictions: int
    readiness: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class GuidedUnderstandingState:
    """Run-scoped working understanding. It never promotes supplied answers to authority or memory."""

    organization_id: str
    onboarding_run_id: str
    source_fingerprint: str
    status: GuidedUnderstandingStatus
    questions: tuple[GuidedQuestion, ...]
    answer_history: tuple[GuidedAnswerRecord, ...]
    summary: GuidedUnderstandingSummary
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ReasoningCapability:
    """A replaceable reasoning capability declaration; it is never organization identity."""

    provider_id: str
    model: str
    display_name: str
    supports_governed_evidence: bool
    supports_required_context: bool
    local_configuration_present: bool
    recommendation: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_id or not self.model or not self.display_name:
            raise ValueError("reasoning capability identity is required")


@dataclass(frozen=True, slots=True)
class CapabilityValidation:
    capability: ReasoningCapability
    readiness: CapabilityReadiness
    reasons: tuple[str, ...]

    @property
    def locally_eligible_for_observation(self) -> bool:
        """Local configuration and declared context capability only; no live probe occurred."""
        return self.readiness is CapabilityReadiness.LOCAL_CONFIGURATION_PRESENT


@dataclass(frozen=True, slots=True)
class OrganizationWorkspace:
    organization_id: str
    display_name: str
    workspace_path: str

    def __post_init__(self) -> None:
        _validate_identifier(self.organization_id, "organization")
        if not self.display_name.strip() or not self.workspace_path:
            raise ValueError("organization workspace identity is required")


@dataclass(frozen=True, slots=True)
class OrganizationContext:
    """Explicit organization and onboarding-run scope; no ambient organization is permitted."""

    organization_id: str
    onboarding_run_id: str
    repository_path: str
    workspace_path: str
    observation_mode: ObservationMode
    reasoning_capability: ReasoningCapability

    def __post_init__(self) -> None:
        _validate_identifier(self.organization_id, "organization")
        _validate_identifier(self.onboarding_run_id, "onboarding run")
        if not self.repository_path or not self.workspace_path:
            raise ValueError("organization context requires repository and workspace paths")
        if self.observation_mode is not ObservationMode.READ_ONLY:
            raise ValueError("Phase 6A supports read-only observation mode only")


@dataclass(frozen=True, slots=True)
class DiscoveryFeedEvent:
    sequence: int
    event_type: str
    message: str
    observation_ids: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    processed_entries: int = 0

    def __post_init__(self) -> None:
        if self.sequence < 0 or self.processed_entries < 0 or not self.event_type or not self.message:
            raise ValueError("discovery event identity is required")


@dataclass(frozen=True, slots=True)
class UnderstandingDimension:
    name: str
    state: UnderstandingState
    observation_ids: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    explanation: str

    def __post_init__(self) -> None:
        if not self.name or not self.explanation:
            raise ValueError("understanding dimensions require a name and explanation")


@dataclass(frozen=True, slots=True)
class UnderstandingMeter:
    dimensions: tuple[UnderstandingDimension, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        if len(self.fingerprint) != 64 or any(char not in "0123456789abcdef" for char in self.fingerprint):
            raise ValueError("understanding meter fingerprint must be SHA-256")
        if len({item.name for item in self.dimensions}) != len(self.dimensions):
            raise ValueError("understanding dimensions must be unique")


@dataclass(frozen=True, slots=True)
class ObservationSummaryItem:
    state: UnderstandingState
    statement: str
    observation_ids: tuple[str, ...]
    evidence_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.statement:
            raise ValueError("observation summary statements are required")


@dataclass(frozen=True, slots=True)
class ObservationSummary:
    observed: tuple[ObservationSummaryItem, ...]
    discovered: tuple[ObservationSummaryItem, ...]
    unknown: tuple[ObservationSummaryItem, ...]
    requires_confirmation: tuple[ObservationSummaryItem, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        if len(self.fingerprint) != 64 or any(char not in "0123456789abcdef" for char in self.fingerprint):
            raise ValueError("observation summary fingerprint must be SHA-256")


@dataclass(frozen=True, slots=True)
class ObservationRun:
    context: OrganizationContext
    state: OnboardingRunState
    discovery_feed: tuple[DiscoveryFeedEvent, ...]
    understanding_meter: UnderstandingMeter
    summary: ObservationSummary
    repository_fingerprint: str
    audit_fingerprint: str


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")
    ).hexdigest()


def serializable(value: object) -> dict[str, object]:
    return asdict(value)


def _json_default(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Cannot serialize {type(value)!r}")


def _validate_identifier(value: str, label: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} ID must be lowercase letters, digits, and hyphens (3-64 characters)")
