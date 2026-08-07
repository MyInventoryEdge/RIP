"""Home page: platform readiness presentation over Foundation evidence."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..foundation.loader import load_foundation
from .work_queue import WorkItem, load_work_queue


@dataclass(frozen=True, slots=True)
class HomeOverview:
    health: str
    source: str
    documents: int
    fingerprint: str
    primary_object: str
    work_items: tuple[WorkItem, ...]


def refresh_home() -> HomeOverview:
    """Read existing Foundation evidence; no state or authority is changed."""
    foundation = load_foundation(Path(r"C:\RIP\00-Constitution"))
    return HomeOverview(
        health="Foundation validated", source=foundation.source,
        documents=len(foundation.artifacts), fingerprint=foundation.corpus_fingerprint,
        primary_object=foundation.primary_object, work_items=load_work_queue(provisioning_ready=_provisioning_ready(), include_constitutional=True),
    )


def _provisioning_ready() -> bool:
    try:
        from ..platform_provisioning import load_trust_authority_context
        load_trust_authority_context()
        return True
    except Exception:
        return False
