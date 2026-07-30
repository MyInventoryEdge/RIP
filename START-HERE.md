# Start Here

RIP is a governed organizational knowledge platform.

Do not begin by treating RIP as a codebase, repository scanner, or documentation collection. Begin by understanding why RIP exists, what governs it, how it represents organizational reality, and how understanding becomes durable institutional knowledge.

## Recommended Reading Order

1. [`RIP-000 — Constitution`](00-Constitution/RIP-000-Constitution.md)
2. [`RIP-001 — Mission`](00-Constitution/RIP-001-Mission.md)
3. [`RIP-002 — Lexicon`](00-Constitution/RIP-002-Lexicon.md)
4. [`RIP-003 — Conceptual Model`](00-Constitution/RIP-003-Conceptual-Model.md)
5. [`RIP-004 — Governance`](00-Constitution/RIP-004-Governance.md)
6. [`RIP-005 — Organizational Learning`](00-Constitution/RIP-005-Organizational-Learning.md)
7. [`RIP-006 — Governance Chronicle`](00-Constitution/RIP-006-Governance-Chronicle.md)
8. [`RIP-007 — Constitutional Document Registry`](00-Constitution/RIP-007-Constitutional-Document-Registry.md)
9. [`RIP Vision`](00-Vision/RIP-Vision.md)
10. [`RIP-PROP-0003 — Product Vision and Platform Direction`](20-Proposals/RIP-PROP-0003-Product-Vision-and-Platform-Direction.md)
11. [`DEC-0003 — Product Vision and Platform Direction`](30-Evolution/Decisions/DEC-0003-Product-Vision-and-Platform-Direction.md)
12. [`VAL-0003 — Repository Alignment`](30-Evolution/Validation/VAL-0003-Repository-Alignment.md)
13. [`README.md`](README.md)

## Constitutional Architecture

```text
                         RIP-001
                          Mission
                             │
                             ▼
                         RIP-000
                       Constitution
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
       RIP-002            RIP-003            RIP-004
        Lexicon       Conceptual Model       Governance
                             │                  │
                             ▼                  ├──────────────┐
                          RIP-005               ▼              ▼
                    Organizational Learning  RIP-006        RIP-007
                                           Chronicle       Registry
                                      (historical,       (authoritative
                                      non-normative)      catalog)
```

The diagram is an orientation aid, not an independent source of authority. The documents themselves and the Constitutional Document Registry control.

## What Each Constitutional Document Answers

- **RIP-000 — Constitution:** What are RIP's enduring governing principles and boundaries?
- **RIP-001 — Mission:** Why does RIP exist?
- **RIP-002 — Lexicon:** What do RIP's governed terms mean?
- **RIP-003 — Conceptual Model:** How does RIP represent organizational reality and understanding?
- **RIP-004 — Governance:** How is authority created, changed, and exercised?
- **RIP-005 — Organizational Learning:** How does experience become durable governed knowledge?
- **RIP-006 — Governance Chronicle:** How and why did RIP's governance evolve?
- **RIP-007 — Constitutional Document Registry:** What governed artifacts exist, and what is their status and authority?

## What a New Engineer Should Understand

After reading the repository, a new engineer should be able to explain that:

- RIP exists to prevent organizations from losing knowledge, decisions, rationale, context, lessons, and institutional memory;
- the Organization is RIP's primary object;
- knowledge is RIP's primary enduring asset;
- governance determines authority;
- repositories are sources of knowledge, not the center of the platform;
- AI and Hosts may infer, recommend, and execute, but may not silently create authority;
- important decisions must not remain trapped in conversations;
- concepts are modeled independently from providers and technologies;
- implementation is incomplete until it has been validated;
- historical context remains preserved without silently becoming current authority;
- every governed artifact must be registered;
- RIP must apply these principles to itself.
