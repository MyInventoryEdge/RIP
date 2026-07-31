from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .foundation import load_foundation
from .interpretation import interpret_session
from .interpretation.renderer import render_knowledge
from .interpretation.service import DEFAULT_CHUNK_CHARACTERS, DEFAULT_MODEL as INTERPRETATION_DEFAULT_MODEL
from .observation import observe_filesystem
from .reasoning import DEFAULT_MODEL, ask_repository
from .session import parse_session
from .voice import VoiceManager
from .voice.manager import TEST_PHRASE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rip",
        description="Inspect RIP's governed foundation and observable repository structure.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root or 00-Constitution path, depending on the command.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Validate Constitutional Boot and list the active corpus")
    subparsers.add_parser("constitution", help="Print the Constitution")

    lexicon = subparsers.add_parser("lexicon", help="Read a Lexicon definition")
    lexicon.add_argument("term", nargs="?", help="Term to read; omit to list all terms")

    section = subparsers.add_parser("section", help="Read a section from an artifact")
    section.add_argument("artifact", choices=["constitution", "model", "governance", "learning"])
    section.add_argument("heading", help="Section heading, with or without its number")

    subparsers.add_parser("self", help="Print RIP's currently loaded self-description")

    observe = subparsers.add_parser(
        "observe",
        help="Record deterministic filesystem observations without semantic inference",
    )
    observe.add_argument("path", nargs="?", type=Path, help="Directory to observe; defaults to repository root")
    observe.add_argument("--json", action="store_true", help="Write the complete observation set as JSON")
    observe.add_argument("--include-hidden", action="store_true", help="Include hidden entries except excluded build/cache directories")
    observe.add_argument("--all", action="store_true", help="Print every observation in human-readable output")

    parse_session_command = subparsers.add_parser("parse-session", help="Normalize an exported conversation into RIP's canonical session format")
    parse_session_command.add_argument("conversation", type=Path, help="Path to a supported conversation.json export")
    parse_session_command.add_argument("--output", required=True, type=Path, help="Directory for canonical-session.json, canonical-session.md, and parser-manifest.json")

    interpret = subparsers.add_parser("interpret", help="Extract governed knowledge candidates from a validated canonical session")
    interpret.add_argument("canonical_session", type=Path, help="Path to a validated canonical-session.json")
    interpret.add_argument("--output", required=True, type=Path, help="Directory for interpretation outputs")
    interpret.add_argument("--model", default=INTERPRETATION_DEFAULT_MODEL, help=f"Interpreter model; defaults to {INTERPRETATION_DEFAULT_MODEL}")
    interpret.add_argument("--chunk-characters", type=int, default=DEFAULT_CHUNK_CHARACTERS, help=f"Maximum canonical message characters per provider request; defaults to {DEFAULT_CHUNK_CHARACTERS}")
    render = subparsers.add_parser("render-knowledge", help="Render candidate knowledge into self-contained human review reports")
    render.add_argument("candidate_knowledge", type=Path, help="Path to candidate-knowledge.json")
    render.add_argument("--output", required=True, type=Path, help="Directory for candidate-review.html and candidate-review.md")

    ask = subparsers.add_parser(
        "ask",
        help="Ask an AI provider to interpret RIP's foundation and deterministic observations",
    )
    ask.add_argument("question", help="Question to answer from the supplied RIP evidence")
    ask.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model identifier; defaults to RIP_OPENAI_MODEL or {DEFAULT_MODEL}",
    )
    ask.add_argument("--show-metadata", action="store_true", help="Print provider, model, response ID, and token usage")
    ask.add_argument("--primary-evidence", action="append", default=[], help="Repository-relative file to load as primary task evidence; may be repeated")
    voice = subparsers.add_parser("voice", help="Configure and use spoken output")
    voice_sub = voice.add_subparsers(dest="voice_command", required=True)
    voice_sub.add_parser("status"); voice_sub.add_parser("list"); voice_sub.add_parser("enable"); voice_sub.add_parser("disable"); voice_sub.add_parser("test")
    preview = voice_sub.add_parser("preview"); preview.add_argument("voice", nargs="?"); preview.add_argument("--all", action="store_true"); preview.add_argument("--yes", action="store_true"); preview.add_argument("--output-dir")
    voice_sub.add_parser("microphones")
    record = voice_sub.add_parser("record"); record.add_argument("--output", required=True); record.add_argument("--max-seconds", type=int, default=30); record.add_argument("--device", type=int)
    listen = voice_sub.add_parser("listen"); listen.add_argument("--output"); listen.add_argument("--keep-audio", action="store_true"); listen.add_argument("--max-seconds", type=int, default=30); listen.add_argument("--device", type=int); listen.add_argument("--language")
    set_voice = voice_sub.add_parser("set"); set_voice.add_argument("voice")
    set_model = voice_sub.add_parser("set-model"); set_model.add_argument("model")
    set_speed = voice_sub.add_parser("set-speed"); set_speed.add_argument("speed", type=float)
    set_instructions = voice_sub.add_parser("set-instructions"); set_instructions.add_argument("instructions")
    speak = voice_sub.add_parser("speak"); speak.add_argument("text"); speak.add_argument("--output"); speak.add_argument("--no-play", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "parse-session":
            session = parse_session(args.conversation, args.output)
            print(f"Canonical session: {session.session_id}")
            print(f"Messages: {session.statistics.message_count}")
            print(f"Validation: {'PASS' if session.validation.passed else 'FAIL'}")
            print(f"Output: {args.output.resolve()}")
            for warning in session.validation.warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            return 0
        if args.command == "interpret":
            result = interpret_session(args.canonical_session, args.output, model=args.model, chunk_characters=args.chunk_characters)
            print("Knowledge Interpretation Complete\n")
            print("Knowledge Type:\n    Architectural Decisions")
            print(f"\nCandidates:\n    {len(result.candidates)}")
            print(f"\nEvidence Coverage:\n    {result.messages_with_evidence} messages")
            print(f"\nRejected:\n    {result.rejected_candidates}")
            print("\nValidation:\n    PASS")
            print(f"\nOutput: {args.output.resolve()}")
            return 0
        if args.command == "render-knowledge":
            result = render_knowledge(args.candidate_knowledge, args.output)
            print(f"Candidates read: {result['candidates']}")
            print(f"Candidates rendered to HTML: {result['candidates']}")
            print(f"Candidates rendered to Markdown: {result['candidates']}")
            print("Validation: PASS")
            return 0
        if args.command == "voice":
            manager = VoiceManager(Path.cwd() / ".rip-voice" / "config.json")
            if args.voice_command == "microphones":
                for item in manager.list_microphones(): print(f"{'* ' if item.default else '  '}{item.index}: {item.name} ({item.channels} input channels, {item.sample_rate} Hz)")
                return 0
            if args.voice_command in {"record", "listen"}:
                import tempfile
                output = Path(args.output) if args.output else Path(tempfile.mkstemp(suffix=".wav")[1])
                print("Listening...\nSpeak now.")
                manager.record(output, device=args.device, maximum_seconds=args.max_seconds)
                print(f"Recording stopped: {output}")
                if args.voice_command == "record": return 0
                print("Transcribing...")
                text = manager.transcribe(output, language=args.language)
                print(f"You said: {text}")
                if not args.keep_audio and not args.output: output.unlink(missing_ok=True)
                return 0
            if args.voice_command == "status":
                config = manager.load(); print(f"Enabled: {config.enabled}\nProvider: {config.provider}\nModel: {config.model}\nVoice: {config.voice}\nSpeed: {config.speed}\nInstructions: {'present' if config.instructions else 'absent'}\nPlayback enabled: {config.playback_enabled}\nConfiguration: {manager.path}\nAPI key available: {'yes' if manager.provider.ready() else 'no'}"); return 0
            if args.voice_command == "list":
                current = manager.load().voice
                for voice_name in manager.provider.list_voices(): print(f"{'* ' if voice_name == current else '  '}{voice_name}")
                return 0
            if args.voice_command == "preview":
                voices = manager.provider.list_voices() if args.all else (args.voice or manager.load().voice,)
                if args.all and not args.yes and input(f"Preview {len(voices)} voices? This will make {len(voices)} billable speech requests. [y/N] ").strip().lower() != "y": print("Preview cancelled."); return 0
                try:
                    for name in voices: print(f"Previewing voice: {name}")
                    results, error = manager.preview(voices, output_dir=args.output_dir)
                except KeyboardInterrupt: print(f"Preview interrupted after {len(locals().get('results', []))} voices."); return 1
                for result in results:
                    if result.output_path: print(f"Generated: {result.output_path}")
                if error: print(error); return 1
                return 0
            if args.voice_command == "set": manager.update(voice=args.voice)
            elif args.voice_command == "set-model": manager.update(model=args.model)
            elif args.voice_command == "set-speed": manager.update(speed=args.speed)
            elif args.voice_command == "set-instructions": manager.update(instructions=args.instructions)
            elif args.voice_command == "enable": manager.update(enabled=True)
            elif args.voice_command == "disable": manager.update(enabled=False)
            else:
                result = manager.speak(TEST_PHRASE if args.voice_command == "test" else args.text, output_path=getattr(args, "output", None), play=not getattr(args, "no_play", False))
                print(result.message); return 0 if result.success else 1
            print("Voice configuration saved."); return 0
        if args.command == "ask":
            result = ask_repository(args.question, root=args.root, model=args.model, primary_paths=args.primary_evidence)
            print("RIP Grounded Interpretation\n")
            print(result.answer)
            if result.unknown_observation_ids:
                print("\nWARNING: The provider cited observation IDs not present in the supplied evidence:", file=sys.stderr)
                for observation_id in result.unknown_observation_ids:
                    print(f"  {observation_id}", file=sys.stderr)
            if not result.cited_observation_ids:
                print("\nWARNING: The provider returned no observation citations.", file=sys.stderr)
            if args.show_metadata:
                print("\nReasoning metadata:")
                print(f"  Provider: {result.provider}")
                print(f"  Model: {result.model}")
                if result.response_id:
                    print(f"  Response ID: {result.response_id}")
                if result.input_tokens is not None:
                    print(f"  Input tokens: {result.input_tokens}")
                if result.output_tokens is not None:
                    print(f"  Output tokens: {result.output_tokens}")
                print(f"  Cited observations: {len(result.cited_observation_ids)}")
            return 0

        if args.command == "observe":
            target = args.path or args.root
            observed = observe_filesystem(target, include_hidden=args.include_hidden)
            if args.json:
                print(json.dumps(observed.to_dict(), indent=2, sort_keys=True))
            else:
                _print_observations(observed, show_all=args.all)
            return 0

        foundation = load_foundation(args.root)

        if args.command == "status":
            print("RIP Foundation\n")
            for line in foundation.status_lines():
                print(line)
            print(f"\nFoundation directory: {foundation.root}")
            print(f"Registry version: {foundation.artifact('RIP-007').metadata.get('Version')}")
            print(f"Corpus fingerprint: {foundation.corpus_fingerprint}")
            print(f"Documents registered: {len(foundation.registry_entries)}")
            print(f"Documents loaded: {len(foundation.artifacts)}")
            print(f"Constitutional Memory source: {foundation.source}")
            print("Validation result: valid")
            for identifier, label in (("RIP-001", "Mission"), ("RIP-004", "Governance"), ("RIP-006", "Chronicle"), ("RIP-007", "Registry")):
                print(f"{label} loaded: {identifier in {item.artifact_id for item in foundation.artifacts}}")
            print(f"Primary Object: {foundation.primary_object}")
            print(f"Lexicon Terms: {len(foundation.lexicon)}")
            return 0

        if args.command == "constitution":
            print(foundation.constitution.raw_markdown, end="")
            return 0

        if args.command == "lexicon":
            if args.term:
                definition = foundation.term(args.term)
                print(f"{args.term}\n{'=' * len(args.term)}")
                print(definition)
            else:
                for term in foundation.lexicon:
                    print(term)
            return 0

        if args.command == "section":
            artifact = {
                "constitution": foundation.constitution,
                "model": foundation.conceptual_model,
                "governance": foundation.governance,
                "learning": foundation.learning,
            }[args.artifact]
            selected = artifact.section(args.heading)
            print(f"{selected.heading}\n{'=' * len(selected.heading)}")
            print(selected.body)
            return 0

        if args.command == "self":
            print("RIP currently understands the following about itself:\n")
            print(f"Primary object: {foundation.primary_object}")
            print("Governing artifacts:")
            for artifact in foundation.artifacts:
                status = artifact.metadata.get("Status", "Status not declared")
                print(f"  - {artifact.artifact_id} - {artifact.title} ({status})")
            print(f"Lexicon vocabulary: {len(foundation.lexicon)} defined terms")
            print("\nRIP does not yet claim semantic reasoning, autonomous discovery, or authority.")
            return 0

        parser.error(f"Unknown command: {args.command}")
        return 2
    except (FileNotFoundError, PermissionError, ValueError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _print_observations(observed, *, show_all: bool) -> None:
    print("RIP Filesystem Observation\n")
    print(f"Observation root: {observed.root}")
    print(f"Observed at: {observed.observed_at.isoformat()}")
    print(f"Observation count: {len(observed.observations)}")
    print("\nObserved kinds:")
    for kind, count in observed.counts().items():
        print(f"  {kind}: {count}")

    top_level = [
        item for item in observed.observations
        if item.relative_path != "." and "/" not in item.relative_path
    ]
    print("\nTop-level structure:")
    for item in top_level:
        marker = "/" if item.kind == "directory" else ""
        print(f"  {item.relative_path}{marker} [{item.kind}]")

    if show_all:
        print("\nAll observations:")
        for item in observed.observations:
            print(f"  {item.observation_id}  {item.kind:<28} {item.relative_path}")

    print("\nBoundary: these are deterministic observations, not semantic conclusions or authority.")


if __name__ == "__main__":
    raise SystemExit(main())
