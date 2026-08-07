# Architectural Review Board Session 0002

## Independent Adversarial Re-Review of Customer Zero Milestone 1

**Review date:** 2026-08-04  
**Repository:** `C:\RIP`  
**Branch:** `main`  
**Reviewed HEAD:** `4455524a3e1170f2ce16d257e1d0a1f2f1f64e0f`  
**Review mode:** Independent, adversarial, read-only investigation; this report is the only repository artifact created by Session 0002.  
**Customer Zero recommendation:** **NOT AUTHORIZED**

---

## Executive Summary

The corrected Milestone 1 architecture does not deserve Customer Zero authorization.

The review independently confirmed that 180 tests pass and that `git diff --check` passes, but those results do not validate the architecture. Production tracing and temporary-directory adversarial execution established three Critical failures:

1. The trust-decision envelope and execution receipt are not authoritative integrity boundaries. A writer that can change the JSON can recompute the public checksum, change a paused action into continuation, replay the decision in another run or organization, substitute a completed receipt, and cause a transition to execute twice after a crash boundary.
2. Downstream “freshness” is a comparison against a static, unsealed `trusted-baseline.json`, not a determination of current customer-source state. Guided understanding, proposal generation, and classification continuation accept customer-source mutation after observation. The native source watcher is registered but is not consumed by any downstream freshness path.
3. The governed source root can be escaped through a Windows junction. The manifest walker treats a junction as a normal directory, recurses through it, and hashes content outside the approved root.

Six High findings additionally invalidate the claimed correction: scoped continuation performs no scoped verification and has no governed resolution journey; lifecycle transitions still have multiple owners; production storage can be redirected to arbitrary roots; preservation can seal an incomplete run; migration accepts stale or forged completed receipts and corrupted destinations; and the real operator journey has unresolved dead ends, false freshness language, a provider prerequisite for provider-free observation, and no governed migration or full-verification workflow.

Three Medium findings cover inaccurate and incomplete architecture metrics, tests that explicitly encode unsafe behavior as success, and a review package that neither enumerates AO-0001 through AO-0013 nor maps them to evidence while simultaneously acknowledging unfinished Customer Zero prerequisites.

Severity totals are:

| Severity | Open findings |
|---|---:|
| Critical | 3 |
| High | 6 |
| Medium | 3 |
| Low | 0 |

The authorization rule requires zero unresolved Critical findings and zero unresolved High findings threatening trust, source boundaries, recovery, storage singularity, or operator completion. This implementation fails each of those conditions. A long Customer Zero run would exercise known defects rather than validate a closed architecture.

---

## Review Basis and Repository Reality

The review established repository reality from the current working tree, Git status and tracked diff, all new production modules, surrounding unchanged production code, relevant tests, the constitutional corpus, the Milestone 1 review package, the stabilization plan, and the interrupted-run recovery architecture.

The worktree contained broad intentional Milestone 1 changes: 28 tracked files were modified and 15 architecture, production, and test files were untracked. Two additional untracked items were classified separately:

- `C:\RIP\State\constitutional-memory.json` is generated local RIP-owned state. It contains the eight-document constitutional memory, expected hashes and source signatures, and no structured alternate runtime root. It is runtime output, not production architecture.
- `C:\RIP\customer-zero-p0-review.patch` is a generated review patch representing an earlier change surface. It is review evidence, not production architecture.

Neither generated item was removed or treated as an implementation control.

At the end of investigation, the current Milestone 1 changes remained unstaged. `HEAD` and `origin/main` both resolved to `4455524a3e1170f2ce16d257e1d0a1f2f1f64e0f`; therefore the reviewed working-tree delta was neither committed nor ahead of the remote. No repository Customer Zero authorization artifact was found. These observations establish current state only; they do not prove that no historical remote operation ever occurred.

---

## Verification of Builder Claims

| Builder claim | Result | Independent verification |
|---|---|---|
| AO-0001 through AO-0013 are implemented. | **Rejected / not traceable** | No repository-resident AO registry, Session 0001 report, or AO-to-code/test evidence matrix was found. Multiple claimed controls are demonstrably false. See ARB2-C-001 through ARB2-M-003. |
| Production storage authority no longer accepts ambient environment authority. | **Narrowly true, architecturally false** | `RIP_STORAGE_ROOT` is ignored by `storage_root()`, but ordinary production onboarding, workspace resolution, run paths, test-style root parameters, and the UI still accept arbitrary roots. See ARB2-H-003. |
| Downstream guided/proposal freshness checks consume `trusted-baseline.json` and do not rescan customer repositories. | **Mechanically true, semantically unsafe** | Consumers read the baseline, but that baseline is unsealed and is not current-source verification. Post-observation changes are accepted. See ARB2-C-002. |
| Architecture metrics record deterministic traversal, reads, hashes, mutation, policy, trust, pause, continuation, and artifact writes. | **False** | Counters are double-counted, misclassified, and absent from major workflows. See ARB2-M-001. |
| Full suite passes: 180 tests. | **Verified with qualification** | The advertised `py -m unittest` could not run because the host launcher reported no installed Python. The bundled Python runtime, with `src` explicitly on `PYTHONPATH`, ran all 180 tests in 16.471 seconds with zero failures. Passing tests do not overcome the defects; some tests assert them as expected behavior. |
| `git diff --check` passes. | **Verified** | Exit code 0; only line-ending conversion warnings were emitted. |
| No staging, commit, push, or Customer Zero authorization occurred for this working delta. | **Verified for observable current state** | Cached diff was empty; `HEAD == origin/main`; the reviewed delta remained uncommitted; no authorization artifact was found. Historical external actions cannot be proven solely from current repository state. |

---

## Re-Test of Every ARB Session 0001 Critical Finding

The repository did not contain the original Session 0001 report or an AO register. The four critical finding categories reproduced in the Session 0002 mandate were therefore treated as the authoritative Session 0001 re-test set.

| Session 0001 finding category | Result | Session 0002 evidence |
|---|---|---|
| Trust decisions can be forged, partially written, mismatched, stale, or replayed against the wrong observation, policy, scope, or manifest. | **Still open — Critical** | Public-checksum recomputation changed pause to continue; missing timestamp and unknown fields were accepted; cross-run/cross-organization replay succeeded; policy-file disagreement and manifest-content tampering were not detected; completed receipt substitution was accepted; crash recovery repeated a transition. ARB2-C-001. |
| Scoped verification can escape the governed source root through traversal, absolute paths, symlinks, junctions, normalization, case behavior, or manifest tampering. | **Still open — Critical** | The isolated scoped helper rejects basic `..` and resolved symlink escapes, but it is unused. The production manifest walker followed a Windows junction and hashed an external file; observation projection also re-resolves an approved nested root to an ancestor repository. ARB2-C-003 and ARB2-H-001. |
| `PAUSE_AFFECTED_SCOPE` can self-promote without a new governed materiality decision. | **Still open — Critical/High** | The nominal replay branch returns `continued=False`, but the envelope can be rewritten and rechecksummed into `continue`. There is no legitimate materiality-resolution action; the UI invokes replay directly and a different decision conflicts with the existing envelope. ARB2-C-001 and ARB2-H-001. |
| Classification or another subsystem owns an alternate continuation, verification, interruption, or lifecycle path. | **Still open — High** | Classification directly writes `awaiting-classification`, supplies its own transition callback to `observed`, and resume orchestration selects between a trust-artifact branch and a classification-integration branch. ARB2-H-002. |

