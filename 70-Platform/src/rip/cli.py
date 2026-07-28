from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .foundation import load_foundation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rip",
        description="Inspect RIP's governed constitutional foundation.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path to 00-Constitution. By default RIP discovers it from the current directory.",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
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
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
