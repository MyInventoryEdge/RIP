#!/usr/bin/env python3
"""Export one loaded ChatGPT conversation from an authenticated browser profile."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


MARKDOWN_EXTRACTOR = r"""
() => {
  const escapeText = (value) => value.replace(/\\/g, "\\\\").replace(/([*_`])/g, "\\$1");
  const text = (node) => (node.innerText || node.textContent || "").replace(/\r/g, "").trim();
  const render = (node) => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || "";
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const tag = node.tagName.toLowerCase();
    if (tag === "pre") {
      const code = node.querySelector("code");
      const language = [...(code?.classList || [])].find((item) => item.startsWith("language-"))?.slice(9) || "";
      return "\n\n```" + language + "\n" + text(code || node) + "\n```\n\n";
    }
    if (tag === "code") return "`" + text(node) + "`";
    if (/^h[1-6]$/.test(tag)) return "\n\n" + "#".repeat(Number(tag[1])) + " " + text(node) + "\n\n";
    if (tag === "br") return "\n";
    if (tag === "strong" || tag === "b") return "**" + [...node.childNodes].map(render).join("").trim() + "**";
    if (tag === "em" || tag === "i") return "*" + [...node.childNodes].map(render).join("").trim() + "*";
    if (tag === "a") return "[" + text(node) + "](" + (node.href || "") + ")";
    if (tag === "li") return "\n- " + [...node.childNodes].map(render).join("").trim();
    if (tag === "blockquote") return "\n> " + text(node).replace(/\n/g, "\n> ") + "\n";
    if (tag === "hr") return "\n\n---\n\n";
    if (tag === "table") return "\n\n" + text(node) + "\n\n";
    const body = [...node.childNodes].map(render).join("");
    return ["p", "div", "section"].includes(tag) ? "\n\n" + body.trim() + "\n\n" : body;
  };
  const turns = [...document.querySelectorAll('[data-message-author-role]')];
  return turns.map((turn, index) => {
    const role = turn.getAttribute('data-message-author-role') || 'unknown';
    const content = turn.querySelector('.markdown') || turn.querySelector('[data-message-content]') || turn;
    return { index, role, markdown: render(content).replace(/\n{3,}/g, '\n\n').trim() };
  }).filter((message) => message.markdown);
}
"""


def scroll_until_complete(page, *, timeout_seconds: int) -> None:
    """Scroll until both document height and message count remain stable."""
    deadline = time.monotonic() + timeout_seconds
    stable_rounds = 0
    previous = None
    while time.monotonic() < deadline:
        snapshot = page.evaluate("""() => ({
          height: document.documentElement.scrollHeight,
          messages: document.querySelectorAll('[data-message-author-role]').length
        })""")
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(900)
        if snapshot == previous:
            stable_rounds += 1
            if stable_rounds >= 3:
                return
        else:
            stable_rounds = 0
        previous = snapshot
    raise RuntimeError(f"Conversation did not finish loading within {timeout_seconds} seconds.")


def write_exports(output_dir: Path, url: str, messages: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    exported_at = datetime.now(timezone.utc).isoformat()
    conversation = {"source_url": url, "exported_at": exported_at, "messages": messages}
    markdown = "\n\n".join(f"## {message['role'].title()}\n\n{message['markdown']}" for message in messages) + "\n"
    manifest = {
        "exported_at": exported_at,
        "source_url": url,
        "message_count": len(messages),
        "files": ["conversation.json", "conversation.md"],
    }
    (output_dir / "conversation.json").write_text(json.dumps(conversation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "conversation.md").write_text(markdown, encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def open_browser(playwright, args):
    """Attach to the dedicated Edge session started by start-authenticated-edge.ps1."""
    try:
        browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=5_000)
        if not browser.contexts:
            raise RuntimeError("The dedicated Edge session has no browser context.")
        return browser, browser.contexts[0]
    except PlaywrightError as exc:
        raise RuntimeError(
            "Cannot connect to the dedicated Edge session. Run start-authenticated-edge.ps1, "
            "sign in to ChatGPT in that Edge window, then run the exporter again."
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a complete ChatGPT conversation through the dedicated authenticated Edge session.")
    parser.add_argument("url", help="ChatGPT conversation URL")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd(), help="Directory for conversation.json, conversation.md, and manifest.json")
    parser.add_argument("--timeout", type=int, default=120, help="Maximum seconds to wait for complete loading")
    args = parser.parse_args(argv)

    if "chatgpt.com" not in args.url and "chat.openai.com" not in args.url:
        parser.error("URL must be a ChatGPT conversation URL.")

    try:
        with sync_playwright() as playwright:
            _browser, context = open_browser(playwright, args)
            page = None
            try:
                page = context.new_page()
                page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                page.wait_for_selector('[data-message-author-role]', timeout=args.timeout * 1000)
                scroll_until_complete(page, timeout_seconds=args.timeout)
                messages = page.evaluate(MARKDOWN_EXTRACTOR)
            finally:
                # This is the user's browser context. Only the exporter-created
                # tab is closed; Playwright disconnects when its process exits.
                if page is not None:
                    page.close()
        if not messages:
            raise RuntimeError("No ChatGPT messages were found after the conversation finished loading.")
        write_exports(args.output_dir, args.url, messages)
        print(f"Exported {len(messages)} messages to {args.output_dir.resolve()}")
        return 0
    except (PlaywrightError, OSError, RuntimeError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
