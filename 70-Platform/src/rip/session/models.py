from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class Participant:
    participant_id: str
    role: str


@dataclass(frozen=True, slots=True)
class CodeBlock:
    language: str | None
    content: str


@dataclass(frozen=True, slots=True)
class Link:
    text: str
    url: str


@dataclass(frozen=True, slots=True)
class ImageReference:
    alt_text: str
    url: str


@dataclass(frozen=True, slots=True)
class AttachmentReference:
    name: str
    url: str | None


@dataclass(frozen=True, slots=True)
class Message:
    source_message_id: str
    source_order: int
    participant_id: str
    role: str
    markdown: str
    searchable_text: str
    code_blocks: tuple[CodeBlock, ...] = ()
    links: tuple[Link, ...] = ()
    images: tuple[ImageReference, ...] = ()
    attachments: tuple[AttachmentReference, ...] = ()
    source_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SessionStatistics:
    message_count: int
    participant_count: int
    code_block_count: int
    link_count: int
    image_count: int
    attachment_count: int
    role_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    input_message_count: int
    output_message_count: int


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    source_format: str
    source_metadata: dict[str, object]
    participants: tuple[Participant, ...]
    messages: tuple[Message, ...]
    statistics: SessionStatistics
    validation: ValidationResult

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
