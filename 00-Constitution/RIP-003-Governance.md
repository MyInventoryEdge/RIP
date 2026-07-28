# RIP-003 — Governance

**Status:** Approved Direction

## Governance Principle

The organization governs. RIP provides the structure through which governance becomes explicit, traceable, enactable, reviewable, and evolvable.

## Governance Artifact Types

### Idea
A lightweight record of a potentially important organizational insight, concern, opportunity, or change.

### Proposal
A formal request for organizational action or authority.

### Decision
The authoritative governance outcome.

### Implementation
The work performed to fulfill an approved decision.

### Validation
The evidence-based evaluation of whether implementation fulfilled the decision and intended purpose.

## Gatekeeper Authority

The Gatekeeper MAY:

- approve proposals;
- reject proposals;
- defer proposals;
- withdraw proposals where authorized;
- reopen prior proposals;
- supersede existing authority;
- require additional evidence;
- require implementation validation;
- designate implementation ownership;
- delegate bounded authority explicitly.

The Gatekeeper SHALL:

- record decision rationale;
- preserve all proposal history;
- distinguish preference, recommendation, knowledge, and authority;
- define validation expectations;
- define reconsideration criteria when appropriate;
- avoid presenting temporary expediency as permanent principle;
- identify affected artifacts and authority.

The Gatekeeper SHALL NOT:

- erase rejected or obsolete decisions from history;
- delegate constitutional authority implicitly;
- treat automated recommendations as self-ratifying;
- permit a Host to silently establish policy;
- represent inferred knowledge as approved authority without governance.

## Decision Requirements

Every decision SHALL identify:

- proposal ID;
- decision state;
- decision date;
- decision authority;
- exact decision;
- rationale;
- alternatives considered;
- affected artifacts;
- implementation requirements;
- validation requirements;
- reconsideration criteria, when applicable;
- related decisions and proposals.

## Validation Requirements

Validation SHALL identify:

- decision being validated;
- implementation examined;
- validation method;
- evidence reviewed;
- criteria;
- result;
- limitations or unresolved gaps;
- follow-up actions;
- authority accepting the result.

## Repository Alignment

When the organization has approved a coherent body of related decisions, RIP's governed artifacts SHOULD be updated in a single consistency pass.

Artificial phasing SHALL NOT be used merely to postpone documenting already approved understanding.

## Role Boundaries

### Organization and Gatekeeper
Create and authorize organizational knowledge.

### Repository
Preserves governed organizational knowledge and history.

### Engineer
Consumes, critiques, implements, and improves the governed direction.

### Host or AI
Assists discovery, inference, organization, explanation, execution, and validation within declared boundaries.

No engineer, Host, or AI becomes organizational authority merely by producing useful output.
