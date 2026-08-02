# RIP 6.0 — Phase 6C Evidence-Based Organizational Understanding Proposal

## Boundary

Phase 6C creates an immutable, run-scoped, non-authoritative proposal from a completed Phase 6A observation, effective Phase 6B supplied answers, and explicit confirmed interpretations. It does not create governance, approval, authority, Organizational Memory, activation, provider reasoning, or customer-source writes.

## Engineering Model

`OrganizationalUnderstandingProposal` has deterministic semantic identity, ordered non-empty sections, statement-level provenance, readiness reasons and blockers, and a lifecycle of generated, reviewed, stale, superseded, or withdrawn. `generated_at` is audit metadata and is excluded from the semantic fingerprint.

Every `ProposedUnderstandingStatement` has a bounded type, epistemic label, normalized subject, and `StatementProvenance`. Provenance contains observation, effective-answer, confirmed-interpretation, uncertainty, contradiction, and deterministic-rule references. No provenance reference is AI reasoning.

`ConfirmedInterpretation` is explicit and non-authoritative. It requires a current source snapshot, a relevant question and answered records, observation references, accepted onboarding authority category, and no material contradiction. `WithdrawalRecord` is immutable and marks an answer or interpretation non-effective without deleting history.

## Determinism and Readiness

Sections follow the approved fixed order and empty unsupported sections are omitted. Statements sort by epistemic label, normalized subject, provenance fingerprint, and identifier. Unknowns, contradictions, and authority gaps remain visible.

Readiness is Preliminary, Evidence Complete, Human Review Required, or Governance Draft Ready. Each result has explicit reasons and blockers. Governance Draft Ready only identifies suitability for a later drafting phase; it neither drafts nor authorizes governance.

## Experience Layer

Internal contracts use precise engineering names and enums. The console maps them to customer-facing labels such as “Direct observation” and “Customer-supplied knowledge”; raw enum values are not rendered. The proposal inspector presents section, statement, epistemic label, and exact provenance under “Why do you believe this?” It always discloses that the proposal is not governance, Organizational Memory, approval, or activation.

## Persistence and Future Capture

The proposal is persisted only beneath the isolated onboarding run. It is an immutable evidence-backed snapshot suitable for a future Capture Understanding capability, but no automatic Organizational Memory promotion occurs. Source freshness is checked before generation; stale source state is rejected rather than reinterpreted.
