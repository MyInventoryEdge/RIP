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
class RegistryEntry:
    sequence: int
    document_id: str
    title: str
    filename: str
    version: str
    status: str
    fields: Mapping[str, str]

    @property
    def active(self) -> bool:
        return self.status.casefold() in {"ratified", "approved", "active"}


@dataclass(frozen=True, slots=True)
class ConstitutionalMemory:
    root: Path
    artifacts: tuple[FoundationArtifact, ...]
    registry_entries: tuple[RegistryEntry, ...]
    document_hashes: Mapping[str, str]
    registry_hash: str
    corpus_fingerprint: str
    memory_schema_version: str
    validation_timestamp: str
    source: str
    lexicon: Mapping[str, str]
    primary_object: str

    def artifact(self, document_id: str) -> FoundationArtifact:
        for item in self.artifacts:
            if item.artifact_id == document_id:
                return item
        raise KeyError(f"Constitutional artifact not found: {document_id}")

    def by_filename(self, filename: str) -> FoundationArtifact:
        for item in self.artifacts:
            if item.path.name == filename:
                return item
        raise KeyError(f"Constitutional artifact not found: {filename}")

    @property
    def constitution(self) -> FoundationArtifact:
        return self.artifact("RIP-000")

    @property
    def mission(self) -> FoundationArtifact:
        return self.artifact("RIP-001")

    @property
    def lexicon_artifact(self) -> FoundationArtifact:
        return self.artifact("RIP-002")

    @property
    def conceptual_model(self) -> FoundationArtifact:
        return self.artifact("RIP-003")

    @property
    def governance(self) -> FoundationArtifact:
        return self.artifact("RIP-004")

    @property
    def learning(self) -> FoundationArtifact:
        return self.artifact("RIP-005")

    def term(self, name: str) -> str:
        for term, definition in self.lexicon.items():
            if term.casefold() == name.casefold():
                return definition
        raise KeyError(f"Lexicon term not found: {name}")

    def status_lines(self) -> tuple[str, ...]:
        return tuple(f"{item.artifact_id}: Loaded - {item.title}" for item in self.artifacts)


Foundation = ConstitutionalMemory


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
