"""Authoritative RIP locations for permanent managed artifacts."""
from __future__ import annotations
from pathlib import Path

PRODUCTION_SESSION = "chatgpt-production-0001"
PRODUCTION_INTERPRETATION = "architectural-decisions-production-0001"

def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]

def managed_knowledge_root() -> Path:
    return repository_root() / "60-Reference" / "Knowledge"

def session_archive(name: str = PRODUCTION_SESSION) -> Path:
    return managed_knowledge_root() / "Session-Archives" / name

def interpretation_archive(name: str = PRODUCTION_INTERPRETATION) -> Path:
    return managed_knowledge_root() / "Interpretations" / name

def production_canonical_session() -> Path:
    return session_archive() / "canonical-session.json"

def production_candidate_knowledge() -> Path:
    return interpretation_archive() / "candidate-knowledge.json"
