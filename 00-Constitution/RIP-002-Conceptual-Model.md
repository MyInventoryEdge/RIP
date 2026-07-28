# RIP-002 — Conceptual Model

**Status:** Approved Direction

## Primary Model

```text
Organization
├── People
├── Products
├── Repositories
├── Services
├── Infrastructure
├── Concepts
├── Providers
├── Knowledge
├── Governance
├── Operations
├── Changes
├── Hosts
└── History
```

The Organization is the primary object. Every other first-class object exists within, serves, describes, governs, changes, or provides evidence about the organization.

## Three Foundational Pillars

```text
                 Organization
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     Knowledge     Governance     Execution
```

### Knowledge
What the organization understands, including provenance, evidence, relationships, uncertainty, and history.

### Governance
What the organization has authorized, rejected, deferred, superseded, or designated for reconsideration.

### Execution
How people, Hosts, services, tools, workflows, and providers apply governed knowledge.

## Knowledge Lifecycle

```text
Conversation
    ↓
Idea
    ↓
Proposal
    ↓
Decision
    ↓
Implementation
    ↓
Validation
    ↓
Institutional Knowledge
```

Artifacts may move backward or branch when reconsidered, rejected, superseded, or reopened. No lifecycle state erases history.

## Authority, Evidence, Knowledge, and History

These bodies remain distinguishable:

### Authority
What currently governs.

### Evidence
What has been observed.

### Knowledge
What the organization currently understands, including degree of confidence and provenance.

### History
How evidence, knowledge, and authority evolved.

Evidence does not become authority merely because it exists. Inferred knowledge does not become authority merely because it is persuasive. History does not remain authority merely because it once governed.

## Supplied and Inferred Knowledge

```text
Authorized Organizational Sources ──► Supplied Knowledge
Repositories / Services / Systems ───► Technical Evidence
Technical Evidence + Analysis ───────► Inferred Knowledge
Supplied + Inferred Knowledge ───────► Proposals and Understanding
Governance ──────────────────────────► Authority
```

## Concepts and Providers

```text
Concept
   │
   ├── required capabilities
   ├── organizational purpose
   ├── constraints
   └── relationships
           │
           ▼
Provider Implementation
```

A provider fulfills a concept. It does not define the concept.

## Operations

```text
Governed Knowledge
+ Current Evidence
+ Dependencies
+ Authority
+ Organizational Structure
              ↓
       Generated Operations
```

Operational views should be generated from current organizational understanding rather than maintained as disconnected manual representations.

## Changes

```text
Origin
  ↓
Idea / Proposal
  ↓
Decision
  ↓
Implementation
  ↓
Operational Effect
  ↓
Validation
  ↓
Updated Knowledge and History
```

## Construction Method

```text
Observe
  ↓
Extract
  ↓
Represent Provenance
  ↓
Generalize into Concepts
  ↓
Govern
  ↓
Standardize
  ↓
Implement
  ↓
Validate
  ↓
Learn
  ↓
Repeat
```
