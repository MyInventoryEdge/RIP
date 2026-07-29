# RIP-PROP-0005 — Communication Manager

## Status

Approved for implementation.

## Decision Owner

Bob Berry

## Purpose

Establish a single governed communication pathway through which RIP publishes facts, recommendations, warnings, outcomes, and future spoken messages.

The Communication Manager is not a personality layer and does not imply consciousness. It is an architectural service that gives RIP a consistent, accountable, extensible way to communicate its state and reasoning.

## Problem

Direct console output couples RIP's subsystems to presentation. As RIP grows, the same information may need to reach several destinations:

- console output;
- structured logs;
- spoken output;
- desktop notifications;
- dashboards;
- email or other external channels.

Without a common communication model, each subsystem will format and deliver its own messages, producing duplication, inconsistency, weak auditability, and expensive future migration.

## Governing Principle

RIP subsystems publish meaningful events. Communication channels decide how those events are presented.

A subsystem should not need to know whether a message is printed, logged, spoken, displayed, or transmitted.

## Scope

Milestone 0005 will introduce:

1. a structured communication message model;
2. governed severity levels;
3. a channel contract;
4. a central Communication Manager;
5. a console channel;
6. a logging channel;
7. message filtering and speech eligibility metadata;
8. channel-failure isolation;
9. automated tests;
10. migration of at least one existing console workflow.

## Non-Goals

This milestone will not introduce:

- speech synthesis dependencies;
- voice input;
- conversational turn management;
- emotional simulation;
- claims of consciousness;
- autonomous interruption policy;
- external notification providers.

Those capabilities may be added later as channels or policies without changing the core event contract.

## Message Model

Each communication event must contain, at minimum:

- `text` — the human-readable message;
- `severity` — governed importance level;
- `category` — functional classification;
- `source` — originating subsystem when known;
- `speak` — whether the originating subsystem considers speech appropriate;
- `timestamp` — creation time;
- `metadata` — optional structured context.

The initial severity set is:

- `DEBUG`
- `INFO`
- `SUCCESS`
- `WARNING`
- `ERROR`
- `CRITICAL`

`SUCCESS` is intentionally distinct from `INFO` because verified completion is a first-class platform event.

## Channel Contract

Every communication channel must accept the same structured message and deliver it according to its own responsibilities.

Conceptual contract:

```python
class CommunicationChannel(Protocol):
    def deliver(self, message: CommunicationMessage) -> None:
        ...
```

Initial channels:

- `ConsoleChannel`
- `LoggingChannel`

Future channels may include:

- `SpeechChannel`
- `DesktopNotificationChannel`
- `DashboardChannel`
- `EmailChannel`

## Manager Responsibilities

The Communication Manager will:

- construct or accept structured messages;
- fan messages out to registered channels;
- preserve message consistency across channels;
- isolate channel failures so one failed destination does not crash RIP;
- provide predictable return values for testing and audit;
- support future filtering and policy controls.

The Communication Manager will not:

- reinterpret technical facts;
- invent personality;
- alter subsystem decisions;
- silently suppress critical messages;
- make governance decisions.

## Speech Policy Foundation

The `speak` field expresses eligibility or intent, not an unconditional command.

A future speech channel will combine message intent with user configuration and channel policy. The expected default policy is:

- `CRITICAL` — always speak when speech is enabled;
- `ERROR` — normally speak;
- `WARNING` — speak selectively;
- `SUCCESS` — speak for significant task completion;
- `INFO` — normally remain silent;
- `DEBUG` — never speak.

## Failure Isolation

A failed channel must not prevent other channels from receiving the message. Channel failures must be observable through a safe mechanism that avoids recursive communication failure.

## Validation Requirements

Automated tests must verify:

- message construction;
- default field values;
- channel fan-out;
- delivery ordering where ordering is promised;
- console formatting;
- logging behavior;
- filtering behavior;
- metadata preservation;
- channel-failure isolation;
- no mutation of immutable message content;
- successful migration of at least one current console path.

## Definition of Done

Milestone 0005 is complete when:

- a central Communication Manager exists;
- console and logging channels implement the shared contract;
- structured messages use governed severity and category values;
- one channel failure does not crash RIP or block remaining channels;
- tests pass locally and through GitHub Actions;
- at least one existing workflow no longer writes directly to the console;
- implementation documentation identifies how a future Speech Channel attaches;
- no text-to-speech dependency has been introduced.

## Architectural Consequence

After this milestone, new RIP subsystems should communicate through the Communication Manager rather than direct `print()` calls or channel-specific integrations.

This creates the stable boundary required for RIP to gain a voice later without coupling speech technology to reasoning, observation, governance, or repository intelligence.