No Session 0001 critical category is closed.

---

## New Findings and Severity Index

| ID | Severity | Title | Status |
|---|---|---|---|
| ARB2-C-001 | Critical | Trust envelope, receipt, replay, and crash-recovery integrity are not authoritative | Open |
| ARB2-C-002 | Critical | Static trusted baseline permits stale customer evidence through every downstream stage | Open |
| ARB2-C-003 | Critical | Windows junctions escape the governed source root and are hashed as customer evidence | Open |
| ARB2-H-001 | High | Scoped continuation neither verifies scope nor offers a governed pause-resolution path | Open |
| ARB2-H-002 | High | Trust Action Executor is not the single lifecycle execution owner | Open |
| ARB2-H-003 | High | Production storage singularity can be bypassed and storage topology has duplicate owners | Open |
| ARB2-H-004 | High | Preservation seals existence rather than lifecycle completeness and recovery is incomplete | Open |
| ARB2-H-005 | High | Storage migration is not transactionally receipt-bound, resumable, or revalidated | Open |
| ARB2-H-006 | High | Operator journey contains dead ends, false claims, and missing required workflows | Open |
| ARB2-M-001 | Medium | Architecture metrics are inaccurate, incomplete, and sometimes double-counted | Open |
| ARB2-M-002 | Medium | Passing tests encode acknowledged defects and omit decisive adversarial cases | Open |
| ARB2-M-003 | Medium | AO traceability is absent and the review package self-identifies unfinished prerequisites | Open |

---

## Critical Findings

### ARB2-C-001 — Trust envelope, receipt, replay, and crash-recovery integrity are not authoritative

**Severity:** Critical  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/trust_actions.py:41-54` constructs an envelope without organization ID, onboarding run ID, governed source-root identity, trusted-baseline identity, an expiration or monotonic sequence, or execution result. `created_at` and `execution_status` are expressly excluded from its fingerprint.
- `70-Platform/src/rip/trust_actions.py:54` and `139-140` use an ordinary SHA-256 of writer-controlled JSON. The checksum authenticates no actor or storage authority; any writer capable of editing the envelope can calculate the replacement checksum.
- `70-Platform/src/rip/trust_actions.py:121-130` uses a required-subset check rather than an exact schema. `created_at` is not required, unknown fields are not rejected, and policy validation checks only four embedded keys rather than an authoritative external policy fingerprint.
- `70-Platform/src/rip/trust_actions.py:131-136` validates reasoning only when a reasoning file happens to exist and validates only the manifest’s stored `manifest_fingerprint` label, not the manifest’s canonical content.
- `70-Platform/src/rip/trust_actions.py:66-68` returns any object with matching `envelope_fingerprint` and `status == "completed"`; receipt schema, action, timestamps, execution identity, and result are not validated.
- `70-Platform/src/rip/trust_actions.py:69-77` writes `executing`, invokes an arbitrary transition callback, and then writes `completed`. A crash after callback side effects but before the completion write causes the callback to run again.
- `70-Platform/src/rip/trust_actions.py:22-24` accepts arbitrary transition and full-verification callbacks, so the persisted contract does not define or constrain the operational effect.

**Adversarial proof**

Temporary-directory execution demonstrated the following architectural effects without altering repository files:

- A valid `pause-affected-scope` envelope was changed to `continue`, its public canonical checksum was recalculated, and persisted continuation returned `continued=True`.
- The modified envelope omitted `created_at` and included an unknown injected field; validation still accepted it.
- An envelope and same-label manifest created for one run were copied into a differently named organization/run directory; continuation succeeded even though a current policy file disagreed.
- Manifest entries were changed to an escaping path while the stored manifest label was retained; envelope validation accepted the manifest and continuation proceeded.
- A receipt with an unsupported schema and contradictory action was returned as a completed receipt because its envelope fingerprint and status matched.
- A simulated failure after transition side effects left the receipt at `executing`; retry invoked the transition a second time.

**Architectural rationale**

A checksum controlled by the same writer as the decision proves internal consistency only until that writer changes both data and checksum. It does not prove governance authority, run identity, current policy, manifest content, source scope, or execution finality. An authoritative execution boundary must bind decision provenance and effect to a non-replayable, run-scoped, durably ordered state machine. Crash recovery must be idempotent at the side-effect boundary, not merely at the JSON-write boundary.

**Affected platform capability**

Trust integrity, governed continuation, Trust Action Executor, source-scope pause, policy application, lifecycle transition, recovery, auditability, and full verification.

**Required correction**

Create one strict, versioned envelope whose canonical content binds organization, run, source-root identity, observation, reasoning record, action, exact scope, authoritative policy identity and fingerprint, canonical manifest content fingerprint, trusted baseline, evidence identities, creation/expiry or monotonic decision sequence, execution operation ID, durable intent, and durable result. Reject unknown and missing fields. Protect authority with a storage-enforced append-only journal and/or an authenticated signature rooted in platform authority rather than a self-recomputable checksum. Validate policy and manifest content independently. Replace arbitrary callbacks with typed executor commands. Implement compare-and-set lifecycle transitions and idempotent operation receipts so every crash point can be replayed without repeating effects.

**Required permanent regression**

Permanent tests must cover: data plus checksum substitution; missing and unknown fields; cross-run and cross-organization replay; source-root mismatch; observation mismatch; policy-file and policy-fingerprint change; manifest-label-preserving content change; baseline mismatch; duplicate/conflicting envelope and projection artifacts; partial envelope/receipt writes; forged or contradictory receipts; crash before intent, after intent, during effect, after effect, and before completion; and exact-once behavior for every executor command.

---

### ARB2-C-002 — Static trusted baseline permits stale customer evidence through every downstream stage

**Severity:** Critical  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/onboarding/service.py:363-365` writes `observation.json` and an unsealed `trusted-baseline.json` containing only source, manifest, and observation fingerprint labels.
- `70-Platform/src/rip/onboarding/service.py:385-394` defines `current_repository_fingerprint()` as a read of the stored baseline. It does not consult the customer source, the source tracker, current metadata, a continuation receipt, or a baseline fingerprint.
- `70-Platform/src/rip/onboarding/service.py:452-470` implements `_tracked_source_fingerprint()`, including metadata disagreement and dirty-tracker handling, but no production consumer calls it.
- `70-Platform/src/rip/onboarding/guided.py:66-78`, `92-95`, and `176-178` describe and perform “freshness” by comparing the observation fingerprint to the static baseline value.
- `70-Platform/src/rip/onboarding/proposal.py:52-55` and `171-173` use the same static comparison before proposal generation.
- `70-Platform/src/rip/onboarding/classification_lifecycle.py:155-180` evaluates only retained artifacts and advances to `observed`; it performs no current-source verification.
- `70-Platform/src/rip/onboarding/resume_orchestration.py:50-60` reports “Fresh source verification succeeded” even though the called lifecycle performs none.
- `70-Platform/tests/test_onboarding_performance.py:108-120` changes the repository and explicitly asserts that `current_repository_fingerprint()` remains the original value without a full scan.
- `70-Platform/tests/test_resume_orchestration.py:38-47` changes the customer source and explicitly asserts that resume still continues with `READY`.

**Adversarial proof**

