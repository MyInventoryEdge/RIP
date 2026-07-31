from __future__ import annotations
from .interfaces import ArtifactChunker
from .models import ArtifactDescriptor

class ChunkerRegistry:
    def __init__(self) -> None: self._chunkers: dict[str, ArtifactChunker] = {}
    def register(self, chunker: ArtifactChunker) -> None:
        if not chunker.name or chunker.name in self._chunkers: raise ValueError(f"Duplicate chunker registration: {chunker.name}")
        self._chunkers[chunker.name] = chunker
    def resolve(self, descriptor: ArtifactDescriptor) -> ArtifactChunker:
        if not descriptor.preferred_chunker: raise LookupError("Artifact descriptor has no preferred chunker")
        try: chunker=self._chunkers[descriptor.preferred_chunker]
        except KeyError as exc: raise LookupError(f"Unknown chunker: {descriptor.preferred_chunker}") from exc
        if not chunker.can_chunk(descriptor): raise LookupError(f"Chunker cannot handle descriptor: {chunker.name}")
        return chunker
