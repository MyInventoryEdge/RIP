# CZ-RC-1 — Interrupted Run Preservation and Continuation

## Root cause

The former recovery-snapshot operation coupled three unrelated activities:
preserving an interrupted run, copying a live customer source, and proving an
archival copy against that live source. Its pre-copy measurement, copy,
post-copy measurement, and copied-tree verification amplified a single source
difference into multiple full traversals.

## Promoted boundaries

`preserve_interrupted_run` seals a receipt over RIP-owned artifacts only. It
does not enumerate, measure, read, copy, or modify the customer source. The
receipt lists retained context, lifecycle state, stages, manifests, observation
artifacts, diagnostics, classifications, decisions, policies, and the exact
integrity difference when present. Reopen reads that receipt only. Retained
manifests, observation output, stage history, and immutable contracts are never
rewritten.

`create_archival_source_snapshot` is a separate, explicitly operator-requested
archival service. Its full measure/copy/recheck work is permitted only there;
it is not recovery and cannot be called by the preservation path.

`resume_governed_onboarding` remains the explicit continuation boundary. Its
verification is never performed merely to preserve or reopen a run. Current
classification continuation still uses complete verification; a future policy
promotion may permit scoped verification only when it records the dependency
scope and justification. Otherwise the run remains governed-paused rather than
calling a new observation “recovery.”

## Guarantees and deferred materiality

On source change, observation writes the initial and final manifests plus an
exact added/removed/modified/kind/access difference, then seals the run without
another traversal. The difference is available for later governed materiality
reasoning; no path, including mutable operational state, is silently excluded.

This design complies with the existing trust-first, safe-resume, classification,
and authoritative workspace-resolution architecture. Traversal instrumentation
in the regression tests makes preservation and reopening fail if either invokes
the manifest walker or source-copy routine.