An ordinary production-path observation was completed against a one-file customer repository. The file was then changed. `begin_guided_understanding()` returned active guided state and preserved the original observation fingerprint while the current file contained different bytes. The same architecture governs answer recording and proposal generation. The classification test suite independently confirms that a changed source is expected to continue.

**Architectural rationale**

A trusted baseline is the state against which current evidence must be evaluated; it is not evidence that current source still equals itself. Replacing freshness with a stored-value self-comparison converts “do not rescan unnecessarily” into “never detect later change.” That permits stale or materially changed customer evidence to flow into supplied knowledge, proposals, classifications, readiness, and lifecycle completion while the UI asserts current verification.

**Affected platform capability**

Trusted baseline promotion, guided understanding, answer persistence, proposal generation, classification, readiness, resume, recovery, diagnostics, and long-running onboarding safety.

**Required correction**

Promote one governed freshness service. It must load and authenticate the trusted baseline, bind it to organization/run/source identity and canonical manifest, consume a healthy process-local watcher plus deterministic metadata only as an invalidation optimization, and fall back to full content verification on restart, missing/unhealthy/overflowed/dirty watcher, metadata disagreement, source identity change, or policy requirement. All downstream consumers must call that one service and consume its sealed decision/receipt. Remove false “fresh verification” language until the service has actually produced that result.

**Required permanent regression**

For every downstream stage, mutate, add, remove, rename, replace, change kind, change access state, and junction-swap the customer source after observation. Cover clean tracker, dirty tracker, overflow, tracker absence, process restart, metadata disagreement, timestamp preservation, same-size content replacement, baseline tampering, manifest tampering, and repository-path substitution. Each unsafe state must pause or perform governed verification before downstream persistence or continuation.

---

### ARB2-C-003 — Windows junctions escape the governed source root and are hashed as customer evidence

**Severity:** Critical  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/onboarding/service.py:728-744` classifies `DirEntry.is_dir(follow_symlinks=True)` and `DirEntry.is_symlink()`, then recurses whenever the entry is a directory and not a symlink.
- On Windows, a junction is a reparse-point directory for which the tested runtime reported `is_junction=True` and `is_symlink=False`. It therefore satisfies the recursion condition.
- `70-Platform/src/rip/onboarding/service.py:586-607` treats the external descendant as a file and hashes it through `_sha256_file()` at `630-637`.
- `70-Platform/src/rip/observation/filesystem.py:151-172` independently calls `find_repository_root()` and joins manifest-relative paths to the rediscovered root without validating that each normalized path remains beneath the approved root.
- `70-Platform/src/rip/observation/filesystem.py:29-40` may expand an approved nested directory to an ancestor containing `.git`, changing the observation root relative to the manifest root.

**Adversarial proof**

In a temporary directory, a governed source contained a Windows junction to a sibling directory outside that source. The runtime classified the entry as `is_symlink=False`, `is_junction=True`. `_source_manifest()` produced both `junction` and `junction/secret.txt`, and the outside file was classified and content-hashed as if it were inside the governed source.

The isolated `verify_declared_scope()` helper does resolve candidates and would reject this resolved escape, but production observation does not use that helper, and persisted continuation does not call it at all.

**Architectural rationale**

The approved source root is an authority boundary. Lexical path checks are insufficient on Windows because reparse points can redirect traversal after a path has already appeared contained. Reading and hashing external content violates customer scope, may cross organization boundaries, and contaminates observation, reasoning, policy, and preservation with evidence that was never authorized.

**Affected platform capability**

Source observation, source manifests, evidence provenance, scope verification, trusted baselines, archival snapshots, and customer data isolation.

**Required correction**

Make traversal reparse-point aware. Use non-following metadata to identify every symlink, junction, mount point, and other reparse point before descent; reject or record it as a non-followed link unless a separate governed policy explicitly authorizes it. Validate final opened handles and canonical paths against a stable root identity, not only path strings. Keep manifest generation and observation projection anchored to the exact approved root; never rediscover an ancestor. Fail closed on uninspectable directories rather than silently omitting their descendants.

**Required permanent regression**

Add Windows regressions for file symlinks, directory symlinks, junctions, nested junctions, mount points, root replacement, reparse-point swaps during traversal, UNC roots, drive-relative paths, case normalization, trailing-dot/space normalization, alternate data streams where applicable, approved nested repository roots, and manifest path tampering. Assert that no outside byte is read and that the retained boundary failure is explicit.

---

## High Findings

### ARB2-H-001 — Scoped continuation neither verifies scope nor offers a governed pause-resolution path

**Severity:** High  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/trust_actions.py:83-101` defines `verify_declared_scope()`, but the only references are tests; no production workflow invokes it.
- `70-Platform/src/rip/trust_actions.py:104-118` ignores `source_root`, manifest entries, and `affected_scope`. For `continue` it returns `continued=True` with `verified=()`; for pause it returns `continued=False`.
- `70-Platform/src/rip/onboarding/resume_orchestration.py:35-41` detects the presence of diagnostic `trust-action.json` and `trust-scope.json`, then calls persisted continuation. It keys branch selection on diagnostic projections rather than the authoritative envelope.
- `70-Platform/src/rip/console/app.py:88-94` marks `paused-affected-scope` as resumable while disabling the decision action.
- `70-Platform/src/rip/console/app.py:207-217` offers only “Execute governed decision”; it provides no materiality decision, policy selection, scope edit, or authority capture.
- `70-Platform/src/rip/onboarding/classification_review.py:40-46` promises that RIP will replay the decision and verify only its declared scope, which production does not do.
- `70-Platform/src/rip/trust_actions.py:55-59` rejects a different decision for the same run, but no production service creates a versioned superseding decision that resolves the pause.

**Adversarial proof**

Persisted continuation of a valid continue decision returned `verified=()` without touching source. Persisted continuation of a pause remained paused. The UI exposes that replay as the primary action, so an operator cannot create the required new governed materiality decision. The only demonstrated promotion path was the invalid envelope substitution covered by ARB2-C-001.

**Architectural rationale**

Identity verification and materiality resolution are different decisions. A pause must not be resolved by byte equality alone, but it must have an explicit governed path to a new decision. Once a new decision exists, any claimed scoped continuation must actually verify the bound scope and dependencies and seal that result before lifecycle advancement.

**Affected platform capability**

Scoped pause, governed review, materiality reasoning, safe continuation, operator completion, and source verification.

**Required correction**

Implement a versioned materiality-resolution command that binds reviewer authority, evidence, reasoning, policy, exact affected scope and dependencies, and a supersedes link to the paused decision. Invoke real scoped verification through the executor, persist per-path results, bind them to the new envelope, and transition only after a completed receipt. Treat diagnostic projections as non-authoritative UI views and never use their mere presence to select execution.

**Required permanent regression**

Exercise an unresolved pause end-to-end: close, reopen, review, decide, verify exact scope, crash/recover, and complete. Cover added, removed, modified, directory, kind-change, access-change, dependency-expansion, empty scope, stale scope, changed policy, changed manifest, and absent decision. Assert no continuation without a new governed decision and a successful bound verification receipt.

---

### ARB2-H-002 — Trust Action Executor is not the single lifecycle execution owner

