# RIP Platform

Executable platform for the Repository Intelligence Platform.

## Milestone 0001 — Foundation

```powershell
rip status
rip self
rip lexicon Authority
```

## Milestone 0002 — Filesystem Observation

RIP can now record deterministic evidence about the structure of its own repository without claiming semantic interpretation.

```powershell
rip observe
rip observe --all
rip observe --json
```

The default observation target is the nearest ancestor containing `.git`, or both `00-Constitution` and `70-Platform`. A path may also be supplied explicitly:

```powershell
rip observe C:\RIP
```

The observer records stable IDs, paths, evidence kinds, timestamps, and basic file metadata. It excludes common generated/cache directories such as `.git`, `__pycache__`, `node_modules`, `bin`, and `obj`.

## Install or update

From `C:\RIP\70-Platform`:

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
```

No network access, AI provider, database, or non-standard Python dependency is required.

## Constitutional Boot and Memory

RIP bootstraps `RIP-000` and `RIP-007`, discovers the active Constitutional Corpus from the Registry, validates every registered artifact, and retains a validated Constitutional Memory. The runtime state is stored atomically at `70-Platform/.rip-state/constitutional-memory.json`, is ignored by Git, and is reused when source signatures are unchanged. A changed registry or constitutional artifact rebuilds the validated memory; corrupt state is rejected and recovered from the authoritative Markdown corpus.

## Milestone 0003: Grounded reasoning

RIP can send its governed foundation and current deterministic observation set to an OpenAI reasoning provider:

```powershell
rip ask "What do you know about yourself?"
```

The command reads `OPENAI_API_KEY` from the environment. The model defaults to `gpt-5.5` and can be changed without code changes:

```powershell
$env:RIP_OPENAI_MODEL = "your-model-id"
rip ask "What do you know about yourself?" --show-metadata
```

The provider receives a structured evidence package, not direct filesystem access. Repository claims are instructed to cite exact observation IDs. Output is explicitly bounded as AI interpretation rather than organizational authority.

## Milestone 0004A - RIP Reasoning Console

The temporary Windows testing console provides a simple chat-style interface over the same reasoning service used by `rip ask`.

Launch after installation with:

```powershell
rip-console
```

or double-click/run:

```powershell
.\START-RIP-CONSOLE.ps1
```

The console includes:

- a question box with Enter-to-send and Shift+Enter for a new line;
- live status messages for repository discovery, foundation loading, observation, evidence construction, and reasoning;
- a scrollable conversation transcript;
- one-click copying of the latest RIP response;
- optional provider, model, token, response-ID, elapsed-time, and citation details;
- clear conversation and friendly error presentation.

This console is intentionally temporary and contains no separate reasoning implementation. It calls `rip.reasoning.ask_repository` directly so it can later be replaced by the permanent application UI without changing RIP's reasoning architecture.
