# RIP 6.0 — Phase 6B Guided Organizational Understanding

## Purpose and Boundary

Phase 6B turns evidence-backed uncertainty from a completed, read-only Phase 6A observation into a deterministic guided interview. It is an onboarding-workspace capability only. It does not create governance, Organizational Memory, approval, activation, provider reasoning, or customer-repository changes.

## Inputs and Outputs

The only source input is a completed `ObservationRun`, including its repository fingerprint, understanding meter, and evidence references. `GuidedQuestion` records the observed evidence, reason for asking, uncertainty resolved, and the understanding change that an answer could support. Questions are generated solely from non-observed Phase 6A dimensions; there are no hidden defaults or semantic/provider calls.

`GuidedAnswerRecord` is append-only supplied knowledge. It identifies the respondent, stated role, authority claim, disposition, source fingerprint, and any prior record it supersedes. A supplied answer remains supplied knowledge even when the respondent claims authority.

`GuidedUnderstandingState` is run-scoped and persisted at `onboarding-runs/<run>/guided-understanding.json`. Reopening a current run resumes its exact questions and immutable answer history. A new Phase 6A run is the reset boundary.

## Determinism and Priority

Authority gaps produce a critical authority-identification question. Other signal or unknown dimensions produce confirmation questions with fixed priority: critical authority, high mission/products/decision history, then standard remaining dimensions. Ordering is priority, case-folded dimension, and stable resolution key. Resolution keys suppress duplicate questions.

Conflicting effective answers from different respondents produce an explicit critical contradiction question. RIP preserves both supplied records; it never chooses a winner. Authority gaps and contradictions make the summary `not-ready`.

## Freshness and Read-only Safety

Beginning or recording guided understanding recomputes the Phase 6A repository fingerprint using the existing read-only traversal. A mismatch rejects the operation and requires a fresh observation run. All writes are confined to the isolated RIP organization workspace. Phase 6B does not open artifact contents beyond the established fingerprint operation and does not write customer sources.

## Non-promotion Rule

No Phase 6B artifact is governance, current authority, Organizational Memory, an approval, or activation. Promotion requires later governed processes outside this phase.