**Severity:** High  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/trust_actions.py:22-24` delegates operational ownership to arbitrary caller callbacks; `74` invokes the callback without constraining its state transition.
- `70-Platform/src/rip/onboarding/service.py:188-191` writes `created` directly; `306-308` defines a caller-owned state callback; and `368-370` writes `observed` directly for clean observation.
- `70-Platform/src/rip/onboarding/classification_lifecycle.py:98-104` persists a request and directly writes `awaiting-classification`.
- `70-Platform/src/rip/onboarding/classification_lifecycle.py:155-159` claims classification never writes a lifecycle transition, but `170-180`, especially callback line `176`, advances the run to `observed` through a classification-owned callback.
- `70-Platform/src/rip/onboarding/resume_orchestration.py:35-60` contains two independent continuation branches: persisted mutation action and classification integration/lifecycle.
- `70-Platform/src/rip/onboarding/service.py:306-320` and `classification_lifecycle.py:171-180` independently construct `MutationInterpretation` objects and executor calls for different owners.

**Adversarial proof**

The crash-boundary proof in ARB2-C-001 demonstrated that the executor can call a caller-owned transition more than once. Static call-graph enumeration found direct lifecycle writers in onboarding service and classification lifecycle in addition to the executor-mediated callbacks.

**Architectural rationale**

An execution owner cannot guarantee ordering, idempotency, allowed transitions, or durable intent if callers supply arbitrary effects and other subsystems write the same state directly. The current class centralizes some file writes but not ownership of lifecycle semantics.

**Affected platform capability**

Lifecycle state machine, Trust Action Executor, observation, classification, resume, recovery, and execution receipts.

**Required correction**

Define one typed lifecycle state machine and make it the only writer of lifecycle state. Replace callbacks with executor-owned commands and enumerated transition effects. Require every transition to validate current state, bound decision, durable intent, idempotency key, and completed result. Observation, classification, recovery, and UI may submit commands but may not write state or define transition callbacks.

**Required permanent regression**

Statically and dynamically enumerate every permitted lifecycle edge. Fail tests if any production module outside the state-machine owner writes `state.json`. Cover concurrent commands, duplicate submissions, stale expected state, crash at every write boundary, conflicting executor owners, and impossible transitions.

---

### ARB2-H-003 — Production storage singularity can be bypassed and storage topology has duplicate owners

**Severity:** High  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/paths.py:17-21` accepts any explicit root and does not distinguish a test injector from ordinary production use.
- `70-Platform/src/rip/paths.py:39-49` accepts any caller-supplied workspace and constructs run and audit paths without proving that workspace is beneath `C:\RIP`.
- `70-Platform/src/rip/onboarding/service.py:127-150` is an ordinary production entry point that accepts `base_directory` and creates a complete organization workspace there without consulting `organization_workspace()`.
- `70-Platform/src/rip/onboarding/service.py:397-411` resolves an organization under any selected root.
- `70-Platform/src/rip/console/app.py:412`, `438-440`, and `513-515` exposes a workspace text field and Browse control, permitting an operator to select an alternate workspace and make it runtime truth.
- `70-Platform/src/rip/paths.py:24-29` approves `Runs` and `Snapshots`, but `39-45` retains `onboarding-runs` under Workspace and `60-64` places `recovery-snapshots` under the Workspace parent instead of the approved `Snapshots` area.

**Adversarial proof**

An ordinary call to `create_organization_workspace()` created and used a production-form organization workspace under a temporary alternate root. `storage_root(explicit_alternate)` also returned the alternate root. This required no migration capability or test-only token.

The narrow ambient-environment correction is real: setting `RIP_STORAGE_ROOT` does not change default `storage_root()`. That does not establish storage singularity while explicit production roots and UI browsing remain available.

**Architectural rationale**

Authority is defined by enforceable construction boundaries, not comments describing intended callers. If ordinary production functions and UI can select arbitrary roots, `C:\RIP` is a default, not an authority. Duplicate `Runs`, `onboarding-runs`, `Snapshots`, and `recovery-snapshots` topologies create multiple truths and complicate migration and recovery.

**Affected platform capability**

Storage authority, onboarding workspace, run identity, audit logs, snapshots, constitutional state, voice configuration, migration, and operator configuration.

**Required correction**

Remove root parameters from production constructors and resolve all runtime areas exclusively through `rip.paths` under a canonical `C:\RIP` identity. Put test injection behind a separate explicit test factory unavailable to production composition. Put governed migration behind a separately authorized migration context. Remove workspace browsing from production UI. Validate containment and reparse points at creation and every reopen. Consolidate Runs and Snapshots into the approved topology with a governed migration.

**Required permanent regression**

Assert that every production entry point rejects alternate roots, environment-root attempts, relative roots, UNC alternates, symlink/junction roots, legacy `.rip-*` roots, and caller-constructed run paths. Separately prove test factories and migration contexts work only when explicitly invoked. Enumerate every production write and assert it resolves beneath an approved `C:\RIP` area.

---

### ARB2-H-004 — Preservation seals existence rather than lifecycle completeness and recovery is incomplete

**Severity:** High  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/onboarding/recovery.py:82-85` requires only context, state, initial manifest, final manifest, and stages.
- `70-Platform/src/rip/onboarding/recovery.py:86-98` inventories whatever other files happen to exist, but defines no lifecycle-specific required inventory for envelope, reasoning, policy, scope, baseline, execution receipt, lifecycle history, classification, decisions, readiness, diagnostics, metrics, or audit linkage.
- `70-Platform/src/rip/onboarding/recovery.py:95-97` returns an existing preservation receipt without first revalidating its artifact inventory.
- `70-Platform/src/rip/onboarding/recovery.py:101-112` correctly validates every artifact that is listed, but cannot detect an artifact omitted before the original seal.
- `70-Platform/src/rip/onboarding/models.py:19-25` declares an `interrupted` state, and `recovery.py:129-131` requires it for archival snapshots, but production state writers at `service.py:190`, `308`, `369` and `classification_lifecycle.py:103`, `176` never write `interrupted`.
- The normal source-change path writes `paused-affected-scope` at `service.py:306-308`; therefore `create_archival_source_snapshot()` rejects the principal interrupted observation path.

**Adversarial proof**

A manually constructed run containing only the five required JSON filenames—with empty manifests and stages and no trust envelope, policy, reasoning, scope, receipt, baseline, diagnostics, classifications, decisions, readiness, or metrics—was accepted and sealed. The receipt listed only those five files.

**Architectural rationale**

Hashing every artifact that remains is not proof that every artifact necessary to reproduce and explain the decision remains. Completeness must be defined by lifecycle state and transaction history. Otherwise a deletion before seal becomes indistinguishable from an optional artifact. A declared recovery state that production cannot enter and an archival operation that rejects the real paused path do not form a usable recovery architecture.

**Affected platform capability**

Interrupted-run preservation, reopen, provenance, trust explanation, recovery, archival capture, and Operational Memory.

**Required correction**

Define a versioned lifecycle-specific preservation manifest with required, optional-with-reason, and prohibited artifacts. Seal canonical content, size, hash, identity, organization, run, storage root, lifecycle sequence, and authoritative decision/receipt relationships after quiescing the run. Fail closed when required artifacts are missing or malformed. Validate an existing seal before returning it. Implement real entry into an interrupted state or remove the state and align recovery to the actual pause state. Make archival capture explicitly available but separate, with correct eligibility.

**Required permanent regression**

Delete or alter each required artifact before seal and after seal, alter and rechecksum the receipt, replay it into another organization/run/root, introduce unexpected files, truncate during preservation, interrupt at every lifecycle stage, and reopen without customer-source access. Verify optional-versus-required rules for clean, paused, classification, executing, completed, and partially persisted states.

---

### ARB2-H-005 — Storage migration is not transactionally receipt-bound, resumable, or revalidated

**Severity:** High  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/storage_migration.py:63-79` returns a mutable-in-memory plan with no schema, canonical plan fingerprint, operator authority, or immutable persisted plan.
- `70-Platform/src/rip/storage_migration.py:82-90` returns any prior completed receipt immediately, before revalidating that it matches the supplied plan or that source and destination still match.
- `70-Platform/src/rip/storage_migration.py:126-133` validates only receipt schema and dataclass shape. The receipt has no fingerprint or authenticated binding to plan, operator, source state, destination state, or checkpoint chain.
- `70-Platform/src/rip/storage_migration.py:101-107` copies directly to the final destination, checkpoints after copy, and has no partial-file staging, quarantine, fsync/durability boundary, or atomic commit rename.
- `70-Platform/src/rip/storage_migration.py:97-100` treats any partial or changed destination as a terminal conflict; it neither resumes nor quarantines it.
- `70-Platform/src/rip/storage_migration.py:93-100` accepts all paths embedded in a caller-created `StorageMigrationPlan`; execute does not re-prove that sources are known legacy roots or destinations remain under the governed root.

