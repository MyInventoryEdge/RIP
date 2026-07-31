from __future__ import annotations

import unittest

from rip.retrieval.models import ArtifactDescriptor
from rip.retrieval.registry import ChunkerRegistry

ARTIFACT_HASH = "a" * 64


class TestChunker:
    name = "test"

    def can_chunk(self, descriptor: ArtifactDescriptor) -> bool:
        return descriptor.artifact_type == "test"

    def chunk(self, descriptor: ArtifactDescriptor, content: str):
        raise AssertionError("Phase 1 must not invoke chunking")


def descriptor(preferred_chunker: str | None = "test", artifact_type: str = "test") -> ArtifactDescriptor:
    return ArtifactDescriptor("evidence/input.txt", "obs-1", artifact_type, "text/plain", "utf-8", 0, ARTIFACT_HASH, 0, preferred_chunker, True)


class ChunkerRegistryTests(unittest.TestCase):
    def test_explicit_registration_and_descriptor_based_resolution(self) -> None:
        registry = ChunkerRegistry()
        registry.register(TestChunker())
        self.assertEqual(registry.resolve(descriptor()).name, "test")

    def test_rejects_duplicate_unknown_and_incompatible_chunkers(self) -> None:
        registry = ChunkerRegistry()
        registry.register(TestChunker())
        with self.assertRaises(ValueError):
            registry.register(TestChunker())
        with self.assertRaises(LookupError):
            registry.resolve(descriptor("unknown"))
        with self.assertRaises(LookupError):
            registry.resolve(descriptor(None))
        with self.assertRaises(LookupError):
            registry.resolve(descriptor("test", "other"))

    def test_resolution_does_not_invoke_chunking_or_reasoning(self) -> None:
        registry = ChunkerRegistry()
        registry.register(TestChunker())
        registry.resolve(descriptor())
