# ADR-0007 — Whole-ledger rewrite is an implementation artifact
**Status:** Accepted

**Question:** Is rewriting the complete ledger constitutionally required?
**Context:** Publication cost grew with complete persisted history.
**Alternatives Considered:** Rewrite; append.
**Evidence:** CE-JA-004.
**Decision:** Whole-ledger rewrite is not a constitutional requirement.
**Constitutional Justification:** Integrity derives from hashes, signatures, fsync, and Head History—not rewriting prior bytes.
**Consequences:** Implementations must not reintroduce it as a convenience.
**Authorities Affected:** Journal Authority.
**Related Constitutional Evidence:** CE-JA-004.
**Superseded By:** —