**Adversarial proof**

- After a migration completed, both the legacy source and governed destination were changed. Re-execution returned the old completed receipt without inspecting either file; corrupted destination content remained accepted.
- The completed receipt’s source locations were changed to a different path. Re-execution returned the modified receipt because schema and shape remained valid.
- A partial destination created after planning caused a `destination changed` error and remained in the authoritative destination; it was neither resumed nor quarantined.

**Architectural rationale**

Idempotency means repeating the operation produces or verifies the same governed outcome. Returning an old receipt without checking the current outcome is replay, not idempotency. Direct final-path copies expose partial artifacts as destination truth and prevent deterministic crash recovery.

**Affected platform capability**

Legacy storage discovery, storage migration, State, Configuration, Workspace, named run migration, recovery, and operator audit.

**Required correction**

Persist and seal a canonical plan bound to known legacy roots, governed destination root, every artifact, conflict decision, operator authority, and source snapshot. Copy to a transaction-specific partial area, flush, verify size/hash, atomically rename into place, and append a hash-chained checkpoint. Quarantine unexpected or partial destinations. On every replay—including completed receipts—validate receipt-to-plan binding and governed destination integrity; report changed legacy source as a new plan requirement rather than silently returning success. Reject caller-constructed paths outside approved migration contracts.

**Required permanent regression**

Interrupt after planning, during copy, after copy, after verification, before checkpoint, after checkpoint, before rename, after rename, and before completion. Cover changed source after planning, changed destination after completion, stale or modified receipt, replay against another plan/root/run, duplicate runs, partial destinations, conflicts, quarantine, named runs, zero-file roots, symlink/junction legacy content, and operator cancellation. Assert non-destructive behavior and deterministic resume.

---

### ARB2-H-006 — Operator journey contains dead ends, false claims, and missing required workflows

