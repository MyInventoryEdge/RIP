# ADR-0009 — Storage Authority discovered through constitutional analysis
**Status:** Accepted

**Question:** What permits safe incremental validation?
**Context:** Mutable local storage cannot prove unread prefixes unchanged.
**Alternatives Considered:** Local checkpoints; authenticated immutable storage.
**Evidence:** CE-SA-001.
**Decision:** Storage Authority is a separate future capability for immutable objects, authenticated roots, and rollback detection.
**Constitutional Justification:** Storage integrity is not Journal semantics.
**Consequences:** No implementation is authorized by this ADR.
**Authorities Affected:** Storage, Journal.
**Related Constitutional Evidence:** CE-SA-001.
**Superseded By:** —
