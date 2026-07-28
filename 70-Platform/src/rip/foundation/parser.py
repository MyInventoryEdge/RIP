from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import FoundationArtifact, Section, freeze_mapping

TITLE_RE = re.compile(r"^#\s+(?P<id>RIP-\d{3})\s+[—-]\s+(?P<title>.+?)\s*$")
HEADING_RE = re.compile(r"^(?P<marks>#{2,6})\s+(?P<heading>.+?)\s*$")
META_RE = re.compile(r"^\*\*(?P<key>[^*]+):\*\*\s*(?P<value>.+?)\s*$")


@dataclass
class _MutableSection:
    heading: str
    level: int
    lines: list[str] = field(default_factory=list)
    children: list["_MutableSection"] = field(default_factory=list)

    def freeze(self) -> Section:
        return Section(
            heading=self.heading,
            level=self.level,
            body="\n".join(self.lines).strip(),
            children=tuple(child.freeze() for child in self.children),
        )


def parse_artifact(path: Path) -> FoundationArtifact:
    raw = path.read_text(encoding="utf-8-sig")
    lines = raw.splitlines()
    if not lines:
        raise ValueError(f"Artifact is empty: {path}")

    title_match = TITLE_RE.match(lines[0])
    if not title_match:
        raise ValueError(f"Invalid RIP artifact title in {path.name}: {lines[0]!r}")

    metadata: dict[str, str] = {}
    roots: list[_MutableSection] = []
    stack: list[_MutableSection] = []

    for line in lines[1:]:
        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group("marks"))
            node = _MutableSection(heading=heading_match.group("heading"), level=level)
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)
            continue

        if not roots:
            meta_match = META_RE.match(line)
            if meta_match:
                metadata[meta_match.group("key").strip()] = meta_match.group("value").strip()
            continue

        if stack:
            stack[-1].lines.append(line)

    return FoundationArtifact(
        artifact_id=title_match.group("id"),
        title=title_match.group("title").strip(),
        path=path.resolve(),
        metadata=freeze_mapping(metadata),
        sections=tuple(root.freeze() for root in roots),
        raw_markdown=raw,
    )
