"""Read-only, deterministic customer-facing classification review data."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from .models import fingerprint
from .service import resolve_onboarding_run_directory, resolve_organization_workspace

@dataclass(frozen=True, slots=True)
class ClassificationReview:
    organization_id: str
    onboarding_run_id: str
    state: str
    preserved_files: tuple[str, ...]
    requests: tuple[dict[str, object], ...]
    attention_events: tuple[dict[str, object], ...]
    readiness: str
    complete_source_fingerprint: str | None
    organizational_evidence_fingerprint: str | None
    diagnostics: dict[str, object]
    fingerprint: str

def load_classification_review(workspace_root: str | Path, organization_id: str, run_id: str) -> ClassificationReview:
    """Load retained review data through the authoritative organization/run resolver."""
    root = resolve_organization_workspace(workspace_root, organization_id)
    run = resolve_onboarding_run_directory(workspace_root, organization_id, run_id)
    context = _read(run / "context.json"); state = _read(run / "state.json").get("state", "unknown")
    final = _read(run / "final-source-manifest.json") if (run / "final-source-manifest.json").is_file() else {}
    recovery = _read(run / "classification-recovery.json") if (run / "classification-recovery.json").is_file() else {}
    evaluation = _read(run / "classification-evaluation.json") if (run / "classification-evaluation.json").is_file() else {}
    request_dir = run / "classifications" / "requests"
    requests = tuple(_read(path).get("contract", {}) for path in sorted(request_dir.glob("*.json"))) if request_dir.is_dir() else ()
    attention = tuple(item for item in _read(root / "attention-events.json") if item.get("onboarding_run_id") == run_id) if (root / "attention-events.json").is_file() else ()
    preserved = tuple(name for name in ("initial-source-manifest.json", "final-source-manifest.json", "integrity-difference.json", "observation.json", "stages.json", "preserved-interrupted-run.json") if (run / name).is_file())
    diagnostics = {"manifest": final, "integrity_difference": _read(run / "integrity-difference.json") if (run / "integrity-difference.json").is_file() else {}, "evaluation_summary": evaluation.get("summary", {}), "recovery": recovery, "preservation": _read(run / "preserved-interrupted-run.json") if (run / "preserved-interrupted-run.json").is_file() else {}, "trust_action": _read(run / "trust-action.json") if (run / "trust-action.json").is_file() else {}, "trust_scope": _read(run / "trust-scope.json") if (run / "trust-scope.json").is_file() else {}, "mutation_reasoning": _read(run / "mutation-reasoning.json") if (run / "mutation-reasoning.json").is_file() else {}}
    payload = {"organization_id": context.get("organization_id", ""), "onboarding_run_id": run_id, "state": state, "preserved_files": preserved, "requests": requests, "attention_events": attention, "readiness": recovery.get("readiness", "not-evaluated"), "complete_source_fingerprint": evaluation.get("complete_source_fingerprint") or final.get("manifest_fingerprint"), "organizational_evidence_fingerprint": evaluation.get("organizational_evidence_fingerprint"), "diagnostics": diagnostics}
    return ClassificationReview(**payload, fingerprint=fingerprint(payload))

def format_classification_review(review: ClassificationReview, *, diagnostics: bool = False) -> str:
    if review.state == "paused-affected-scope":
        reasoning = review.diagnostics.get("mutation_reasoning", {}).get("interpretation", {})
        scope = review.diagnostics.get("trust_scope", {}).get("affected_scope", ())
        action = review.diagnostics.get("trust_action", {}).get("action", {}).get("action", "governed review")
        lines = ["RIP preserved this onboarding run and paused only the affected evidence scope.", f"What RIP observed: {', '.join(scope) or 'a retained source difference'}.", f"What RIP concluded: {reasoning.get('explanation', 'The evidence needs governed interpretation.')}", "What remains trusted: all retained evidence outside the stated affected scope.", f"Selected trust action: {action}.", "Decision required: review the affected scope only; archival capture is not required.", "What happens next: RIP will replay the persisted trust decision and verify only its declared scope. You may safely close and return later."]
        if diagnostics: lines.append(json.dumps(review.diagnostics, ensure_ascii=False, sort_keys=True, indent=2))
        return "\n".join(lines)
    lines = ["Onboarding paused safely. Completed work was preserved.", "Classification changes interpretation, never observation.", "No customer source was modified.", f"Run: {review.onboarding_run_id}", f"State: {review.state}", f"Readiness: {review.readiness}", f"Complete Source Fingerprint: {review.complete_source_fingerprint or 'not available'}", f"Organizational Evidence Fingerprint: {review.organizational_evidence_fingerprint or 'not available'}", "Preserved: " + (", ".join(review.preserved_files) or "none"), f"Classification requests: {len(review.requests)}; attention events: {len(review.attention_events)}"]
    for item in review.requests:
        lines.append(f"Request: {item.get('target')} ({item.get('scope')}); proposed {item.get('proposed_evidence_class')} / {item.get('proposed_integrity_treatment')}; authority required: {item.get('authority_claim')}; fingerprint: {item.get('fingerprint')}")
    if diagnostics:
        lines.append(json.dumps(review.diagnostics, ensure_ascii=False, sort_keys=True, indent=2))
    return "\n".join(lines)

def _read(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))
