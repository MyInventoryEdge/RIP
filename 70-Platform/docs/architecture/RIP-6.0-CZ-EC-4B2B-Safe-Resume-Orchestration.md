# CZ-EC-4B2B — Safe Resume Orchestration

Safe resume consumes the persisted classification-integration result. It only
continues when the promoted integration service reports `READY` and provides an
effective immutable policy. The orchestration layer then delegates to the
existing lifecycle resume service, which performs a fresh complete source
manifest verification against retained onboarding evidence.

If the source differs, lifecycle writes its deterministic comparison record,
marks the run interrupted, and preserves all retained immutable artifacts. The
orchestrator reports `STALE_SOURCE`; it does not classify, reconstruct policy,
or evaluate readiness itself.

If verification succeeds, lifecycle owns the sole state advancement. The
console only requests the operation and displays its result. Notification,
performance, and Phase 6D work remain deferred.
