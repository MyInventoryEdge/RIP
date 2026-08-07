# ADR-0006 — Append-only Publication Ledger replaces whole-ledger rewrite
**Status:** Accepted

**Question:** How must publication evidence be persisted?
**Context:** Whole-ledger rewrite made immutable evidence operationally quadratic.
**Alternatives Considered:** Rewrite; append-only ledger with pending projection.
**Evidence:** CE-JA-004 and CE-JA-005.
**Decision:** Persist pending evidence, then fsync an exact append to the ledger.
**Constitutional Justification:** Append-only evidence preserves history without mutation.
**Consequences:** Crash fixtures validate pending/orphan states explicitly.
**Authorities Affected:** Journal Authority.
**Related Constitutional Evidence:** CE-JA-005.
**Superseded By:** —
