# ADR-0004 — Current Head is a projection only
**Status:** Accepted

**Question:** Is the current-head file commitment authority?
**Context:** Projection replacement can lag authenticated history after interruption.
**Alternatives Considered:** Authoritative current head; projection-only current head.
**Evidence:** CE-JA-003 Slice 3.
**Decision:** Current Head is a replaceable projection of authenticated Head History.
**Constitutional Justification:** Projection cannot override authenticated history.
**Consequences:** Stale projection cannot undo commitment.
**Authorities Affected:** Journal Authority.
**Related Constitutional Evidence:** CE-JA-003.
**Superseded By:** —
