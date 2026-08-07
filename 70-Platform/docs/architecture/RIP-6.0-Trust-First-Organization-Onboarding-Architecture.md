# RIP 6.0 — Trust-First Organization Onboarding Architecture

## Purpose

RIP 6.0 introduces organization onboarding as a trust-first capability. Its purpose is to establish evidence-based understanding before RIP asks material questions, drafts governance, or performs any operational action.

This architecture does not make an organization part of RIP. RIP remains the platform; each organization remains sovereign and governs its own authority.

## Governing principles

- There is no ambient organization. Every onboarding operation requires an explicit, immutable Organization Context.
- The lifecycle is **Observe First, Ask Second, Propose Third, Activate Last**.
- Customer repositories and approved external sources remain read-only throughout onboarding.
- RIP may write disclosed onboarding records only within an isolated RIP-controlled organization workspace that does not overlap a customer source.
- Observation progress reflects completed work and evidence state, never elapsed-time estimates or artificial percentages.
- A discovery event is emitted only after the represented observation or classification work has occurred.
- Reasoning capability is replaceable. Provider selection is capability-first and does not become organization identity.
- Local configuration and declared context support do not prove live provider connectivity or model accessibility; RIP states that limit explicitly unless a future governed live probe is performed.
- Understanding is never faked. Metadata may establish that an artifact was observed or that a signal was detected, but it does not establish organizational mission, authority, product identity, decision meaning, or governance.
- Generated output is non-authoritative. Approval precedes governance promotion, activation, and action.
- Onboarding runs are isolated and resettable. A completed run remains auditable; a new run receives a new identity.
- Organizational Memory belongs to the originating organization and remains distinct from RIP Constitutional Memory.
- Every material onboarding claim must be inspectable through its supporting evidence, observation IDs, source paths, and deterministic fingerprints.

## Organization boundary

An Organization Context binds one organization ID, one onboarding-run ID, one approved repository target, one isolated RIP workspace, one observation mode, and one declared reasoning capability. Operations without that context are invalid.

No cache, index, audit record, observation result, discovery feed, provider request, or generated artifact may be shared implicitly across organization contexts. Customer knowledge does not become RIP Institutional Knowledge merely because RIP processed it. Any general lesson must follow the separate Governed Organizational Wisdom path.

## Read-only onboarding boundary

Phase 6A allows repository reads, deterministic observation, evidence classification, and generation of onboarding records in the RIP workspace. It prohibits customer-source writes, governance promotion, organization activation, Organizational Memory initialization, and operational customer action.

The workspace boundary is validated before initialization and before every run: it cannot equal, contain, or be contained by the observed repository. Observation additionally fingerprints the repository before and after the observer runs. If the source changes during observation, RIP rejects the result rather than claiming a stable read-only observation.

## Truthful progress

The Discovery Feed is an audit-visible representation of actual work. Phase 6A emits deterministic semantic stages for:

1. repository fingerprint start, periodically coalesced processed-entry counts, and completion;
2. repository observation start and completion with the actual observed-entry count;
3. repository integrity-verification start, per-entry processed counts, and completion;
4. evidence classification and observation-summary construction;
5. evidence signals discovered from completed observation; and
6. observation-run completion.

The filesystem observer projects path and type evidence from the completed initial source manifest. It reports the truthful stage transition and completed observation count rather than simulating separate per-entry observation work.

Progress events are operational presentation, not additional evidence. RIP coalesces manifest progress at a fixed entry interval so a large repository does not create hundreds of thousands of retained UI events. Every reported count represents completed work, and the completion event retains the exact final count.

## Performance without weakened integrity

Source performance optimizations preserve the governed trust boundary:

- File content is still SHA-256 hashed before and after observation.
- Hashing reads files in bounded buffers rather than loading an entire file into memory.
- A bounded worker pool may hash independent files concurrently, but results are consumed in deterministic repository order before manifest construction.
- The source-manifest schema, per-file SHA-256 values, aggregate fingerprint, manifest fingerprint, symlink handling, and access-error representation remain unchanged.
- Filesystem observations are projected from the exact initial source manifest instead of performing a redundant third repository walk. This changes neither the observation scope nor the evidence classification rules.
- Phase timing, byte counts, worker count, progress interval, and verification method are written to `observation-performance.json`. Operational timing is kept outside deterministic evidence fingerprints.

After an independent before/after content verification succeeds, a process-local native filesystem watcher and deterministic metadata fingerprint may establish that the source remains unchanged during guided interaction. The watcher is an optimization only. If it is unavailable, unhealthy, overflowed, reports a source change, or disagrees with current metadata, RIP performs a complete SHA-256 freshness scan. A process restart also falls back to complete verification because no process-local watcher survives restart.

RIP does not trust file size or modification time as a substitute for content integrity. Metadata is used only to invalidate the fast path; it never proves content identity without the clean native watcher and the previously completed full-content baseline.

## Epistemic representation

Customer-facing onboarding output distinguishes four conditions:

- **Observed:** RIP directly observed an artifact or repository boundary.
- **Signals Detected:** filenames, paths, file kinds, or manifests provide a limited evidence signal.
- **Requires Confirmation:** a signal may matter organizationally, but customer confirmation is required before treating it as meaning or authority.
- **Unknown:** the approved observation scope did not establish the requested understanding.

For example, a file named `mission.md` is a mission-related filename signal, not proof of the organization’s mission. A project manifest is a product signal, not product identity. A governance-related filename is not organizational authority. No semantic provider call is required or used to cross these boundaries in Phase 6A.

## Capability-first reasoning connection

Onboarding presents a recommended reasoning capability and permits an explicit provider/model override. Validation checks whether an approved capability declaration exists, whether it declares governed-evidence and required-context support, and whether local configuration is present. The result states that live provider connectivity and model accessibility have not been verified.

No organization evidence is transmitted by this validation. Repository observation does not call a provider.

## Run lifecycle

```text
Organization Context created
        ↓
Read-only repository observation
        ↓
Evidence-linked summary
        ↓
Completed onboarding run
        ↓
Future phases only: Ask → Propose → Customer Approval → Activate
```

Reset creates a new onboarding run rather than rewriting a completed run. It does not alter RIP Constitutional Memory, customer sources, customer authority, or prior approved organization records.

## Non-goals of Phase 6A

Phase 6A does not conduct adaptive interviews, generate governance, promote governance, activate organizations, initialize Organizational Memory, learn continuously, modify customer sources, or create tenant information in the RIP repository.
