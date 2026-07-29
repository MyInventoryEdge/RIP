from __future__ import annotations

import os
import sys

from openai import OpenAI


def main() -> int:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        return 1

    model = os.getenv("RIP_OPENAI_MODEL", "gpt-5.5")
    client = OpenAI(api_key=key)
    response = client.responses.create(
        model=model,
        input="Reply only with: RIP connection successful.",
    )
    print("\n=== RESPONSE ===")
    print(response.output_text)
    print(f"\nModel: {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
