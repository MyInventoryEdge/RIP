# RIP 6.0 — CZ-EC-1 Evidence-Classification Contracts

## Purpose and boundary

CZ-EC-1 establishes a durable, organization- and onboarding-run-scoped vocabulary for recording human-reviewed evidence classifications. It is a contract and persistence phase only. It does not alter observation, source-integrity evaluation, onboarding state, reasoning, retrieval, providers, prompts, or the console UI.

**Classification changes interpretation, never observation.** RIP shall never conceal, delete, rewrite, or pretend it did not observe evidence. Classification affects only how observed evidence may later participate in organizational understanding and integrity evaluation.

## Immutable contracts

`ClassificationRequest` records a proposed class, treatment, normalized target, explicit scope, source-manifest fingerprint, requester provenance, rationale, and deterministic fingerprint.

`ClassificationDecision` records an approving or declining reviewer decision against one request. An approved decision must declare both the class and integrity treatment. Decisions are append-only and may identify a prior decision as superseded.

`EvidenceClassification` records an accepted classification linked to an approved decision. It remains scoped to exactly one organization and onboarding run, retains the source-manifest fingerprint, and may identify a prior classification as superseded.

`EvidenceClassificationPolicy` is an immutable, run-scoped collection of classification records. Its fingerprint covers the complete ordered contract representation. The contract rejects duplicate records and cross-organization or cross-run records.

The current evidence classes are Organizational Evidence, Operational State, Generated Artifact, Inventory Only, and Unknown. Unknown remains conservative: it can only carry `BLOCKING`. `Generated Artifact` and integrity treatment are distinct. The contracts can record an explicitly approved `NON_BLOCKING_REPORTED` generated-artifact decision, but CZ-EC-1 does not apply that decision to fingerprinting or integrity behavior.

External Reference is reserved as a future architectural concept; CZ-EC-1 implements no External Reference behavior.

## Scope representation

Contracts represent either an exact path or a future path-glob scope. Targets are persisted as normalized relative POSIX-style paths. Exact paths reject glob tokens. A path-glob accepts only `*` within one segment, `?` for one non-separator character, and `**` as a complete path segment; character classes, braces, negation, absolute paths, backslashes, empty segments, and current/parent traversal are rejected. CZ-EC-1 validates this representation only. It does not match patterns, preview broader scopes, or accept policy authority workflows; those behaviors remain deferred.

## Deterministic serialization and persistence

Contract fingerprints are SHA-256 hashes of canonical JSON: UTF-8, sorted object keys, compact separators, and enum values persisted as strings. Timestamps are caller-supplied metadata and are included when supplied; the implementation never creates implicit time values.

`serialize_contract` writes a schema envelope and canonical contract payload. `persist_contract` stores exactly one immutable JSON document below:

`<organization-workspace>/onboarding-runs/<run-id>/classifications/<requests|decisions|records|policies>/<contract-id>.json`

Rewriting the same content is idempotent. Reusing an identity with different content fails locally. The persistence API requires an explicit workspace path and contract run ID; it has no ambient organization, repository access, network access, cache, or artifact-loading behavior.

## Deferred work

CZ-EC-1 intentionally does not implement lifecycle changes, Awaiting Classification, pause/resume, integrity interpretation, dual source fingerprints, UI, attention events, recovery workflows, policy matching, broad-scope previews, or source-repository changes.
