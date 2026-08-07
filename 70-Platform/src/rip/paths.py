"""The sole authority for RIP-owned storage and managed repository artifacts.

Customer source locations are never resolved here.  Production-owned runtime
state is rooted at ``C:\\RIP``; callers may provide an explicit root only for
isolated tests or a governed migration operation.
"""
from __future__ import annotations
from pathlib import Path

PRODUCTION_SESSION = "chatgpt-production-0001"
PRODUCTION_INTERPRETATION = "architectural-decisions-production-0001"

def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def storage_root(root: str | Path | None = None) -> Path:
    """Resolve the governed RIP storage root, defaulting to ``C:\\RIP``."""
    # Environment state is never authority.  An explicit root exists solely
    # for isolated tests and governed migration planning.
    return Path(root if root is not None else r"C:\RIP").expanduser().resolve()


def storage_directory(name: str, *, root: str | Path | None = None) -> Path:
    """Return one approved top-level area; reject path construction escapes."""
    approved = frozenset({"Workspace", "Runs", "Evidence", "Artifacts", "Diagnostics", "Cache", "Snapshots", "Logs", "Configuration", "State"})
    if name not in approved:
        raise ValueError(f"Unknown RIP storage area: {name}")
    return storage_root(root) / name


def organization_workspace(organization_id: str, *, root: str | Path | None = None) -> Path:
    """Return the authoritative workspace for one validated organization id."""
    if not organization_id or Path(organization_id).name != organization_id or organization_id in {".", ".."}:
        raise ValueError("organization id is not a safe storage name")
    return storage_directory("Workspace", root=root) / organization_id


def onboarding_run_directory(workspace: str | Path, run_id: str) -> Path:
    """Return a run directory through the storage authority, never by callers."""
    if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError("onboarding run id is not a safe storage name")
    # The legacy on-disk segment remains encapsulated during governed migration;
    # no consumer may construct it directly.
    return Path(workspace).resolve() / "onboarding-runs" / run_id


def workspace_log_path(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / "audit" / "audit.json"


def constitutional_memory_path(*, root: str | Path | None = None) -> Path:
    return storage_directory("State", root=root) / "constitutional-memory.json"


def voice_configuration_path(*, root: str | Path | None = None) -> Path:
    return storage_directory("Configuration", root=root) / "voice.json"


def recovery_snapshot_directory(workspace: str | Path, organization_id: str) -> Path:
    """Return the workspace-local archival area without caller path joins."""
    if not organization_id or Path(organization_id).name != organization_id:
        raise ValueError("organization id is not a safe storage name")
    return Path(workspace).resolve().parent / "recovery-snapshots" / organization_id

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
