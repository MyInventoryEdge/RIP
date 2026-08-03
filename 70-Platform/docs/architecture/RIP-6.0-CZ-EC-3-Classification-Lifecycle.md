# RIP 6.0 — CZ-EC-3 Classification Lifecycle

## Trust boundary

CZ-EC-3 introduces a durable `AWAITING_CLASSIFICATION` state only after a completed observation exists. A classification request never deletes or rewrites the initial/final manifests, diagnostics, observation result, fingerprints, or stage history.

**Classification changes interpretation, never observation.** Classification records and attention events are written only inside the organization-scoped RIP workspace. Customer repositories remain read-only.

## Pause and attention

`request_evidence_classification` creates an immutable CZ-EC-1 request, persists it under the onboarding run, writes a provider-neutral immutable attention event, and writes recovery state. The run moves from `OBSERVED` to `AWAITING_CLASSIFICATION`. Observation cannot be rerun from that state.

## Resume

Resume accepts an immutable policy and first recomputes the complete source manifest. It compares that fresh manifest to the retained final manifest before evaluating classifications. It never continues an unsafe checkpoint.

If the source differs, the run becomes `INTERRUPTED`, a resume-integrity record is retained, and all completed work remains available. If source verification succeeds, deterministic readiness is evaluated: conflicts or Unknown entries retain the awaiting state; a ready evaluation is retained and the run returns to `OBSERVED`.

## Deferred scope

This phase provides no UI, customer interaction flow, delivery provider, notification service, advanced recovery workflow, or Phase 6D behavior.
