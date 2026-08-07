# ADR-0010 — Deployment classes determine incremental-validation permission
**Status:** Accepted

**Question:** When is incremental validation constitutionally permitted?
**Context:** Signed local state alone cannot detect whole-store rollback.
**Alternatives Considered:** Universal permission; deployment-class permission.
**Evidence:** CE-SA-002.
**Decision:** Only hardware-anchored, externally witnessed, or quorum-anchored deployments may permit it; local-only storage may not.
**Constitutional Justification:** Anti-rollback is an explicit trust dependency.
**Consequences:** Missing or uncertain anchor fails closed.
**Authorities Affected:** Future Storage Authority, Journal Authority.
**Related Constitutional Evidence:** CE-SA-002.
**Superseded By:** —
