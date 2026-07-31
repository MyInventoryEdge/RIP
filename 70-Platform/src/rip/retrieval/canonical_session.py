"""Deterministic, lossless chunking for RIP canonical-session JSON artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import ArtifactDescriptor, ChunkCatalog, EvidenceChunk, MessageRange, VersionMetadata

UTF8_BYTES_PER_TOKEN = 3
DEFAULT_SOFT_TARGET_TOKENS = 24_000
DEFAULT_HARD_CEILING_TOKENS = 32_000


class OversizedLogicalUnitError(ValueError):
    """A complete message exceeds the governed hard ceiling and cannot be split."""


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"canonical session JSON contains unsupported constant {value!r}")


def _canonical_json(value: object) -> str:
    """Canonical JSON: UTF-8, sorted object keys, compact separators, no added newline."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CanonicalSessionChunker:
    """Chunks only between complete validated canonical-session message objects."""

    name = "canonical-session"
    versions = VersionMetadata("1.0", name, "1.0", "1.0", "1.0")

    def __init__(
        self,
        *,
        soft_target_tokens: int = DEFAULT_SOFT_TARGET_TOKENS,
        hard_ceiling_tokens: int = DEFAULT_HARD_CEILING_TOKENS,
    ) -> None:
        if soft_target_tokens < 0 or hard_ceiling_tokens <= 0 or soft_target_tokens > hard_ceiling_tokens:
            raise ValueError("chunk size policy requires 0 <= soft target <= hard ceiling")
        self.soft_target_tokens = soft_target_tokens
        self.hard_ceiling_tokens = hard_ceiling_tokens

    def can_chunk(self, descriptor: ArtifactDescriptor) -> bool:
        return descriptor.artifact_type == "canonical-session" and descriptor.media_type == "application/json"

    def describe(
        self,
        path: str | Path,
        *,
        repository_root: str | Path,
        source_observation_id: str | None,
    ) -> ArtifactDescriptor:
        """Create provenance from one existing repository artifact; no scanning occurs."""
        artifact_path = Path(path).resolve()
        root = Path(repository_root).resolve()
        try:
            relative_path = artifact_path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"canonical session artifact is outside repository root: {artifact_path}") from exc
        raw = artifact_path.read_bytes()
        return ArtifactDescriptor(
            repository_relative_path=relative_path,
            source_observation_id=source_observation_id,
            artifact_type="canonical-session",
            media_type="application/json",
            encoding="utf-8",
            byte_size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            estimated_token_count=(len(raw) + UTF8_BYTES_PER_TOKEN - 1) // UTF8_BYTES_PER_TOKEN,
            preferred_chunker=self.name,
            chunkable=True,
        )

    def chunk_file(
        self,
        path: str | Path,
        *,
        repository_root: str | Path,
        source_observation_id: str | None,
    ) -> ChunkCatalog:
        descriptor = self.describe(path, repository_root=repository_root, source_observation_id=source_observation_id)
        try:
            content = Path(path).read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"canonical session artifact is not valid UTF-8: {descriptor.repository_relative_path}") from exc
        return self.chunk(descriptor, content)

    def chunk(self, descriptor: ArtifactDescriptor, content: str) -> ChunkCatalog:
        """Return lossless chunks from canonical JSON text and an already-governed descriptor."""
        if not self.can_chunk(descriptor):
            raise ValueError(f"artifact is not a canonical-session JSON artifact: {descriptor.repository_relative_path}")
        if descriptor.encoding.lower() != "utf-8":
            raise ValueError(f"canonical session must declare UTF-8 encoding: {descriptor.repository_relative_path}")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != descriptor.sha256:
            raise ValueError(f"artifact SHA-256 does not match descriptor: {descriptor.repository_relative_path}")
        document = self._load_and_validate(content, descriptor.repository_relative_path)
        messages = document["messages"]
        assert isinstance(messages, list)
        chunks: list[EvidenceChunk] = []
        pending: list[dict[str, Any]] = []
        pending_start = 0

        for index, message in enumerate(messages):
            candidate = [*pending, message]
            candidate_tokens = self._estimate_tokens(_canonical_json(candidate))
            message_tokens = self._estimate_tokens(_canonical_json([message]))
            if message_tokens > self.hard_ceiling_tokens:
                raise OversizedLogicalUnitError(
                    f"canonical session {descriptor.repository_relative_path} message {index} "
                    f"({message['source_message_id']}) exceeds hard ceiling of {self.hard_ceiling_tokens} estimated tokens"
                )
            if pending and candidate_tokens > self.soft_target_tokens:
                chunks.append(self._build_chunk(descriptor, len(chunks), pending_start, pending))
                pending = [message]
                pending_start = index
            else:
                pending = candidate

        if pending:
            chunks.append(self._build_chunk(descriptor, len(chunks), pending_start, pending))
        return ChunkCatalog(descriptor, tuple(chunks), total_logical_units=len(messages), overlap_logical_units=0)

    def _build_chunk(
        self,
        descriptor: ArtifactDescriptor,
        chunk_index: int,
        start_index: int,
        messages: list[dict[str, Any]],
    ) -> EvidenceChunk:
        content = _canonical_json(messages)
        estimated_tokens = self._estimate_tokens(content)
        if estimated_tokens > self.hard_ceiling_tokens:
            raise OversizedLogicalUnitError(
                f"canonical session {descriptor.repository_relative_path} chunk {chunk_index} exceeds hard ceiling"
            )
        chunk_hash = _sha256(content)
        version_digest = _sha256(_canonical_json(asdict(self.versions)))
        chunk_id = f"rip-chunk:{version_digest}:{descriptor.sha256}:{chunk_index}:{chunk_hash}"
        return EvidenceChunk(
            repository_relative_path=descriptor.repository_relative_path,
            source_observation_id=descriptor.source_observation_id,
            artifact_type=descriptor.artifact_type,
            media_type=descriptor.media_type,
            encoding=descriptor.encoding,
            artifact_sha256=descriptor.sha256,
            chunk_sha256=chunk_hash,
            chunk_id=chunk_id,
            chunk_index=chunk_index,
            content=content,
            source_range=MessageRange(
                "message",
                start_index,
                start_index + len(messages) - 1,
                str(messages[0]["source_message_id"]),
                str(messages[-1]["source_message_id"]),
            ),
            versions=self.versions,
        )

    def _load_and_validate(self, content: str, artifact_path: str) -> dict[str, object]:
        try:
            document = json.loads(content, parse_constant=_reject_nonstandard_constant)
        except json.JSONDecodeError as exc:
            raise ValueError(f"canonical session is not valid JSON: {artifact_path}") from exc
        if not isinstance(document, dict) or not isinstance(document.get("messages"), list):
            raise ValueError(f"canonical session must contain a top-level messages array: {artifact_path}")
        if not isinstance(document.get("session_id"), str) or not document["session_id"]:
            raise ValueError(f"canonical session is missing a nonempty session_id: {artifact_path}")
        if not isinstance(document.get("source_format"), str) or not document["source_format"]:
            raise ValueError(f"canonical session is missing a nonempty source_format: {artifact_path}")
        validation = document.get("validation")
        if not isinstance(validation, dict) or validation.get("passed") is not True:
            raise ValueError(f"canonical session validation must be passed: {artifact_path}")
        ids: set[str] = set()
        for index, message in enumerate(document["messages"]):
            if not isinstance(message, dict):
                raise ValueError(f"canonical session message {index} must be an object: {artifact_path}")
            for field in ("source_message_id", "participant_id", "role", "markdown"):
                if not isinstance(message.get(field), str) or not message[field]:
                    raise ValueError(f"canonical session message {index} is missing nonempty {field}: {artifact_path}")
            if message.get("source_order") != index:
                raise ValueError(f"canonical session message {index} has noncontiguous source_order: {artifact_path}")
            message_id = message["source_message_id"]
            if message_id in ids:
                raise ValueError(f"canonical session has duplicate source_message_id {message_id}: {artifact_path}")
            ids.add(message_id)
        return document

    @staticmethod
    def _estimate_tokens(content: str) -> int:
        return (len(content.encode("utf-8")) + UTF8_BYTES_PER_TOKEN - 1) // UTF8_BYTES_PER_TOKEN


