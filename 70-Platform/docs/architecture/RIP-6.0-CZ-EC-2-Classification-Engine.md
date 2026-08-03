# RIP 6.0 — CZ-EC-2 Classification Engine

## Boundary

CZ-EC-2 deterministically evaluates a previously complete source manifest against a CZ-EC-1 immutable policy. It does not inspect the source filesystem, mutate customer repositories, change onboarding state, pause or resume a run, notify a person, or render UI.

**Classification changes interpretation, never observation.** Every manifest entry remains represented in the evaluation result, including Operational State, Generated Artifact, Inventory Only, Unknown, directories, symlinks, and access-state entries.

## Resolution

Exact paths have precedence over path-globs. Path-globs use the restricted normalized POSIX representation established in CZ-EC-1: `*` stays within a path segment, `?` matches one non-separator, and `**` matches zero or more complete segments. The engine never follows a symlink to evaluate a pattern.

Among matching globs, the most literal and least wildcarded scope wins deterministically. Equal-precedence records that disagree create a `ClassificationConflict`; the affected entry becomes `UNKNOWN` with `BLOCKING` treatment. No filename, extension, directory name, or heuristic changes an unknown entry.

Policies and all records must name the same source-manifest fingerprint. A stale policy or a malformed, duplicate, or unsorted manifest is rejected locally.

## Fingerprints

The Complete Source Fingerprint hashes every evaluated manifest entry: path, kind, content/symlink/access value, and size. Classifications never change it.

The Organizational Evidence Fingerprint hashes organizational evidence, conservative Unknown entries, and blocking Generated Artifacts. Operational State and Inventory Only remain visible in the result but do not participate. A Generated Artifact with explicit `NON_BLOCKING_REPORTED` treatment remains inventoried, content-hashed, visible, and part of the Complete Source Fingerprint, but is excluded from the Organizational Evidence Fingerprint.

The evaluation, each entry, every conflict, and the summary carry deterministic SHA-256 fingerprints based on canonical JSON-compatible values.

## Deferred work

CZ-EC-2 does not implement Awaiting Classification, onboarding execution changes, pause/resume, lifecycle transitions, customer interaction, UI panels, attention events, notification providers, recovery workflow, or automatic cloud-worker handling.
