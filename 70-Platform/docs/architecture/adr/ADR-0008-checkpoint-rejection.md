# ADR-0008 — Checkpoint-only incremental validation is rejected on mutable local storage
**Status:** Accepted

**Question:** Can a signed checkpoint replace replay on mutable local storage?
**Context:** Unread historic bytes can be changed without altering a signed checkpoint.
**Alternatives Considered:** Checkpoint-only validation; full replay.
**Evidence:** CE-JA-007 and CE-JA-008.
**Decision:** Checkpoint-only incremental validation is rejected.
**Constitutional Justification:** A digest detects mutation only when its summarized bytes are re-read.
**Consequences:** Full replay remains mandatory absent authenticated immutable storage.
**Authorities Affected:** Journal, future Storage Authority.
**Related Constitutional Evidence:** CE-JA-007–008.
**Superseded By:** —
