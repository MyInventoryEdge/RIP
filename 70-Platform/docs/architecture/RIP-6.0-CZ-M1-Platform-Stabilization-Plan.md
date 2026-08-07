# Customer Zero Milestone 1 — Platform Stabilization Execution Plan

## Authority and outcome

Milestone 1 is the active architectural track. It replaces hidden,
component-owned runtime locations and interruption-first workflow behavior with
explicit platform services that minimize operator attention while preserving the
trust model.

## Ordered implementation

1. **Storage authority.** `rip.paths` owns the production storage root
   (`C:\\RIP`) and the only approved areas: Workspace, Runs, Evidence,
   Artifacts, Diagnostics, Cache, Snapshots, Logs, Configuration, and State.
   Components receive an explicit root only for tests or governed migration.
2. **Mutation interpretation.** Compare retained manifest evidence, apply
   governed classifications and dependency scope, retain the explanation and
   materiality decision, and interrupt only when no safe decision is proven.
3. **Recovery journey.** Preservation is immediate; UI explains retained
   evidence, mutation reasoning, and the next governed continuation action.
   Archival capture remains an Advanced operation.
4. **Scoped continuation.** Verify the exact affected paths and declared
   dependencies when the policy proves that scope sufficient. A policy that
   requires complete verification records a separate justified operation.
5. **Platform review and performance.** Every tool receives filesystem,
   persistence, UX, interruption, and expensive-operation review backed by
   deterministic tests and operational metrics.

## Windows development configuration

Recommended Defender exclusions are limited to the RIP-owned runtime areas
under `C:\\RIP`: `Workspace`, `Runs`, `Artifacts`, `Cache`, `Snapshots`, and
`Logs`. They reduce repeated scanning of large immutable evidence and generated
artifacts. Do not exclude customer repositories, source-control metadata,
system directories, user profiles, downloads, or the whole drive. Defender is
not disabled; exclusions require local security approval and should be reviewed
when storage ownership changes.

## Migration

Existing `.rip-state`, `.rip-voice`, and `.rip-onboarding` data is migrated by
an explicit, idempotent tool after validation of ownership and content. It must
copy before recording a verified migration receipt; it must never silently
delete legacy data. New writes use the storage authority only.

## Exit evidence

The milestone requires end-to-end workflow tests for automatic safe mutation
continuation, governed pause, retained-artifact recovery, scope-bounded
verification, storage-root enforcement, and each migrated tool. Passing unit
tests alone is insufficient.
