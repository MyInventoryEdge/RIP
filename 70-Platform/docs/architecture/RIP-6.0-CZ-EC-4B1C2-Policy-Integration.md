# CZ-EC-4B1C2 Policy Integration and Readiness Evaluation

The integration service loads only persisted immutable classification envelopes for one
retained workspace and onboarding run. It validates schema, reconstructed fingerprints,
organization/run/source binding, decision-to-record provenance, and retained-manifest scope.
It reconstructs append-only policy history deterministically, persists only an immutable
effective-policy snapshot, evaluates the retained manifest, and writes an immutable
integration summary.

Readiness is `blocked-by-conflict` for effective-policy conflicts, `awaiting-classification`
for outstanding requests or unknown entries, and `ready` only for a conflict-free policy with
no outstanding request or unknown entry. Stale retained artifacts are rejected at the loading
boundary. The service never verifies the live customer source, mutates onboarding lifecycle,
resumes onboarding, delivers notifications, or changes customer files.
