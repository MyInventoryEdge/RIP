# ADR-0012 — Transaction Authority retirement
**Status:** Accepted

**Question:** Does Transaction Authority own one constitutional truth that no other Authority owns?

**Context:** CE-TA-001 established that the named component issued only an intended lifecycle record, had no call sites, and explicitly refused execution. Journal Authority owns authenticated publication. Trust execution and the lifecycle executor own the currently implemented decision execution and state advancement. No transaction-specific replay, recovery, acknowledgement, completion, failure, or compensation truth exists.

**Alternatives Considered:** Retain Transaction Authority; create a replacement Authority; retire it.

**Evidence:** CE-TA-001; `rip.transactions`; Trust execution and lifecycle evidence contracts.

**Decision:** Retire Transaction Authority. It issues no new evidence and performs no execution. No replacement Authority is created. The retired module remains solely as historical evidence until governed preservation requirements authorize its removal.

**Constitutional Justification:** An Authority may exist only for a singular, durable, independently reconstructable truth. Reality established none for Transaction Authority.

**Consequences:** The platform signing identity is `rip-platform-key-provider`, not Transaction Authority. Legacy key identity remains accepted only to verify historical signatures; it cannot issue new evidence. Journal, Producer Policy, Trust, lifecycle, and onboarding ownership are unchanged.

**Authorities Affected:** Retired Transaction Authority; PlatformKeyProvider naming only.

**Related Constitutional Evidence:** CE-TA-001.

**Superseded By:** —
