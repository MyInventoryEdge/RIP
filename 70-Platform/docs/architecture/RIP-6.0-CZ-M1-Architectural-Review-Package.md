# Customer Zero Milestone 1 — Architectural Review Package

## AO implementation update

Session 0001 obligations are implemented as platform controls: a single
fingerprinted trust-decision envelope is the sole continuation contract;
scopes are resolved and contained beneath the governed source root; paused
decisions cannot self-promote; and the Trust Action Executor records intent
before execution and completion afterwards. Classification no longer owns a
second source-verification or transition path. Preserved runs carry a complete
hash-and-size artifact inventory, migration writes durable per-artifact
checkpoints, and the primary review workflow contains no archival capture.

## Post-ARB Session 0002 authority hardening

The Trust Decision Envelope now also binds the governed source-root identity;
replay validates that identity before executing. Freshness is consumed solely
from the promoted baseline rather than recreated by guided understanding or
proposal generation. Legacy migration discovery refuses symbolic links and
escaped targets. Architectural counters provide deterministic evidence for
source traversal, hashing, reasoning, trust execution, persistence, and
baseline consumption.

## Platform behavior

RIP separates evidence collection, interpretation, and execution. Observation
persists initial/final manifests and exact differences. `rip.mutation` turns a
retained difference plus declared policy into explainable per-path reasoning.
`rip.trust_actions` persists and executes that decision. Consumers, including
onboarding continuation, replay the persisted action rather than re-reasoning.

## Operator journey

An expected non-material operational mutation continues automatically. An
unproven mutation preserves all completed artifacts, marks only its affected
scope paused, and presents a plain-language explanation: what changed, what
remains trusted, why RIP cannot decide, and the focused next action. Archival
capture is optional and outside this path. The operator can close and reopen a
preserved run without a source traversal.

## Storage and migration

`rip.paths` is the production storage authority rooted at `C:\\RIP`, with
State, Configuration, Workspace, Evidence, Artifacts, Diagnostics, Cache,
Snapshots, and Logs areas. Legacy discovery exists only in `storage_migration`.
It inventories former locations, rejects conflicts, verifies each copied file
by size and SHA-256, writes an idempotent receipt, and never deletes legacy
content automatically.

## Traversal and performance review

Initial observation performs one manifest traversal; its observation projection
reuses that manifest. The final integrity comparison is the only planned
second complete traversal. Preservation/reopen and `CONTINUE` replay perform
zero source traversals. Scoped continuation verifies only paths in
`trust-scope.json`. Full verification is an explicit executor action and may
not be selected by continuation. Existing tests instrument manifest and copy
calls to guard these counts.

## Defender guidance

The verified `C:\\RIP` Defender exclusion may improve hashing and artifact I/O
for RIP-owned data. Defender remains enabled. Never place unvalidated external
content there casually; never exclude a drive root, profile, Downloads, Temp,
or wildcard path. Inspect with `Get-MpPreference`; add/remove only through an
administrator-approved `Add-MpPreference -ExclusionPath C:\RIP` or
`Remove-MpPreference -ExclusionPath C:\RIP` operation.

## Pre-run challenge

No mutation bypasses interpretation at the onboarding difference boundary, and
no persisted continuation reinterprets it. Missing trust artifacts fall back to
the existing classification lifecycle; malformed action artifacts fail rather
than infer. At 100,000 or 1,000,000 files, planned full traversal count remains
two during observation and zero during preservation/reopen/CONTINUE replay.
Live multi-day observation still requires a future continuous-observation
policy/ownership feed to classify unknown writers; unknown evidence is scoped
paused rather than silently accepted.

## Remaining limitations and review questions

The legacy on-disk `onboarding-runs` segment is currently encapsulated by the
storage authority for migration compatibility. A future governed migration must
move it to the final named Runs area. Full-verification policy records and a
fully interactive governed-review decision screen require completion before a
production Customer Zero run. Governance Compiler and Governance Runtime are
approved post-Milestone-1 capabilities and are not implemented here.
