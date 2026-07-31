from __future__ import annotations
import hashlib, mimetypes
from pathlib import Path
from typing import Any

from ..retrieval import ArtifactDescriptor, CanonicalSessionChunker, ChunkCatalog, EvidenceChunk

def load_primary_evidence(root: Path, observations, paths: list[str]) -> list[dict[str, Any]]:
    observed={item.relative_path:item for item in observations.observations}
    loaded=[]
    for requested in paths:
        relative=Path(requested)
        if relative.is_absolute() or '..' in relative.parts: raise ValueError(f"Primary evidence path is not repository-relative: {requested}")
        target=(root/relative).resolve()
        if root not in target.parents or not target.is_file(): raise ValueError(f"Primary evidence is not a repository file: {requested}")
        raw=target.read_bytes()
        try: content=raw.decode('utf-8')
        except UnicodeDecodeError as exc: raise ValueError(f"Primary evidence is not UTF-8: {requested}") from exc
        key=target.relative_to(root).as_posix(); observation=observed.get(key)
        digest=hashlib.sha256(raw).hexdigest()
        if observation and observation.metadata.get('sha256') and observation.metadata['sha256'] != digest: raise ValueError(f"Primary evidence changed after observation: {key}")
        loaded.append({'repository_relative_path':key,'source_observation_id':observation.observation_id if observation else None,'media_type':mimetypes.guess_type(target.name)[0] or 'application/octet-stream','encoding':'utf-8','byte_size':len(raw),'content_hash':digest,'load_status':'loaded','truncated':False,'chunked':False,'content':content})
    return loaded


def canonical_session_catalog(
    artifact: dict[str, Any],
    *,
    catalog: ChunkCatalog | None = None,
) -> ChunkCatalog:
    """Return an existing matching catalog or construct one for validated canonical-session evidence."""
    if catalog is not None:
        if (
            catalog.descriptor.repository_relative_path != artifact["repository_relative_path"]
            or catalog.descriptor.sha256 != artifact["content_hash"]
        ):
            raise ValueError("Existing ChunkCatalog does not match primary evidence identity.")
        return catalog

    if artifact["media_type"] != "application/json":
        raise LookupError("No compatible governed chunker is available for this primary evidence artifact.")
    descriptor = ArtifactDescriptor(
        repository_relative_path=artifact["repository_relative_path"],
        source_observation_id=artifact["source_observation_id"],
        artifact_type="canonical-session",
        media_type=artifact["media_type"],
        encoding=artifact["encoding"],
        byte_size=artifact["byte_size"],
        sha256=artifact["content_hash"],
        estimated_token_count=(artifact["byte_size"] + 2) // 3,
        preferred_chunker=CanonicalSessionChunker.name,
        chunkable=True,
    )
    return CanonicalSessionChunker().chunk(descriptor, artifact["content"])


def materialize_retrieved_primary_evidence(
    artifact: dict[str, Any], selected_chunks: tuple[EvidenceChunk, ...]
) -> dict[str, Any]:
    """Represent ordered, unchanged chunks as evidence from one existing artifact."""
    if not selected_chunks:
        raise ValueError("Retrieved primary evidence must contain at least one selected chunk.")
    if any(
        chunk.repository_relative_path != artifact["repository_relative_path"]
        or chunk.artifact_sha256 != artifact["content_hash"]
        for chunk in selected_chunks
    ):
        raise ValueError("Retrieved chunks do not match primary evidence identity.")
    return {
        **artifact,
        "chunked": True,
        "content": "\n\n".join(chunk.content for chunk in selected_chunks),
    }