def reassemble_messages(catalog: ChunkCatalog) -> tuple[dict[str, Any], ...]:
    """Reconstruct the exact canonical message-object sequence from ordered chunks."""
    if catalog.descriptor.artifact_type != "canonical-session":
        raise ValueError("reassembly requires a canonical-session catalog")
    messages: list[dict[str, Any]] = []
    for expected_index, chunk in enumerate(catalog.chunks):
        if chunk.chunk_index != expected_index or not isinstance(chunk.source_range, MessageRange):
            raise ValueError("catalog violates canonical-session chunk ordering or message boundaries")
        if _sha256(chunk.content) != chunk.chunk_sha256:
            raise ValueError(f"chunk content hash does not match: {chunk.chunk_id}")
        try:
            parsed = json.loads(chunk.content, parse_constant=_reject_nonstandard_constant)
        except json.JSONDecodeError as exc:
            raise ValueError(f"chunk content is not valid canonical JSON: {chunk.chunk_id}") from exc
        if not isinstance(parsed, list) or len(parsed) != chunk.source_range.unit_count or not all(isinstance(item, dict) for item in parsed):
            raise ValueError(f"chunk content does not match its message range: {chunk.chunk_id}")
        if parsed[0].get("source_message_id") != chunk.source_range.start_message_id or parsed[-1].get("source_message_id") != chunk.source_range.end_message_id:
            raise ValueError(f"chunk message IDs do not match its message range: {chunk.chunk_id}")
        messages.extend(parsed)
    if len(messages) != catalog.total_logical_units:
        raise ValueError("catalog does not provide complete canonical-session coverage")
    if [message.get("source_order") for message in messages] != list(range(len(messages))):
        raise ValueError("reassembled messages do not preserve canonical source order")
    return tuple(messages)
