# Supreme Decision Authority and Autonomy Control

## Trust anchor and bootstrap ceremony

`SupremeDecisionAuthority` is the sole constitutional authority. It is not an
agent capability. The initial holder is established in a one-time local,
auditable ceremony:

1. An administrator starts RIP on the intended Windows machine and explicitly
   provisions the existing non-exportable platform signing key.
2. The human holder is identified from the Windows process-token boundary; a
   typed name is not accepted as identity proof.
3. The human reviews the holder identity, the named initial constitutional
   artifacts, and the Journal publication path, then explicitly confirms the
   ceremony.
4. RIP creates a signed `rip.sda-bootstrap.v1` record and retains it once at
   `State/sda-bootstrap.json`. Existing bootstrap evidence is immutable.

This bootstrap record is the trust anchor. It deliberately does not claim to
be authorized by a pre-existing SDA. After it exists, all constitutional
changes require a signed, confirmed `rip.supreme-decision.v1` published by the
existing Journal path. No runtime operation creates or replaces bootstrap
evidence.

## Authority and action controls

`rip.authority-charter.v1` represents bounded, revocable delegated authority;
it does not transfer sovereignty. Charters enforce status, effective period,
decision class, permitted schema, scope, and delegation depth.

Every proposed autonomous action is classified through Authority, Scope,
Resource Budget, and Expected Value. The initial policy permits only bounded,
zero-network, non-mutating deterministic projections. Source mutation,
commits, constitutional decisions, Engineering Decisions, policy changes,
authority creation, and broad rewrites cannot run autonomously.

Budgets use `rip.execution-budget.v1`. The narrowest applicable valid numeric
limit controls. An over-budget action is deferred for recommendation; no code
silently expands a budget. Retained `rip.execution-record.v1` records provide
the operator projection without changing observed customer repositories.

## First decision

`first_sda_decision_draft()` prepares, but never publishes, the required first
decision. Its signing and Journal publication require the authenticated holder
to explicitly confirm it. The draft includes Producer Admission Certificate
v2, schema-bound producer admission, v1 preservation, Engineering Decision
Authority, `rip.engineering-decision.v1`, generic delegation, and initial
autonomy-budget rules.
