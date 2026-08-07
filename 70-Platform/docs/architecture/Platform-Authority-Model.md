# Platform Authority Model

## Authority Definition

A Platform Authority is the sole constitutional owner of a defined class of truth. It decides or authenticates that truth, persists evidence through an approved storage boundary, and remains independently verifiable across restart, time, failure, and implementation replacement.

A service performs work; a helper computes locally; a cache accelerates retrieval; a projection presents derived state. None may redefine authoritative truth.

## Mandatory Authority Properties

- One explicit constitutional boundary and owner.
- Exclusive responsibility for its truth domain.
- Typed public contract with no arbitrary callback-defined semantics.
- Persisted, authenticated, versioned evidence.
- Deterministic behavior from declared inputs and policy.
- Clear decision, execution, evidence, and projection boundaries.
- No hidden alternate owner or bypass path.
- Explicit dependency and trust model.
- Replay-safe and restart-safe state change.
- Rebuildable projections and caches.

## Required Evidence Properties

Evidence contains schema/version, authority/operation identity, canonical input/output/policy bindings, continuity where applicable, timestamp, signing authority/key identity, signature version/signature, integrity hash, and references for independent reconstruction. Historical meaning binds the exact authority version, policy/admission state, signing key history, and predecessor evidence at issuance.

## Authority Lifecycle

`Proposed → constitutionally reviewed → admitted → implemented under evidence contract → independently verified → active → retired (verification retained) → superseded or withdrawn`

## Admission Criteria

Precise truth domain; sole-owner and non-ownership statements; public API and evidence schema; canonical signing; historical validation; failure/recovery model; projection/cache boundaries; trust dependencies; independent reconstruction; ownership targets; and constitutional regression plan.

## Retirement Criteria

Disable issuance; retain historical verification; record supersession; migrate or fail-close consumers; remove alternate owners; retain signed retirement evidence.

## Constitutional Tests for New Authorities

1. Owner singularity.
2. Schema strictness.
3. Canonical integrity.
4. Historical verification.
5. Replay resistance.
6. Crash/restart safety.
7. Tamper resistance.
8. Boundary enforcement.
9. Independent reconstruction.
10. Fail-closed operation.