**Severity:** High  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/console/app.py:88-100` labels a scoped pause or ready classification as executable/verified, but ARB2-H-001 and ARB2-C-002 show the corresponding verification does not occur.
- `70-Platform/src/rip/console/app.py:172-218` has review, replay, and close controls but no scoped materiality-decision control and no archival-snapshot control.
- `70-Platform/src/rip/console/app.py:513-515` allows alternate workspace browsing, conflicting with storage singularity.
- `70-Platform/src/rip/onboarding/service.py:154-168` rejects run creation without locally configured reasoning capability even though repository observation at `195-382` makes no provider call.
- `70-Platform/src/rip/console/app.py:536-566` disables observation and presents provider/model correction as required until that unrelated prerequisite passes.
- `70-Platform/src/rip/console/app.py:517-531` reopens only the classification/recovery review. It does not reconstruct successful observation, guided state, current question, or proposal into the primary onboarding journey after close.
- `70-Platform/src/rip/cli.py:19-90` exposes no migration command; the console exposes none either.
- `70-Platform/src/rip/trust_actions.py:70-73` permits full verification only as a caller callback. No governed policy record, operator command, UI journey, or durable verification result exists.
- `70-Platform/docs/architecture/RIP-6.0-CZ-M1-Architectural-Review-Package.md:72-76` acknowledges that full-verification policy records and a fully interactive governed-review decision screen remain incomplete before a production Customer Zero run.

**Adversarial proof**

Production-path run creation without an API key failed before provider-free observation. A paused-scope review exposed only replay, which returned not continued and left no resolution action. Static UI/call-graph review found no migration control, no full-verification control, and no primary-journey rehydration for successful deferred work.

**Architectural rationale**

An operator journey is complete only if every reachable state has a truthful next action and can be safely deferred and reopened. Labels that claim verification when none occurred are trust defects, not presentation defects. Optional providers must not block deterministic local stages. A required migration or explicit verification capability without an operator surface is not operationally deliverable.

**Affected platform capability**

Expected mutable change, unresolved scoped pause, governed review, recovery, reopen, defer/return, migration, explicit full verification, and onboarding completion.

**Required correction**

Build a controller-backed operator state machine that derives controls and language from authenticated lifecycle/decision/receipt state. Add the governed scoped-decision journey, truthful verification progress/result, optional archival action, complete reopen/rehydration, explicit migration workflow, explicit full-verification workflow, and completion state. Remove provider configuration from observation eligibility. Remove alternate storage browsing. Ensure every action survives close/restart and every unavailable action explains the exact prerequisite.

**Required permanent regression**

Automate the real operator journey—not only formatting helpers—for expected mutable change, unresolved pause, authorized and unauthorized decisions, close/reopen at every state, classification conflict, recovery, optional archival capture, migration, full verification, provider absent, source absent, crash recovery, and completion. Assert displayed claims against actual receipts and traversal instrumentation.

---

## Medium Findings

### ARB2-M-001 — Architecture metrics are inaccurate, incomplete, and sometimes double-counted

**Severity:** Medium  
**Status:** Open

**Exact production evidence**

- `70-Platform/src/rip/onboarding/service.py:241` records one traversal/read/hash count for the initial manifest.
- `70-Platform/src/rip/onboarding/service.py:276` records one traversal/read/hash count for the final manifest, then `286` records the same final manifest counts a second time without another content traversal.
- These calls use total `entry_count` as both `source_reads` and `hashes`, even though `service.py:574-577` hashes only file entries; directories, symlinks, and access errors are counted as hashes and reads.
- `70-Platform/src/rip/onboarding/service.py:336-339` may perform a metadata traversal, but that traversal class is not separately recorded.
- `70-Platform/src/rip/architecture_metrics.py:8-18` accepts arbitrary counter names and rewrites a JSON file for every update; there is no declared counter schema, atomic multi-process increment, or event identity.
- `rip.trust_actions`, `onboarding/recovery.py`, `storage_migration.py`, scoped verification, source watcher decisions, classification lifecycle, UI interventions, and archival snapshot workflows contain no architecture-metrics calls.
- Artifact-write counters omit most stages, state writes, audits, policies, reasoning, receipts, preservation, classifications, proposals, and migration writes. The metrics file’s own write is also not represented.

**Adversarial proof**

For a one-file clean observation, production performed two full content-manifest passes. Metrics reported `traversals=3`, `source_reads=3`, and `hashes=3`. The third full-content count was the duplicate at line 286; any metadata traversal was neither typed nor separately represented.

**Architectural rationale**

Metrics used as architecture evidence must correspond to operations at the primitive that performs them. Untyped counters incremented by high-level callers can accidentally equal a total while misrepresenting traversal class, and they cannot reveal uninstrumented alternate paths.

**Affected platform capability**

Architecture validation, performance planning, traversal budgets, trust-decision auditing, recovery, migration, and operator intervention reporting.

**Required correction**

Define a versioned metrics schema with distinct counters for metadata tree walks, content-hash tree walks, snapshot/copy walks, scoped path checks, file opens, bytes read, hashes completed, manifests, policy evaluations, trust decisions, intents, effects, completions, pauses, continuations, artifact writes, migration operations, and operator interventions. Instrument the owning primitives, attach workflow/operation IDs, and aggregate atomically without changing deterministic evidence.

**Required permanent regression**

Use independent spies around traversal, open/hash, copy, and persistence primitives and compare actual operations to emitted metrics for every major workflow. Cover errors, retries, crashes, parallel hashing, watcher fast path/fallback, scoped verification, preservation/reopen, archival capture, migration, and UI intervention. Reject unknown counters and double increments.

---

### ARB2-M-002 — Passing tests encode acknowledged defects and omit decisive adversarial cases

**Severity:** Medium  
**Status:** Open

**Exact production evidence**

- `70-Platform/tests/test_onboarding_performance.py:108-120` changes source and asserts that the stored fingerprint remains accepted without calling a scan.
- `70-Platform/tests/test_resume_orchestration.py:30-35` names a test “performs fresh verification” but asserts only the success message and state, not any source operation.
- `70-Platform/tests/test_resume_orchestration.py:38-47` changes source and asserts successful continuation.
- `70-Platform/tests/test_persisted_trust_continuation.py:8-22` asserts that continuation returns no verified paths for both continue and pause.
- `70-Platform/tests/test_architectural_obligations.py:23-30` tests only naïve envelope editing without checksum recomputation; it does not test an actor capable of using the public canonical checksum routine.
- `70-Platform/tests/test_storage_migration.py:8-17` covers one happy-path file, replay of unchanged completed receipt, and preplanned conflict only.
- `70-Platform/tests/test_interrupted_run_preservation.py:36-50` verifies no customer traversal and preservation of existing artifacts but does not delete required decision artifacts before the seal.
- The complete suite passes 180 tests, confirming these expectations are active production acceptance criteria.

**Adversarial proof**

Independent tests outside the committed suite demonstrated failures the suite did not detect: authoritative checksum substitution, cross-run replay, receipt substitution, duplicate crash effect, post-observation stale continuation, Windows junction escape, incomplete preservation, stale migration receipt, corrupted completed destination, and metric double counting.

**Architectural rationale**

Tests can prove conformance to an unsafe contract. Names and success messages are not evidence of the operation claimed. Architectural regressions must observe production entry points and the actual source, persistence, and transition primitives involved.

**Affected platform capability**

All Milestone 1 validation, especially trust, freshness, source boundary, recovery, migration, metrics, and operator completion.

**Required correction**

Rewrite unsafe expectations around a governed trust and freshness contract. Add production-entry-point adversarial fixtures with realistic persisted artifacts. Assert failure reason and actual operation, not only return values or strings. Separate unit tests for deterministic serialization from security/authority tests for storage, replay, lifecycle, and source boundaries.

**Required permanent regression**

Promote every adversarial proof in this report into a permanent negative regression, run on Windows where junction and path semantics matter. Include crash-injection and on-disk artifact matrices. Require test names, assertions, and instrumented operations to agree.

---

### ARB2-M-003 — AO traceability is absent and the review package self-identifies unfinished prerequisites

**Severity:** Medium  
**Status:** Open

**Exact production evidence**

- `70-Platform/docs/architecture/RIP-6.0-CZ-M1-Architectural-Review-Package.md:3-13` claims Session 0001 obligations are implemented but does not enumerate AO-0001 through AO-0013, their acceptance criteria, owners, implementation evidence, or regressions.
- A repository-wide search found no AO-0001 through AO-0013 definitions and no retained Session 0001 ARB report.
- `70-Platform/tests/test_architectural_obligations.py:1-58` contains five broad tests, not thirteen obligation contracts or an AO evidence matrix.
- `70-Platform/docs/architecture/RIP-6.0-CZ-M1-Architectural-Review-Package.md:72-76` explicitly states that full-verification policy records and a fully interactive governed-review decision screen require completion before a production Customer Zero run.
- `70-Platform/docs/architecture/RIP-6.0-CZ-M1-Architectural-Review-Package.md:48-50` also identifies continuous-observation policy/ownership for multi-day observation as future work.

**Adversarial proof**

The missing obligation corpus prevented a direct one-to-one audit of AO-0001 through AO-0013. The controls inferable from the package were traced and several were invalidated. Independently, the package’s own remaining-limitations section identifies unfinished pre-production requirements.

**Architectural rationale**

Governed validation must preserve the decision, obligation, implementation, test, and validation chain. A summary assertion cannot substitute for the missing obligations, and an authorization package cannot simultaneously declare implementation complete and identify required production controls as unfinished.

**Affected platform capability**

Governance traceability, ARB validation, milestone acceptance, architectural obligations, and Customer Zero readiness.

**Required correction**

Restore or create the governed Session 0001 report and AO-0001 through AO-0013 registry. For each obligation, record authority, exact acceptance criteria, implementation owner, production evidence, adversarial regression, status, and validation result. Resolve package contradictions and keep limitations explicit without representing incomplete prerequisites as implemented.

**Required permanent regression**

Add a governance validation test that requires every active AO to appear exactly once and to link to existing production evidence and permanent tests. Fail the milestone package build for missing obligations, stale links, contradictory completion/limitation states, or authorization language while stop-ship prerequisites remain open.

---

## Constitutional Violations

| Finding | Constitutional violation |
|---|---|
| ARB2-C-001 | RIP-000 §3 Authority and §7 Learning, Reasoning, and Governance: technical write control and a recomputable checksum can become effective authority. RIP-000 §6 Hosts and RIP-004 Decision Requirements: action is not durably bound to authorized decision provenance, rationale, assumptions, execution, and validation. |
| ARB2-C-002 | RIP-000 §4 Knowledge and Understanding and §10 Operations and Changes: stale evidence is represented as current and operations are not derived from current evidence. RIP-000 §15 and RIP-005 Persistent Governed Memory: retained memory is not refreshed when governing source changes. |
| ARB2-C-003 | RIP-000 §4 and §6: provenance and explicit capability boundaries are violated when external content is read as governed source. RIP-000 §13 Deliverability: the boundary is not internally consistent or capable of reliable validation. |
| ARB2-H-001 / H-002 | RIP-000 §7 and RIP-004 Governance Principle: execution and lifecycle effects are split across subsystem-owned paths, and the required governed materiality decision is absent. |
| ARB2-H-003 | RIP-000 §12 Constitutional Purpose and §13 Deliverability: storage ownership exists in comments and defaults but is not enforceable; duplicate topologies have no singular governed owner. |
| ARB2-H-004 / H-005 | RIP-000 §8 Institutional Memory and §15 Operational Memory; RIP-005 Preservation Requirement: materially necessary provenance, decision context, validation evidence, and outcome integrity are not guaranteed through preservation or migration. |
| ARB2-H-006 | RIP-000 §13 Deliverability and §14 Self-Governance: the system presents capabilities and verification results it does not operationally provide. |
| ARB2-M-001 / M-002 / M-003 | RIP-004 Validation Requirements: implementation existence and passing tests are treated as validation despite inaccurate measures, unsafe expected behavior, missing obligation evidence, and acknowledged gaps. |

The most serious constitutional breach is epistemic: RIP states that a source is fresh, a decision is governed, a scope will be verified, or a migration is complete when the retained evidence does not prove those claims.

---

## Platform Drift

The corrected implementation still contains multiple second truths and duplicate owners:

- **Freshness exists twice:** the active static `trusted-baseline.json` self-comparison and the unused `_tracked_source_fingerprint()` watcher/fallback implementation.
- **Trust decision exists at least three times:** `trust-decision-envelope.json`, diagnostic `trust-action.json`, and diagnostic `trust-scope.json`. Resume chooses its path based on diagnostic file presence but executes the envelope.
- **Lifecycle ownership is split:** onboarding service, classification lifecycle, resume orchestration, and Trust Action Executor all define or write transitions.
- **Policy ownership is split:** mutation rules become a runtime mutation-policy contract while classification creates a separate policy/evaluation/continuation path; neither is compiled into one authoritative execution policy.
- **Storage ownership is split:** `rip.paths` declares approved `Runs` and `Snapshots`, while onboarding constructs `onboarding-runs` and `recovery-snapshots` beneath arbitrary workspaces.
- **Recovery ownership is split:** preservation, archival snapshot, classification recovery, and resume orchestration have incompatible eligibility and no single recovery state machine.
- **Metrics ownership is absent from primitives:** onboarding service guesses counts for operations owned by manifest, persistence, trust, recovery, and migration modules.
- **Onboarding owns platform capabilities:** it constructs storage, mutation policy, trust interpretations, source watchers, preservation calls, lifecycle state, audit files, metrics increments, and operator flow instead of consuming stable platform services.

No additional platform layer should be added until these duplicate truths are collapsed into singular owners.

---

## Trust Integrity Assessment

The trust-decision envelope does not satisfy the requested immutable envelope contract.

| Required binding | Assessment |
|---|---|
| Observation identity | Present only as a string; not bound to organization, run, source root, or an authenticated observation artifact. |
| Reasoning | Fingerprint present; external reasoning validation is optional when the file is missing. |
| Action | Present, but changeable with checksum recomputation. |
| Scope | Present, but not executed or verified by persisted continuation. |
| Policy identity/fingerprint | Embedded policy object present; authoritative external policy and its declared fingerprint are not validated. |
| Manifest identity | Only a stored label is compared; canonical manifest content is not recomputed. |
| Trusted baseline | Absent from the envelope. |
| Timestamps | `created_at` is optional and excluded from the checksum; no expiry, decision sequence, start/completion ordering, or clock policy exists. |
| Execution intent | A mutable `execution_status` label is in the envelope but excluded from its checksum; actual intent is a separate receipt. |
| Execution result | Separate receipt is weakly validated and not part of the immutable envelope. |
| Canonical serialization | Deterministic JSON sorting/separators are used, but strict schema and authoritative signing are absent. |
| Missing/unknown fields | Required-subset check accepts missing timestamp and unknown fields. |
| Conflicting artifacts | Diagnostic files are always rewritten and can disagree; resume branches on their presence. |
| Partial writes | Individual files use temporary replace, but the multi-file envelope/diagnostics/receipt/state transaction is not atomic. |
| Stale/replay | No organization/run/root binding, expiry, or monotonic sequence; cross-run replay was demonstrated. |
| Crash recovery | Transition can repeat after a crash between effect and completion. |

Execution does not fail closed in every invalid state. Trust integrity is therefore **unacceptable for Customer Zero**.

---

## Source-Boundary Assessment

Basic lexical scope protections exist in `verify_declared_scope()`: absolute paths, `..`, missing manifest paths, resolved escapes, non-files, and mismatched hashes are rejected. That helper is not enough because:

1. It is not called by production continuation.
2. It consumes caller-supplied expected entries without first validating the canonical manifest content.
3. It reads a path after a separate resolve/containment check, leaving a replacement race.
4. It handles only files, so added, removed, kind-changed, directory, symlink, and access-state changes have no complete verification semantics.
5. Production manifest traversal follows Windows junctions outside the governed root.
6. Observation projection may anchor manifest-relative paths to a rediscovered ancestor repository rather than the exact approved source.
7. Directory access failures can stop recursion without preserving an explicit descendant-completeness failure.

The source boundary is **not reliable**. Customer data outside the selected scope can be read, hashed, and represented as governed evidence.

---

## Storage Assessment

The implementation successfully removed ambient `RIP_STORAGE_ROOT` authority from default resolution and moved constitutional memory and voice configuration defaults into named `C:\RIP` areas. Those are useful corrections.

They do not create singular authority because ordinary production APIs and the UI accept arbitrary roots, run paths are caller-relative, and recovery snapshots bypass the approved `Snapshots` area. The acknowledged legacy `onboarding-runs` segment also means the approved `Runs` area is not the active run authority.

Generated `State\constitutional-memory.json` appears to be expected local output rather than evidence of a bypass. It was kept separate from production architecture and was not modified. The generated review patch likewise is not runtime authority.

Storage assessment: **not singular, not enforceable, and not ready for Customer Zero**.

---

## Migration Assessment

Migration has useful primitives: known legacy-name mapping, deterministic inventory, source size/hash capture, copy-before-delete behavior, per-artifact checkpoint attempts, and conflict rejection. It never deletes legacy content automatically.

The decisive properties are missing. The plan is not persisted or sealed; execute trusts caller-created paths; completed receipts short-circuit all current validation; receipts are unsealed; direct final-path copies expose partial files; partial destinations are neither resumable nor quarantined; and no governed operator workflow exists. Named-run behavior is merely incidental path copying rather than an explicit governed migration contract.

Migration is **not transactionally resumable, idempotent, or production-operable**.

---

## Preservation and Recovery Assessment

The promoted separation between preservation and optional archival capture is conceptually correct. `preserve_interrupted_run()` does not traverse or copy customer source, and `reopen_preserved_interrupted_run()` validates the size and hash of listed artifacts without source access.

The seal is nevertheless incomplete because it proves only retained existence, not lifecycle-required completeness. It accepts a five-file shell with no decision evidence. The `interrupted` lifecycle is not produced by normal observation, while archival capture requires it and the real source-change path uses `paused-affected-scope`. The primary review UI has no archival action and no legitimate scoped-resolution action.

Preservation and recovery assessment: **good boundary intent, insufficient completeness and unusable end-to-end recovery**.

---

## Performance and Traversal Assessment

### Actual worst-case traversal behavior

| Major workflow | Customer-source traversal/read behavior | RIP-owned traversal behavior | Assessment |
|---|---|---|---|
| Clean initial observation | 2 complete content-manifest traversals; up to 1 additional metadata traversal when a clean watcher is registered | Run artifact writes and audit rewrites | Observation projection avoids a third content walk, but generic metrics misclassify/double-count and omit metadata class. |
| Expected mutable change during observation | Same 2 content traversals plus possible metadata traversal; mutation interpretation uses retained difference | Trust, stage, audit, state, baseline writes | No extra source scan for reasoning; later freshness is unsafe. |
| Unresolved mutation/preservation | 2 content traversals during observation; preservation itself performs 0 customer traversals | 1 recursive run-artifact inventory plus one full read/hash per retained artifact | Customer boundary is efficient; artifact completeness and large-file memory behavior remain concerns. |
| Reopen preserved run | 0 customer traversals | One stat/read/hash validation per listed artifact | Correct no-source behavior for listed artifacts only. |
| Guided start, answer, proposal | 0 customer traversals | Baseline read and downstream artifact writes | Fast because no current-source verification occurs; unsafe, not an optimization win. |
| Classification integration/resume | 0 customer traversals | Classification file enumeration/evaluation and state/receipt writes | Unsafe “fresh verification” claim; changed source continues. |
| Persisted continue or pause replay | 0 customer traversals and 0 scoped path reads | Envelope read | `source_root` is unused; no verification occurs. |
| Explicit archival source snapshot | 3 customer tree passes: before manifest, copy traversal, after manifest | 1 complete snapshot-manifest traversal | Four total tree traversals, three against customer source. This is acceptable only as an explicit optional archival operation. |
| Load verified archival snapshot | 0 customer traversals | 1 complete snapshot-manifest traversal | Correctly avoids customer source. |
| Migration inventory | 1 recursive traversal per legacy root and one hash read per file | Destination existence/hash checks as applicable | Deterministic but uninstrumented. |
| Migration execution | No source tree walk; per planned file: validation hash plus copy read; destination verification hash | Checkpoint/receipt rewrites for every state | Potentially high I/O amplification; no architecture metrics or transaction staging. |

Instrumentation itself writes and replaces JSON repeatedly. The number of calls is small during observation, so current instrumentation is unlikely to dominate million-file hashing, but it cannot support concurrent writers safely and provides inaccurate evidence. Preservation uses `read_bytes()` for each artifact, which can materially increase memory pressure for large retained artifacts. Migration writes multiple full receipts per artifact and may scale poorly with a growing checkpoint list.

Performance assessment: the two-content-pass observation design is reasonable, but the reported architecture counters are not trustworthy and downstream zero-traversal claims conceal missing freshness verification.

---

## Operator Journey Assessment

| Journey | Assessment |
|---|---|
| Expected mutable change | Mutation reasoning can automatically continue, but all later stages rely on stale baseline self-comparison. |
| Unresolved scoped pause | Dead end. Review explains the scope but provides no governed materiality decision; replay remains paused. |
| Governed review | Classification review exists, but it is separate from mutation materiality and still owns lifecycle effects. Interactive scoped-review decision is admitted incomplete. |
| Recovery | Preservation is automatic for the real pause path, but completeness is not guaranteed and generic interruption has no durable state transition. |
| Reopen | Preserved review reopens without source access. Successful guided/proposal work is not rehydrated into the primary UI journey after close. |
| Defer/return later | “Close and return later” exists for review, but returning does not create the missing resolution path. |
| Migration | No console or CLI workflow. |
| Explicit full verification | Enum and callback exist; no policy record, governed decision, operator action, metrics, or bound receipt. |
| Completion | Proposal can be marked reviewed, but source freshness is not established and interrupted/scoped journeys cannot complete. |
| Provider prerequisites | Observation is provider-free but is blocked until local provider configuration is present. |
| Archival capture | Correctly not on the critical path, but no operator control is present and actual paused state is ineligible. |

Operator journey assessment: **not complete and not truthful enough for Customer Zero**.

---

## Test Quality Assessment

The suite contains substantial useful deterministic coverage for classification contracts, policy reconstruction, observation projection, preservation without customer traversal, recovery snapshot copy verification, and basic storage migration. It exercises many production entry points with realistic temporary artifacts.

However, the Milestone 1 acceptance tests are architecturally insufficient:

- They treat a static baseline read as freshness.
- They explicitly require changed-source classification resume to succeed.
- They assert no paths are verified by persisted continuation.
- They test naïve checksum mismatch, not authority against a writer that can recompute the same public checksum.
- They rely extensively on arbitrary temporary workspace roots through production constructors, so they cannot prove production storage singularity.
- They do not exercise junctions, ancestor-root normalization, cross-run replay, strict envelope schema, policy/manifest disagreement, receipt substitution, exact-once crash recovery, missing preservation artifacts, completed migration revalidation, partial-destination quarantine, or real operator completion.
- Several UI tests inspect source text or formatting helpers rather than driving the controller and asserting operational effects.

The full 180-test pass is therefore a build-health signal, not architectural authorization evidence.

---

## Required Corrections in Priority Order

1. **Stop trust execution.** Replace the self-checksummed envelope/receipt with a strict, run-scoped, authority-rooted, replay-resistant, crash-idempotent execution journal. Close ARB2-C-001.
2. **Restore real freshness.** Implement one governed current-source verification service using the sealed baseline, watcher invalidation, metadata signal, and mandatory full fallback. Route every downstream stage through it. Close ARB2-C-002.
3. **Close the Windows source boundary.** Reject or explicitly govern all reparse points and anchor every traversal/read to the exact approved root. Close ARB2-C-003.
4. **Implement legitimate scoped resolution.** Add a governed superseding materiality decision, actual scoped/dependency verification, sealed results, and truthful UI. Close ARB2-H-001.
5. **Create one lifecycle owner.** Centralize state transitions and typed execution effects; remove direct writers and arbitrary callbacks. Close ARB2-H-002.
6. **Enforce storage singularity.** Remove arbitrary production roots and UI browsing, consolidate Runs/Snapshots, and separate test/migration injection. Close ARB2-H-003.
7. **Define preservation completeness.** Use lifecycle-specific required inventories, atomic sealing, exact reopen validation, and a reachable recovery state machine. Close ARB2-H-004.
8. **Rebuild migration transactionality.** Seal plan/receipt, stage and atomically commit files, revalidate completed destinations, quarantine partials, and provide the governed operator workflow. Close ARB2-H-005.
9. **Complete the operator state machine.** Add reopen/rehydration, decision, migration, full verification, recovery, defer, and completion paths with truthful language and no irrelevant provider gate. Close ARB2-H-006.
10. **Instrument primitives accurately.** Introduce typed, operation-bound metrics and validate them against independent operation counts. Close ARB2-M-001.
11. **Replace unsafe test expectations.** Convert every Session 0002 proof into a permanent Windows-capable negative regression at production entry points. Close ARB2-M-002.
12. **Restore governed traceability.** Publish Session 0001 and AO-0001 through AO-0013 contracts with evidence and eliminate package contradictions. Close ARB2-M-003.

After correction, repeat the entire Session 0002 adversarial review from a fresh independent context. Do not treat closure by unit test alone as validation.

---

## Recommended Milestone 1 Status

**REJECTED — RETURN TO MILESTONE 1 CORRECTION**

Milestone 1 is not architecturally complete. The work should remain an uncommitted correction set until all Critical and High findings are closed with permanent production-entry-point regressions and an independent re-review confirms the closure. The current implementation must not be used for a long-running Customer Zero workflow because that run would encounter known trust, freshness, source-boundary, recovery, storage, and operator defects.

---

## Customer Zero Authorization Recommendation

# NOT AUTHORIZED

