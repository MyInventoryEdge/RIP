from __future__ import annotations

import json
from typing import Any

from ..foundation.models import Foundation
from ..observation.models import ObservationSet

SYSTEM_INSTRUCTIONS = """You are a reasoning provider for the Repository Intelligence Platform (RIP).
Reason only from the supplied evidence package. Do not claim direct filesystem access.
Apply this evidence hierarchy: constitutional artifacts govern reasoning, authority boundaries, provenance, uncertainty handling, and interpretation. When primary_evidence.artifacts is nonempty, its artifact content is the primary factual source for the current task. Repository observations provide supporting filesystem metadata and provenance only.
When primary evidence is relevant to the current task, do not substitute repository observations for artifact content. When answering about a supplied artifact, answer from its content. Do not state that only metadata is available when primary evidence contains the requested artifact content. Every factual claim derived from primary evidence must identify the artifact by its repository-relative path and source observation ID.
Repository observations establish paths, existence, hashes, observation IDs, timestamps, byte sizes, and other filesystem-derived metadata. They do not override primary evidence regarding artifact contents. If observations and primary evidence appear inconsistent, explain the inconsistency and prefer primary evidence for claims about artifact contents.
Distinguish deterministic observation from interpretation. Every factual repository claim supported by an observation must cite one or more observation IDs using the exact form [obs-...].
When constitutional text supports a claim, name the governing artifact (for example RIP-000), but do not invent quotations.
State uncertainty and evidence gaps explicitly.
Do not present interpretation as organizational authority, approval, policy, or decision.
End with this exact boundary line:
Boundary: AI interpretation grounded in supplied evidence; not organizational authority.
"""


def build_evidence_package(
    foundation: Foundation,
    observations: ObservationSet,
    question: str,
    primary_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the complete, serializable evidence package sent to a provider."""
    return {
        "schema": "rip.reasoning.evidence.v1",
        "question": question,
        "foundation": {
            "root": str(foundation.root),
            "primary_object": foundation.primary_object,
            "lexicon_term_count": len(foundation.lexicon),
            "artifacts": [
                {
                    "artifact_id": artifact.artifact_id,
                    "title": artifact.title,
                    "metadata": dict(artifact.metadata),
                    "markdown": artifact.raw_markdown,
                }
                for artifact in foundation.artifacts
            ],
        },
        "observation_set": observations.to_dict(),
        "primary_evidence": {"artifacts": primary_evidence or []},
        "constraints": {
            "observation_ids_are_required_for_repository_claims": True,
            "interpretation_is_not_authority": True,
            "filesystem_access": "none; evidence package only",
        },
    }


def serialize_evidence_package(package: dict[str, Any]) -> str:
    artifacts = package.get("primary_evidence", {}).get("artifacts", [])
    if artifacts and any(not item.get("content") for item in artifacts):
        raise ValueError("Primary-evidence integration error: loaded artifact content is absent from the provider package.")
    return json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_user_input(evidence_json: str) -> str:
    return "Analyze the following RIP evidence package and answer its question.\n\n" + evidence_json
