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

## Canonical session parsing

`rip parse-session` converts a supported conversation export into a source-independent canonical session. It does not classify, summarize, interpret, or call an AI model; it preserves every message's Markdown, role, source identifier, order, and unrecognized source metadata.

```powershell
rip parse-session C:\RIP\tools\chatgpt-exporter\validation-export-complete\conversation.json --output C:\RIP\parsed-session
```

The output directory contains `canonical-session.json` (structured canonical data), `canonical-session.md` (a readable full transcript), and `parser-manifest.json` (source, statistics, warnings, and validation result). Parsing fails rather than producing output when counts, order, source identifiers, or Markdown preservation cannot be validated. The current ChatGPT exporter supplies no upstream turn ID and its viewport-local `index` values may repeat; RIP retains each raw index in source metadata, uses deterministic source-order identifiers, and records the limitation as a warning.

## Voice interaction

Voice is an optional interface preference, not constitutional state. It uses `OPENAI_API_KEY`, OpenAI speech synthesis and transcription, and a microphone accessible through `sounddevice`. Configuration is local at `70-Platform/.rip-voice/config.json` and is ignored by Git.

The Reasoning Console supports typed and spoken questions. Click **Talk** or press **F4**, speak a question, and RIP places the recognized text into the normal question entry before submitting through the existing reasoning workflow. RIP automatically speaks completed responses; **Mute** disables only response playback. **Voice Status** shows the configured and resolved microphone, voice, speech-enabled setting, and transcription model.

Voice capture ends after configured end-of-speech silence (default 1.5 seconds), or after the configured maximum duration (default 60 seconds). While recording, the Talk button becomes **Stop** for immediate finalization and transcription. The console shows each voice state—Listening, silence finalization, Transcribing, Reasoning, speech synthesis, and Playing—and emits duration information through the voice logger. The local voice configuration also supports `maximum_recording_seconds`, `minimum_speech_seconds`, `silence_timeout_seconds`, `silence_threshold`, `show_timing`, and `auto_stop_enabled`.

Launch the console from `C:\RIP\70-Platform`:

```powershell
$env:PYTHONPATH = "src"
& "C:\INVENTORY_EDGE\runtime\python314\python.exe" -m rip.console.app
```

For command-line configuration and diagnostics, use `rip voice status`, `rip voice microphones`, `rip voice set-microphone <index>`, `rip voice record --output sample.wav`, `rip voice listen --output sample.wav`, and `rip voice speak "Hello" --output hello.wav`. If voice input is unavailable, confirm that a microphone is connected and listed by `rip voice microphones`; if speech fails, confirm `OPENAI_API_KEY` is present in the process environment. Generated WAV files are preserved when playback fails so they can be opened directly for troubleshooting.

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

## Phase 6A: Trust-first organization onboarding

The console now includes **Organization Onboarding**, a separate, explicit onboarding window for a single organization and approved repository. Its persistent banner states **Customer Sources — Read Only** and discloses that onboarding records are written only to the isolated RIP-controlled workspace outside the observed repository. Phase 6A records deterministic repository observations and truthful discovery-feed events, and presents an evidence-linked Understanding Meter and Observation Summary.

Customer repositories and approved external sources are never modified during Phase 6A. The phase does not promote governance, activate an organization, initialize Organizational Memory, take operational customer action, or call a provider during repository observation. Reasoning-capability validation verifies only local configuration and declared context support; live provider connectivity and model accessibility are not probed. Each onboarding attempt is a separately identified, restartable run; its audit and generated observation records remain in the isolated RIP workspace rather than in customer sources.
# Knowledge Interpretation

RIP can turn a validated `canonical-session.json` into traceable candidate
architectural decisions. It never alters the session and does not treat a
candidate as approved knowledge. Every candidate includes exact, offset-based
evidence from canonical message IDs for human review; offsets are zero-based
Python Unicode code-point positions in the source Markdown.

```powershell
$env:PYTHONPATH = "src"
python -m rip.cli interpret C:\RIP\60-Reference\Knowledge\Session-Archives\chatgpt-production-0001\canonical-session.json --output C:\Temp\rip-interpretation
```

The output directory contains `candidate-knowledge.json`,
`interpretation-manifest.json`, and `interpretation-report.md`. The command
fails when the input session did not pass parser validation or an AI response
cannot be validated after one explicit repair attempt. The architectural
decision prompt is a version-controlled asset at `prompts/architectural_decisions.md`.

## Large primary evidence

RIP sends in-budget primary evidence losslessly and unchanged. When exactly one supplied
primary artifact makes the complete request exceed the local safe input budget, RIP
automatically applies deterministic lexical retrieval when the artifact is a valid
canonical-session JSON artifact. It selects only complete, unchanged governed chunks from
that one artifact using the user question and an explicit budget computed by reasoning
orchestration. The provider receives the resulting evidence through the same evidence
package and remains unaware that retrieval occurred.

Retrieval audit data remains internal to RIP for provenance, reproducibility, diagnostics,
and validation. It is not reasoning context. If no chunks match, if the artifact has no
compatible chunker, or if multiple oversized artifacts are supplied, RIP fails locally and
does not call the provider. Additional artifact-specific chunkers and multi-artifact budget
allocation are outside the current capability.
