from __future__ import annotations
from typing import Literal, Protocol
from .models import ArtifactDescriptor, ChunkCatalog, RetrievalResult

class ArtifactChunker(Protocol):
    name: str
    def can_chunk(self, descriptor: ArtifactDescriptor) -> bool: ...
    def chunk(self, descriptor: ArtifactDescriptor, content: str) -> ChunkCatalog: ...

class RetrievalStrategy(Protocol):
    name: str
    def retrieve(self, query: str, catalog: ChunkCatalog, *, token_budget: int, max_selected_chunks: int | None = None, surrounding_context: Literal["none"] = "none") -> RetrievalResult: ...

class EvidenceRetrievalEngine(Protocol):
    def retrieve(self, query: str, catalog: ChunkCatalog, *, token_budget: int, max_selected_chunks: int | None = None, surrounding_context: Literal["none"] = "none") -> RetrievalResult: ...
