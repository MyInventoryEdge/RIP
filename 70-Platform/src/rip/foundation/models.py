from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Iterator, Mapping


@dataclass(frozen=True, slots=True)
class Section:
    heading: str
    level: int
    body: str
    children: tuple["Section", ...] = ()


@dataclass(frozen=True, slots=True)
class FoundationArtifact:
    artifact_id: str
    title: str
    path: Path
    metadata: Mapping[str, str]
    sections: tuple[Section, ...]
    raw_markdown: str = field(repr=False)

    def section(self, heading: str) -> Section:
        wanted = normalize_heading(heading)
        for candidate in walk_sections(self.sections):
            if normalize_heading(candidate.heading) == wanted:
                return candidate
        raise KeyError(f"Section not found in {self.artifact_id}: {heading}")


@dataclass(frozen=True, slots=True)
class Foundation:
    root: Path
    constitution: FoundationArtifact
    lexicon_artifact: FoundationArtifact
    conceptual_model: FoundationArtifact
    governance: FoundationArtifact
    learning: FoundationArtifact
    lexicon: Mapping[str, str]
    primary_object: str

    @property
    def artifacts(self) -> tuple[FoundationArtifact, ...]:
        return (
            self.constitution,
            self.lexicon_artifact,
            self.conceptual_model,
            self.governance,
            self.learning,
        )

    def term(self, name: str) -> str:
        for term, definition in self.lexicon.items():
            if term.casefold() == name.casefold():
                return definition
        raise KeyError(f"Lexicon term not found: {name}")

    def status_lines(self) -> tuple[str, ...]:
        return tuple(
            f"{artifact.artifact_id}: Loaded - {artifact.title}"
            for artifact in self.artifacts
        )


def freeze_mapping(values: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(values))


def walk_sections(sections: tuple[Section, ...]) -> Iterator[Section]:
    for section in sections:
        yield section
        yield from walk_sections(section.children)


def normalize_heading(value: str) -> str:
    value = value.strip()
    while value and (value[0].isdigit() or value[0] in ". "):
        value = value[1:]
    return " ".join(value.casefold().split())
