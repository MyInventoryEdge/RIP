# ADR-0002 — Authenticated Head History is the sole commitment authority
**Status:** Accepted

**Question:** What proves commitment?
**Context:** Records can survive interruption before commitment.
**Alternatives Considered:** Record existence; current-head file; authenticated head history.
**Evidence:** CE-JA-002B/002C and CE-JA-003 analysis.
**Decision:** Only an authenticated Head History reference commits a publication.
**Constitutional Justification:** Durable evidence must distinguish publication from commitment.
**Consequences:** Orphans remain evidence, never inferred commitment.
**Authorities Affected:** Journal Authority.
**Related Constitutional Evidence:** CE-JA-003.
**Superseded By:** —
