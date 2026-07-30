# RIP-007 — Constitutional Document Registry

**Document ID:** RIP-007  
**Title:** Constitutional Document Registry  
**Status:** Ratified  
**Authority:** RIP-000 Constitution  
**Classification:** Governance (Normative)  
**Version:** 1.1  
**Effective Date:** 2026-07-29  
**Owner:** Gatekeeper  
**Parent Authority:** RIP-000 Constitution

---

## Purpose

The Constitutional Document Registry is the authoritative catalog of the governed constitutional corpus within the Repository Intelligence Platform (RIP).

It establishes a single source of truth for constitutional document identity, authority, status, classification, and lineage.

Every governed constitutional artifact SHALL appear in this Registry exactly once.

## Registry Principles

The Registry SHALL:

- establish a unique identity for every governed constitutional artifact;
- define each artifact's constitutional authority;
- record document lineage and supersession;
- distinguish normative documents from historical and informative documents;
- support governance validation and repository integrity;
- enable automated governance auditing.

## Required Registry Fields

Each governed constitutional artifact SHALL have, directly or by an explicitly governed default, the following metadata:

| Field | Meaning |
|---|---|
| Document ID | Permanent unique identifier |
| Sequence | Deterministic constitutional boot order |
| Title | Official governed title |
| Filename | Canonical repository filename for the artifact |
| Classification | Constitutional, Governance, Historical, Engineering, or Informative |
| Status | Draft, Proposed, Ratified, Superseded, or Retired |
| Authority | Source from which the artifact derives authority |
| Version | Current governed version |
| Effective Date | Date the current status became effective |
| Owner | Steward responsible for maintenance |
| Parent Authority | Immediate governing authority |
| Supersedes | Earlier artifact replaced by this one |
| Superseded By | Successor artifact, when applicable |
| Notes | Additional governance context |

## Initial Constitutional Registry

| Sequence | Document ID | Title | Filename | Classification | Status | Authority | Version | Effective Date | Owner | Parent Authority | Supersedes | Superseded By | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | RIP-000 | Constitution | RIP-000-Constitution.md | Constitutional | Ratified | Organization through the Gatekeeper | 1.1 | 2026-07-29 | Gatekeeper | Self-governing constitutional authority | None | None | Highest-level normative authority in the RIP corpus; establishes governed memory domains |
| 1 | RIP-001 | Mission | RIP-001-Mission.md | Constitutional | Ratified | RIP-000 | 1.0 | 2026-07-29 | Gatekeeper | RIP-000 | Historical mission language distributed across early governance | None | Canonical statement of why RIP exists |
| 2 | RIP-002 | Lexicon | RIP-002-Lexicon.md | Constitutional | Ratified | RIP-000 | 1.1 | 2026-07-29 | Gatekeeper | RIP-000 | None | None | Canonical governed terminology, including governed memory domains |
| 3 | RIP-003 | Conceptual Model | RIP-003-Conceptual-Model.md | Constitutional | Ratified | RIP-000 | 1.1 | 2026-07-29 | Gatekeeper | RIP-000 | None | None | Canonical model of authority, evidence, history, learning, governance, and retained memory |
| 4 | RIP-004 | Governance | RIP-004-Governance.md | Governance | Ratified | RIP-000 | 1.0 | 2026-07-29 | Gatekeeper | RIP-000 | None | None | Defines governance authority and decision obligations |
| 5 | RIP-005 | Organizational Learning | RIP-005-Organizational-Learning.md | Governance | Ratified | RIP-000 | 1.1 | 2026-07-29 | Gatekeeper | RIP-000 | None | None | Defines learning, governed memory retention, constitutional refresh, evidence, and governance |
| 6 | RIP-006 | Governance Chronicle | RIP-006-Governance-Chronicle.md | Historical | Ratified | RIP-000 | 1.1 | 2026-07-29 | Gatekeeper | RIP-000 | Informal and distributed governance history | None | Governed but non-normative institutional record; includes RIP-AMD-0001 |
| 7 | RIP-007 | Constitutional Document Registry | RIP-007-Constitutional-Document-Registry.md | Governance | Ratified | RIP-000 | 1.1 | 2026-07-29 | Gatekeeper | RIP-000 | Informal document inventory | None | Authoritative catalog of governed constitutional artifacts and their active versions |

## Governance Rules

1. No governed constitutional artifact may exist without a Registry entry.
2. Document identifiers are permanent and SHALL NOT be reused.
3. Superseded and retired constitutional artifacts SHALL remain registered to preserve historical traceability.
4. A change affecting a governed constitutional artifact's identity, status, authority, classification, version, ownership, or lineage SHALL include the corresponding Registry update.
5. The Registry SHALL distinguish current authority from historical context.
6. Automated or manual validation SHALL verify consistency between registered artifacts and repository contents.
7. The Registry does not itself elevate an unratified document to authority merely by listing it. Status and authority SHALL reflect the actual governance decision.

## Stewardship

The Registry is maintained under the authority of RIP-000.

Changes to Registry entries SHALL be traceable to the governance action that authorized the corresponding artifact or metadata change.

Changes to the Registry's required fields or governance rules require approval through constitutional governance.

## Related Constitutional Documents

- RIP-000 — Constitution
- RIP-001 — Mission
- RIP-002 — Lexicon
- RIP-003 — Conceptual Model
- RIP-004 — Governance
- RIP-005 — Organizational Learning
- RIP-006 — Governance Chronicle
