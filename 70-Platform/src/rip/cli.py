from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .foundation import load_foundation
from .observation import observe_filesystem
from .reasoning import DEFAULT_MODEL, ask_repository


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
    subparsers.add_parser("status", help="Verify and list the five foundation artifacts")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "ask":
            result = ask_repository(args.question, root=args.root, model=args.model)
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
