from __future__ import annotations
from typing import Protocol
from .models import ArtifactDescriptor, ChunkCatalog, RetrievalResult

class ArtifactChunker(Protocol):
    name: str
    def can_chunk(self, descriptor: ArtifactDescriptor) -> bool: ...
    def chunk(self, descriptor: ArtifactDescriptor, content: str) -> ChunkCatalog: ...

class RetrievalStrategy(Protocol):
    name: str

class EvidenceRetrievalEngine(Protocol):
    def retrieve(self, *args, **kwargs) -> RetrievalResult: ...
