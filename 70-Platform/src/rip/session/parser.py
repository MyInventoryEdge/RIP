from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .models import AttachmentReference, CodeBlock, ImageReference, Link, Message, Participant, Session, SessionStatistics, ValidationResult

CODE_BLOCK_PATTERN = re.compile(r"(?ms)^```(?P<language>[^\n`]*)\n(?P<content>.*?)^```[ \t]*$")
IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)")
LINK_PATTERN = re.compile(r"(?<!!)\[(?P<text>[^\]]+)\]\((?P<url>[^)]+)\)")
ATTACHMENT_SUFFIXES = {".csv", ".doc", ".docx", ".json", ".md", ".pdf", ".pptx", ".txt", ".xls", ".xlsx", ".zip"}


def load_chatgpt_conversation(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Input is not valid JSON: {path}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("messages"), list):
        raise ValueError("Input must contain a top-level messages array.")
    return document


def parse_session(input_path: Path, output_directory: Path) -> Session:
    source = load_chatgpt_conversation(input_path)
    session = normalize_chatgpt_export(source)
    if not session.validation.passed:
        raise ValueError("Session validation failed: " + "; ".join(session.validation.errors))
    write_session_outputs(session, input_path, output_directory)
    return session


def normalize_chatgpt_export(source: dict[str, object]) -> Session:
    raw_messages = source["messages"]
    if not isinstance(raw_messages, list):
        raise ValueError("Input messages must be an array.")
    warnings: list[str] = []
    exported_indexes = [item.get("index") for item in raw_messages if isinstance(item, dict)]
    indexes_are_unique = len(exported_indexes) == len(raw_messages) and len(exported_indexes) == len(set(map(str, exported_indexes)))
    if not any(isinstance(item, dict) and item.get("id") is not None for item in raw_messages):
        warnings.append("The source export has no upstream ChatGPT turn IDs.")
    if not indexes_are_unique:
        warnings.append("The exported index values are not unique; canonical source message identifiers are deterministic source-order values, while raw indexes are retained in source metadata.")
    participants: dict[str, Participant] = {}
    messages: list[Message] = []
    ids: set[str] = set()
    for order, raw_message in enumerate(raw_messages):
        if not isinstance(raw_message, dict):
            raise ValueError(f"Message {order} must be an object.")
        role = raw_message.get("role")
        markdown = raw_message.get("markdown")
        if not isinstance(role, str) or not isinstance(markdown, str):
            raise ValueError(f"Message {order} must contain string role and markdown fields.")
        source_id = raw_message.get("id")
        if source_id is None and indexes_are_unique:
            source_id = raw_message.get("index")
        if source_id is None:
            source_id = f"source-order:{order}"
        source_id = str(source_id)
        if source_id in ids:
            raise ValueError(f"Duplicate source message identifier: {source_id}")
        ids.add(source_id)
        participant_id = f"role:{role}"
        participants.setdefault(participant_id, Participant(participant_id=participant_id, role=role))
        known_fields = {"id", "index", "role", "markdown"}
        metadata = {key: value for key, value in raw_message.items() if key not in known_fields}
        if "index" in raw_message:
            metadata["exported_index"] = raw_message["index"]
        messages.append(
            Message(
                source_message_id=source_id,
                source_order=order,
                participant_id=participant_id,
                role=role,
                markdown=markdown,
                searchable_text=plain_text(markdown),
                code_blocks=extract_code_blocks(markdown),
                links=extract_links(markdown),
                images=extract_images(markdown),
                attachments=extract_attachments(markdown),
                source_metadata=metadata,
            )
        )
    source_metadata = {key: value for key, value in source.items() if key != "messages"}
    statistics = build_statistics(messages, participants)
    validation = validate_messages(raw_messages, messages, warnings)
    session_seed = json.dumps(source_metadata, sort_keys=True, ensure_ascii=False)
    session_id = "chatgpt-export-" + hashlib.sha256(session_seed.encode("utf-8")).hexdigest()[:16]
    return Session(session_id, "chatgpt-conversation-json", source_metadata, tuple(participants.values()), tuple(messages), statistics, validation)


def extract_code_blocks(markdown: str) -> tuple[CodeBlock, ...]:
    return tuple(CodeBlock(match.group("language").strip() or None, match.group("content")) for match in CODE_BLOCK_PATTERN.finditer(markdown))


def extract_images(markdown: str) -> tuple[ImageReference, ...]:
    return tuple(ImageReference(match.group("alt"), match.group("url")) for match in IMAGE_PATTERN.finditer(markdown))


def extract_links(markdown: str) -> tuple[Link, ...]:
    return tuple(Link(match.group("text"), match.group("url")) for match in LINK_PATTERN.finditer(markdown))


def extract_attachments(markdown: str) -> tuple[AttachmentReference, ...]:
    attachments: list[AttachmentReference] = []
    for link in extract_links(markdown):
        suffix = Path(link.url.split("?")[0]).suffix.lower()
        if suffix in ATTACHMENT_SUFFIXES or link.url.startswith(("attachment:", "sandbox:")):
            attachments.append(AttachmentReference(link.text, link.url))
    return tuple(attachments)


def plain_text(markdown: str) -> str:
    text = CODE_BLOCK_PATTERN.sub(lambda match: "\n" + match.group("content") + "\n", markdown)
    text = IMAGE_PATTERN.sub(lambda match: match.group("alt"), text)
    text = LINK_PATTERN.sub(lambda match: match.group("text"), text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"[`*_~]", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_statistics(messages: list[Message], participants: dict[str, Participant]) -> SessionStatistics:
    return SessionStatistics(
        message_count=len(messages), participant_count=len(participants),
        code_block_count=sum(len(message.code_blocks) for message in messages),
        link_count=sum(len(message.links) for message in messages),
        image_count=sum(len(message.images) for message in messages),
        attachment_count=sum(len(message.attachments) for message in messages),
        role_counts=dict(sorted(Counter(message.role for message in messages).items())),
    )


def validate_messages(raw_messages: list[object], messages: list[Message], warnings: list[str]) -> ValidationResult:
    errors: list[str] = []
    if len(raw_messages) != len(messages): errors.append("Input and normalized message counts differ.")
    if any(not message.markdown for message in messages): errors.append("A normalized message has empty Markdown.")
    ids = [message.source_message_id for message in messages]
    if len(ids) != len(set(ids)): errors.append("Normalized source message identifiers are not unique.")
    if [message.source_order for message in messages] != list(range(len(messages))): errors.append("Normalized source order is not contiguous.")
    return ValidationResult(not errors, tuple(errors), tuple(warnings), len(raw_messages), len(messages))


def write_session_outputs(session: Session, input_path: Path, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    canonical_path = output_directory / "canonical-session.json"
    markdown_path = output_directory / "canonical-session.md"
    manifest_path = output_directory / "parser-manifest.json"
    canonical_path.write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_session_markdown(session), encoding="utf-8")
    manifest = {
        "input": str(input_path), "source_format": session.source_format,
        "outputs": [canonical_path.name, markdown_path.name],
        "validation": asdict(session.validation), "statistics": asdict(session.statistics),
        "unrepresented_source_fields": [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_session_markdown(session: Session) -> str:
    lines = ["# Canonical Session", "", f"Source format: {session.source_format}", f"Messages: {session.statistics.message_count}", f"Validation: {'PASS' if session.validation.passed else 'FAIL'}", ""]
    for message in session.messages:
        lines.extend((f"## {message.role.title()} — source message {message.source_message_id}", "", message.markdown, ""))
    return "\n".join(lines)
