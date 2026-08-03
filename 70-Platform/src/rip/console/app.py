from __future__ import annotations

import os
import json
import queue
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..onboarding import (
    GuidedAnswerDisposition,
    GuidedUnderstandingState,
    OrganizationalUnderstandingProposal,
    ObservationRun,
    ReasoningCapability,
    UnderstandingState,
    begin_guided_understanding,
    create_organization_workspace,
    format_classification_review,
    generate_understanding_proposal,
    review_understanding_proposal,
    observe_organization,
    recommend_reasoning_capability,
    record_guided_answer,
    restart_onboarding_run,
    load_classification_review,
    validate_reasoning_capability,
    ClassificationRequest,
    ClassificationReadiness,
    EvidenceClass,
    IntegrityTreatment,
    accept_decision,
    integrate_persisted_classifications,
    load_persisted_classification_request,
    preview_scope,
    resume_governed_onboarding,
)
from ..observation import find_repository_root
from ..reasoning import ReasoningResult, ask_repository
from ..reasoning.service import DiscoveryDecision
from ..voice import VoiceManager, VoiceState


@dataclass(frozen=True, slots=True)
class ConsoleResponse:
    answer: str
    details: str


@dataclass(frozen=True, slots=True)
class ConsoleDecisionResult:
    """Console orchestration result; interpretation remains in promoted services."""

    request: ClassificationRequest
    decision_id: str
    classification_id: str
    readiness: ClassificationReadiness
    blocking_conditions: tuple[str, ...]


def submit_console_classification_decision(
    *, workspace: str, onboarding_run_id: str, request_id: str,
    evidence_class: EvidenceClass, integrity_treatment: IntegrityTreatment,
    reviewer_identity: str, reviewer_role: str, authority_claim: str, rationale: str,
) -> ConsoleDecisionResult:
    """Invoke the promoted acceptance and integration services for one request."""
    root = Path(workspace)
    request = load_persisted_classification_request(str(root), onboarding_run_id, request_id)
    manifest_path = root / "onboarding-runs" / onboarding_run_id / "final-source-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("retained manifest is unavailable for classification decision") from exc
    if not isinstance(manifest, dict):
        raise ValueError("retained manifest is invalid for classification decision")
    preview = preview_scope(manifest, target=request.target, scope=request.scope)
    decision, record = accept_decision(
        workspace=str(root), manifest=manifest, request=request, preview=preview,
        evidence_class=evidence_class, integrity_treatment=integrity_treatment,
        reviewer_identity=reviewer_identity, reviewer_role=reviewer_role,
        authority_claim=authority_claim, rationale=rationale,
    )
    integration = integrate_persisted_classifications(
        workspace=root, onboarding_run_id=onboarding_run_id,
    )
    conditions = tuple(
        item for item in (
            "Unresolved classification requests remain." if integration.unresolved_request_ids else "",
            "Effective classifications conflict." if integration.readiness is ClassificationReadiness.BLOCKED_BY_CONFLICT else "",
            "Policy is stale for the retained manifest." if integration.readiness is ClassificationReadiness.STALE_POLICY else "",
            "Retained source binding is stale." if integration.readiness is ClassificationReadiness.STALE_SOURCE else "",
        ) if item
    )
    return ConsoleDecisionResult(
        request=request, decision_id=decision.decision_id,
        classification_id=record.classification_id, readiness=integration.readiness,
        blocking_conditions=conditions,
    )


def format_classification_readiness(result: ConsoleDecisionResult) -> str:
    lines = [
        f"Decision accepted: {result.decision_id}",
        f"Classification recorded: {result.classification_id}",
        f"Readiness: {result.readiness.value}",
    ]
    if result.blocking_conditions:
        lines.append("Blocking conditions:")
        lines.extend(f"- {item}" for item in result.blocking_conditions)
    else:
        lines.append("No blocking condition was reported by the readiness service.")
    lines.append("No customer source was modified. Onboarding was not resumed.")
    return "\n".join(lines)


class ClassificationReviewWindow(tk.Toplevel):
    """Read-only CZ-EC-4A presentation of retained classification artifacts."""
    def __init__(self, parent: tk.Tk, workspace: str, run_id: str) -> None:
        super().__init__(parent); self.title("RIP Classification Review"); self.geometry("900x680")
        review = load_classification_review(workspace, run_id)
        ttk.Label(self, text="Onboarding paused safely. Completed work was preserved.", font=("Segoe UI", 11, "bold"), padding=10).pack(anchor="w")
        ttk.Label(self, text="RIP cannot decide an artifact's organizational role without authorized human judgment. Classification changes interpretation, never observation. No customer source was modified.", wraplength=850, padding=(10, 0, 10, 8)).pack(anchor="w")
        pane = ttk.PanedWindow(self, orient="horizontal"); pane.pack(fill="both", expand=True, padx=10, pady=6)
        left = ttk.LabelFrame(pane, text="Classification Requests", padding=6); right = ttk.LabelFrame(pane, text="Review and Diagnostics", padding=6); pane.add(left, weight=1); pane.add(right, weight=3)
        requests = tk.Listbox(left); requests.pack(fill="both", expand=True)
        detail = tk.Text(right, wrap="word", state="normal"); detail.pack(fill="both", expand=True)
        detail.insert("1.0", format_classification_review(review))
        for item in review.requests: requests.insert(tk.END, str(item.get("target", "unknown artifact")))
        def select(_: object) -> None:
            if requests.curselection():
                item = review.requests[requests.curselection()[0]]; detail.delete("1.0", "end"); detail.insert("1.0", format_classification_review(review) + "\n\nSelected request:\n" + str(item))
        requests.bind("<<ListboxSelect>>", select)
        controls = ttk.Frame(self, padding=6); controls.pack(fill="x")
        ttk.Button(controls, text="Show Complete Diagnostics", command=lambda: (detail.delete("1.0", "end"), detail.insert("1.0", format_classification_review(review, diagnostics=True)))).pack(side="left")
        def enter_decision() -> None:
            if not requests.curselection():
                messagebox.showerror("Classification Decision", "Select a persisted classification request first.", parent=self)
                return
            item = review.requests[requests.curselection()[0]]
            request_id = item.get("request_id")
            if not isinstance(request_id, str):
                messagebox.showerror("Classification Decision", "The selected request has no valid identity.", parent=self)
                return
            ClassificationDecisionWindow(self, workspace, run_id, request_id, on_complete=lambda message: detail.insert("end", "\n\n" + message))
        ttk.Button(controls, text="Enter Governed Decision", command=enter_decision).pack(side="right")
        def resume() -> None:
            if not messagebox.askyesno("Fresh source verification", "Verify the current source against the retained manifest and continue only if readiness is READY?", parent=self):
                return
            try:
                result = resume_governed_onboarding(workspace=workspace, onboarding_run_id=run_id)
                text = f"Readiness: {result.readiness.value}\n{result.message}"
                detail.insert("end", "\n\n" + text)
                messagebox.showinfo("Safe Resume", text, parent=self)
            except Exception as exc:
                messagebox.showerror("Safe Resume", str(exc), parent=self)
        ttk.Button(controls, text="Verify Source and Resume", command=resume).pack(side="right", padx=(0, 8))


class ClassificationDecisionWindow(tk.Toplevel):
    """Thin console control surface over promoted decision and readiness services."""

    def __init__(self, parent: tk.Toplevel, workspace: str, run_id: str, request_id: str, on_complete) -> None:
        super().__init__(parent); self.title("RIP Governed Classification Decision"); self.geometry("760x600"); self.transient(parent)
        self._workspace, self._run_id, self._request_id, self._on_complete = workspace, run_id, request_id, on_complete
        request = load_persisted_classification_request(workspace, run_id, request_id)
        manifest = json.loads((Path(workspace) / "onboarding-runs" / run_id / "final-source-manifest.json").read_text(encoding="utf-8"))
        preview = preview_scope(manifest, target=request.target, scope=request.scope)
        self._evidence_class = tk.StringVar(value=request.proposed_evidence_class.value)
        self._integrity = tk.StringVar(value=request.proposed_integrity_treatment.value)
        self._identity = tk.StringVar(); self._role = tk.StringVar(); self._authority = tk.StringVar()
        self._build(request, preview)

    def _build(self, request: ClassificationRequest, preview) -> None:
        frame = ttk.Frame(self, padding=12); frame.pack(fill="both", expand=True); frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Immutable Request and Scope Preview", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        request_text = (
            f"Request: {request.request_id}\nTarget: {request.target}\nScope: {request.scope.value}\n"
            f"Proposed treatment: {request.proposed_evidence_class.value} / {request.proposed_integrity_treatment.value}\n"
            f"Rationale: {request.rationale}\nSource manifest: {request.source_manifest_fingerprint}\n\n"
            f"Exact-path or broader scope preview: {preview.total_matches} retained entries\n"
            f"Kinds: {', '.join(f'{kind}: {count}' for kind, count in preview.counts_by_kind)}\n"
            f"Examples: {', '.join(preview.example_paths[:10])}\n\n"
            "Continuation effects: this writes immutable decision records and displays readiness only. It does not resume onboarding, verify customer sources, or change lifecycle state."
        )
        details = tk.Text(frame, height=13, wrap="word"); details.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 10)); details.insert("1.0", request_text); details.configure(state="disabled")
        self._field(frame, "Evidence class", self._evidence_class, 2, tuple(item.value for item in EvidenceClass), readonly=True)
        self._field(frame, "Integrity treatment", self._integrity, 3, tuple(item.value for item in IntegrityTreatment), readonly=True)
        self._field(frame, "Reviewer identity", self._identity, 4)
        self._field(frame, "Reviewer role", self._role, 5)
        self._field(frame, "Authority claim", self._authority, 6)
        ttk.Label(frame, text="Rationale").grid(row=7, column=0, sticky="nw", pady=3)
        self._rationale = tk.Text(frame, height=4, wrap="word"); self._rationale.grid(row=7, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text="Confirm and Submit Governed Decision", command=self._submit).grid(row=8, column=1, sticky="e", pady=(12, 0))

    @staticmethod
    def _field(parent, label: str, variable: tk.StringVar, row: int, values: tuple[str, ...] | None = None, readonly: bool = False) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        if values:
            ttk.Combobox(parent, textvariable=variable, values=values, state="readonly" if readonly else "normal").grid(row=row, column=1, sticky="ew", pady=3)
        else:
            ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=3)

    def _submit(self) -> None:
        if not messagebox.askyesno("Confirm governed decision", "Submit this immutable classification decision? This cannot resume onboarding.", parent=self):
            return
        try:
            result = submit_console_classification_decision(
                workspace=self._workspace, onboarding_run_id=self._run_id, request_id=self._request_id,
                evidence_class=EvidenceClass(self._evidence_class.get()), integrity_treatment=IntegrityTreatment(self._integrity.get()),
                reviewer_identity=self._identity.get(), reviewer_role=self._role.get(), authority_claim=self._authority.get(),
                rationale=self._rationale.get("1.0", "end").strip(),
            )
        except Exception as exc:
            messagebox.showerror("Classification Decision", str(exc), parent=self); return
        message = format_classification_readiness(result)
        self._on_complete(message)
        messagebox.showinfo("Classification Decision", message, parent=self)
        self.destroy()


def repository_relative_evidence(path: str | Path, root: str | Path | None = None) -> str:
    repository = find_repository_root(root)
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file() or repository not in resolved.parents:
        raise ValueError("Primary evidence must be a file inside the active RIP repository.")
    return resolved.relative_to(repository).as_posix()


def format_details(result: ReasoningResult, elapsed_seconds: float) -> str:
    lines = [
        f"Provider: {result.provider}",
        f"Model: {result.model}",
        f"Elapsed: {elapsed_seconds:.1f} seconds",
        f"Cited observations: {len(result.cited_observation_ids)}",
    ]
    if result.input_tokens is not None:
        lines.append(f"Input tokens: {result.input_tokens}")
    if result.output_tokens is not None:
        lines.append(f"Output tokens: {result.output_tokens}")
    if result.response_id:
        lines.append(f"Response ID: {result.response_id}")
    if result.unknown_observation_ids:
        lines.append("Unknown observation IDs: " + ", ".join(result.unknown_observation_ids))
    return "\n".join(lines)


def format_voice_status(status: dict[str, object]) -> str:
    microphone = status.get("microphone_name") or "Default device"
    configured_microphone = status.get("microphone")
    configured = "Default" if configured_microphone is None else str(configured_microphone)
    return "\n".join(
        (
            f"Configured microphone: {configured}",
            f"Resolved microphone: {microphone}",
            f"Configured voice: {status.get('voice', 'Unavailable')}",
            f"Speech enabled: {'Yes' if status.get('enabled') else 'No'}",
            f"Transcription model: {status.get('transcription_model', 'Unavailable')}",
        )
    )


def format_discovery_details(decision: DiscoveryDecision) -> str:
    lines = [f"Mode: {decision.mode.value}", f"Foundation-only: {'Yes' if decision.foundation_only else 'No'}", "Selected artifacts: " + (", ".join(decision.resolved_paths) or "None")]
    if decision.reason:
        lines.append(f"Reason: {decision.reason}")
    if decision.report:
        lines.extend((f"Fingerprint: {decision.report.discovery_fingerprint}", f"Candidates: {decision.report.diagnostics.artifacts_ranked}", f"Excluded: {decision.report.diagnostics.artifacts_excluded}"))
        for ranking in decision.report.rankings:
            reasons = ", ".join(f"{item.signal} +{item.contribution}" for item in ranking.reason_vector) or "no lexical matches"
            lines.append(f"{ranking.rank}. {ranking.candidate.repository_relative_path}: {ranking.score} ({reasons})")
    return "\n".join(lines)


def format_understanding_meter(result: ObservationRun) -> str:
    labels = {
        UnderstandingState.OBSERVED: "Observed",
        UnderstandingState.SIGNALS_DETECTED: "Signals Detected",
        UnderstandingState.UNKNOWN: "Unknown",
        UnderstandingState.REQUIRES_CONFIRMATION: "Requires Confirmation",
    }
    return "\n".join(f"{dimension.name}: {labels[dimension.state]} — {dimension.explanation}" for dimension in result.understanding_meter.dimensions)


def format_observation_summary(result: ObservationRun) -> str:
    groups = (
        ("Observed", result.summary.observed),
        ("Evidence Signals Detected", result.summary.discovered),
        ("Unknown", result.summary.unknown),
        ("Requires Confirmation", result.summary.requires_confirmation),
    )
    lines: list[str] = []
    for heading, items in groups:
        lines.append(heading)
        if not items:
            lines.append("- None")
        for item in items:
            evidence = ", ".join(item.evidence_paths) or "observation scope"
            lines.append(f"- {item.statement} [{evidence}]")
    return "\n".join(lines)


def format_understanding_proposal(proposal: OrganizationalUnderstandingProposal) -> str:
    """Experience-layer rendering; internal enum values are never customer-facing."""
    readiness = {
        "preliminary": "Preliminary",
        "evidence-complete": "Evidence Complete",
        "human-review-required": "Human Review Required",
        "governance-draft-ready": "Governance Draft Ready",
    }[proposal.readiness.value]
    labels = {
        "directly-observed": "Direct observation",
        "supplied-by-customer": "Customer-supplied knowledge",
        "confirmed-interpretation": "Confirmed interpretation",
        "unresolved": "Unresolved",
        "contradicted": "Contradicted",
        "authority-not-established": "Authority not established",
        "historical-or-current-unconfirmed": "Historical or current status not confirmed",
    }
    lines = [f"Readiness: {readiness}", "Reasons: " + "; ".join(proposal.readiness_reasons), "Blockers: " + (", ".join(proposal.readiness_blockers) or "None"), "", "This proposal is not governance, Organizational Memory, approval, or activation."]
    for section in proposal.sections:
        lines.extend(("", section.title))
        for statement in section.statements:
            sources = ", ".join((*statement.provenance.observation_ids, *statement.provenance.answer_ids, *statement.provenance.interpretation_ids))
            lines.append(f"- {labels[statement.epistemic_label.value]}: {statement.statement_text} [Why do you believe this? {sources or 'uncertainty record'}]")
    return "\n".join(lines)


class OnboardingWindow(tk.Toplevel):
    """Phase 6A organization onboarding: explicit, read-only observation only."""

    POLL_INTERVAL_MS = 100

    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("RIP Organization Onboarding")
        self.geometry("920x720")
        self.minsize(720, 560)
        self.transient(parent)
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._busy = False
        self._capability = recommend_reasoning_capability()
        self._context = None
        self._observation: ObservationRun | None = None
        self._guided_state: GuidedUnderstandingState | None = None
        self._proposal: OrganizationalUnderstandingProposal | None = None
        self.organization_id = tk.StringVar()
        self.organization_name = tk.StringVar()
        self.repository_path = tk.StringVar()
        self.workspace_path = tk.StringVar(value=str(Path.home() / ".rip-onboarding"))
        self.provider_id = tk.StringVar(value=self._capability.provider_id)
        self.model = tk.StringVar(value=self._capability.model)
        self.readiness = tk.StringVar(value="Select a capability to check local configuration and declared context support. Live provider connectivity is not verified in Phase 6A.")
        self.activity = tk.StringVar(value="Ready to establish an isolated, read-only onboarding run.")
        self.next_stage = tk.StringVar(value="Next stage: observe approved repository evidence.")
        self.respondent_identity = tk.StringVar()
        self.respondent_role = tk.StringVar()
        self.authority_claim = tk.StringVar(value="supplied by customer; authority not verified")
        self.answer_disposition = tk.StringVar(value=GuidedAnswerDisposition.ANSWERED.value)
        self._build_ui()
        self.after(self.POLL_INTERVAL_MS, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        banner = ttk.Label(self, text="Customer Sources — Read Only", anchor="center", padding=10, font=("Segoe UI", 11, "bold"))
        banner.grid(row=0, column=0, sticky="ew")
        ttk.Label(self, text="Onboarding records are written only to the isolated RIP workspace. Customer repositories and approved external sources remain read-only; Phase 6A cannot promote governance, activate an organization, or take operational customer action.", wraplength=850, padding=(14, 0, 14, 10)).grid(row=1, column=0, sticky="w")

        setup = ttk.LabelFrame(self, text="Organization and Reasoning Capability", padding=10)
        setup.grid(row=2, column=0, sticky="ew", padx=12)
        setup.columnconfigure(1, weight=1)
        self._field(setup, "Organization ID", self.organization_id, 0)
        self._field(setup, "Organization name", self.organization_name, 1)
        self._field(setup, "Repository", self.repository_path, 2, browse=self._choose_repository)
        self._field(setup, "RIP workspace", self.workspace_path, 3, browse=self._choose_workspace)
        self._field(setup, "Provider override", self.provider_id, 4)
        self._field(setup, "Model override", self.model, 5)
        self.validate_button = ttk.Button(setup, text="Validate Capability", command=self.validate_capability)
        self.validate_button.grid(row=6, column=0, sticky="w", pady=(8, 0))
        ttk.Label(setup, textvariable=self.readiness, wraplength=650).grid(row=6, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(8, 0))

        progress = ttk.LabelFrame(self, text="Current Activity", padding=10)
        progress.grid(row=3, column=0, sticky="ew", padx=12, pady=(8, 0))
        ttk.Label(progress, textvariable=self.activity, wraplength=850).pack(anchor="w")
        ttk.Label(progress, textvariable=self.next_stage, wraplength=850).pack(anchor="w", pady=(4, 0))

        results = ttk.PanedWindow(self, orient="horizontal")
        results.grid(row=4, column=0, sticky="nsew", padx=12, pady=(8, 0))
        feed_frame = ttk.LabelFrame(results, text="Discovery Feed", padding=6)
        meter_frame = ttk.LabelFrame(results, text="Understanding Meter and Observation Summary", padding=6)
        results.add(feed_frame, weight=1); results.add(meter_frame, weight=2)
        self.feed = tk.Listbox(feed_frame, height=16)
        self.feed.pack(fill="both", expand=True)
        self.summary = tk.Text(meter_frame, wrap="word", state="disabled", font=("Segoe UI", 9))
        self.summary.pack(fill="both", expand=True)

        guided = ttk.LabelFrame(self, text="Guided Organizational Understanding", padding=8)
        guided.grid(row=5, column=0, sticky="ew", padx=12, pady=(8, 0))
        guided.columnconfigure(0, weight=1)
        self.guided_details = tk.Text(guided, height=7, wrap="word", state="disabled", font=("Segoe UI", 9))
        self.guided_details.grid(row=0, column=0, columnspan=4, sticky="ew")
        ttk.Label(guided, text="Respondent").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(guided, textvariable=self.respondent_identity, width=20).grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
        ttk.Label(guided, text="Role").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(guided, textvariable=self.respondent_role, width=20).grid(row=1, column=3, sticky="ew", padx=4, pady=(6, 0))
        ttk.Label(guided, text="Authority claim").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(guided, textvariable=self.authority_claim).grid(row=2, column=1, columnspan=3, sticky="ew", padx=4, pady=(4, 0))
        ttk.Label(guided, text="Disposition").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Combobox(guided, textvariable=self.answer_disposition, state="readonly", values=tuple(item.value for item in GuidedAnswerDisposition)).grid(row=3, column=1, sticky="ew", padx=4, pady=(4, 0))
        self.guided_answer = tk.Text(guided, height=3, wrap="word")
        self.guided_answer.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        controls = ttk.Frame(self, padding=12)
        controls.grid(row=6, column=0, sticky="ew")
        self.observe_button = ttk.Button(controls, text="Begin Read-Only Observation", command=self.begin_observation)
        self.observe_button.pack(side="left")
        ttk.Button(controls, text="Restart Onboarding Run", command=self.begin_observation).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Review Classification", command=self.open_classification_review).pack(side="left", padx=(8, 0))
        self.guided_button = ttk.Button(controls, text="Begin / Resume Guided Understanding", command=self.begin_guided_understanding, state="disabled")
        self.guided_button.pack(side="left", padx=(8, 0))
        self.answer_button = ttk.Button(controls, text="Record Supplied Answer", command=self.record_guided_answer, state="disabled")
        self.answer_button.pack(side="left", padx=(8, 0))
        self.proposal_button = ttk.Button(controls, text="Generate Understanding Proposal", command=self.generate_proposal, state="disabled")
        self.proposal_button.pack(side="left", padx=(8, 0))
        self.review_proposal_button = ttk.Button(controls, text="Mark Proposal Reviewed", command=self.review_proposal, state="disabled")
        self.review_proposal_button.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Close", command=self.destroy).pack(side="right")

    def _field(self, parent: ttk.LabelFrame, label: str, variable: tk.StringVar, row: int, browse=None) -> None:
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=2)
        if browse:
            ttk.Button(parent, text="Browse", command=browse).grid(row=row, column=2, padx=(8, 0), pady=2)

    def _choose_repository(self) -> None:
        selected = filedialog.askdirectory(title="Select approved repository to observe")
        if selected: self.repository_path.set(selected)

    def _choose_workspace(self) -> None:
        selected = filedialog.askdirectory(title="Select RIP-controlled onboarding workspace")
        if selected: self.workspace_path.set(selected)

    def open_classification_review(self) -> None:
        run_id = self._context.onboarding_run_id if self._context else simpledialog.askstring("Classification Review", "Onboarding run ID to inspect:", parent=self)
        if not run_id or not self.workspace_path.get().strip(): return
        try: ClassificationReviewWindow(self, self.workspace_path.get(), run_id)
        except Exception as exc: messagebox.showerror("Classification Review", str(exc))

    def _selected_capability(self) -> ReasoningCapability:
        return ReasoningCapability(self.provider_id.get().strip(), self.model.get().strip(), self.provider_id.get().strip() or "Provider", True, True, False)

    def validate_capability(self) -> bool:
        try:
            validation = validate_reasoning_capability(self._selected_capability())
        except ValueError as exc:
            self.readiness.set(str(exc)); return False
        self._capability = validation.capability
        self.readiness.set(" ".join(validation.reasons))
        return validation.locally_eligible_for_observation

    def begin_observation(self) -> None:
        if self._busy:
            return
        if not all((self.organization_id.get().strip(), self.organization_name.get().strip(), self.repository_path.get().strip(), self.workspace_path.get().strip())):
            messagebox.showerror("Organization Onboarding", "Organization identity, repository, and workspace are required.")
            return
        if not self.validate_capability():
            messagebox.showerror("Reasoning Capability", self.readiness.get())
            return
        try:
            workspace = create_organization_workspace(self.workspace_path.get(), organization_id=self.organization_id.get().strip(), display_name=self.organization_name.get().strip(), repository_path=self.repository_path.get())
            self._context = restart_onboarding_run(workspace, repository_path=self.repository_path.get(), reasoning_capability=self._capability)
        except Exception as exc:
            messagebox.showerror("Organization Onboarding", str(exc)); return
        self._busy = True; self.observe_button.configure(state="disabled")
        self.feed.delete(0, tk.END); self._replace_summary("")
        self.activity.set("Observing approved repository evidence. Customer sources are read-only; onboarding records are written only to the isolated RIP workspace.")
        self.next_stage.set("Next stage: organize observed evidence into an onboarding summary.")
        threading.Thread(target=self._observe_worker, args=(self._context,), daemon=True).start()

    def _observe_worker(self, context) -> None:
        try:
            result = observe_organization(context, progress_callback=lambda event: self._events.put(("feed", event)))
            self._events.put(("observed", result))
        except Exception as exc:
            self._events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                event_type, payload = self._events.get_nowait()
                if event_type == "feed":
                    event = payload
                    self.feed.insert(tk.END, f"{event.sequence + 1}. {event.message}")
                    self.activity.set(event.message)
                elif event_type == "observed" and isinstance(payload, ObservationRun):
                    self._observation = payload
                    self._replace_summary(format_understanding_meter(payload) + "\n\n" + format_observation_summary(payload))
                    self.activity.set("Read-only observation complete. Every summary item is linked to observed repository evidence; no customer-source modifications occurred.")
                    self.next_stage.set("Next stage: begin deterministic guided understanding. Supplied answers remain non-governance and non-memory.")
                    self.guided_button.configure(state="normal")
                    self._finish()
                elif event_type == "error":
                    self.activity.set("Observation stopped: " + str(payload)); self.next_stage.set("Next stage: correct the displayed issue or start a fresh onboarding run.")
                    self._finish()
        except queue.Empty:
            pass
        finally:
            if self.winfo_exists(): self.after(self.POLL_INTERVAL_MS, self._poll_events)

    def _replace_summary(self, value: str) -> None:
        self.summary.configure(state="normal"); self.summary.delete("1.0", "end"); self.summary.insert("1.0", value); self.summary.configure(state="disabled")

    def _finish(self) -> None:
        self._busy = False; self.observe_button.configure(state="normal")

    def begin_guided_understanding(self) -> None:
        if self._observation is None:
            messagebox.showerror("Guided Understanding", "Complete a read-only observation before guided understanding.")
            return
        try:
            self._guided_state = begin_guided_understanding(self._observation)
            self._render_guided_question()
            self.proposal_button.configure(state="normal")
            self.activity.set("Guided understanding uses deterministic questions derived from observed uncertainty. Customer sources remain read-only.")
        except Exception as exc:
            messagebox.showerror("Guided Understanding", str(exc))

    def record_guided_answer(self) -> None:
        if self._observation is None or self._guided_state is None:
            return
        question = self._current_guided_question()
        if question is None:
            return
        try:
            self._guided_state = record_guided_answer(
                self._observation, self._guided_state, question_id=question.question_id,
                respondent_identity=self.respondent_identity.get(), respondent_role=self.respondent_role.get(),
                authority_claim=self.authority_claim.get(), disposition=GuidedAnswerDisposition(self.answer_disposition.get()),
                answer=self.guided_answer.get("1.0", "end").strip(),
            )
            self.guided_answer.delete("1.0", "end")
            self._render_guided_question()
        except Exception as exc:
            messagebox.showerror("Guided Understanding", str(exc))

    def _current_guided_question(self):
        if self._guided_state is None:
            return None
        addressed = {item.question_id for item in self._guided_state.answer_history}
        return next((item for item in self._guided_state.questions if item.question_id not in addressed), None)

    def _render_guided_question(self) -> None:
        question = self._current_guided_question()
        self.guided_details.configure(state="normal"); self.guided_details.delete("1.0", "end")
        if question is None:
            summary = self._guided_state.summary
            self.guided_details.insert("1.0", f"No remaining unanswered questions. Readiness: {summary.readiness}; authority gaps: {summary.authority_gaps}; contradictions: {summary.contradictions}. No governance, approval, activation, or organizational memory was created.")
            self.answer_button.configure(state="disabled")
        else:
            self.guided_details.insert("1.0", f"Question ({question.priority.value}): {question.prompt}\n\nObserved: {question.observed}\nWhy this exists: {question.why_this_question}\nUncertainty resolved: {question.uncertainty_resolved}\nUnderstanding change: {question.understanding_change}\nEvidence: {', '.join(question.evidence_paths) or 'observation scope'}")
            self.answer_button.configure(state="normal")
        self.guided_details.configure(state="disabled")

    def generate_proposal(self) -> None:
        if self._observation is None or self._guided_state is None:
            return
        try:
            self._proposal = generate_understanding_proposal(self._observation, self._guided_state)
            self._replace_summary(format_understanding_proposal(self._proposal))
            self.activity.set("Understanding proposal generated from current evidence. This proposal is not governance, Organizational Memory, approval, or activation.")
            self.review_proposal_button.configure(state="normal")
        except Exception as exc:
            messagebox.showerror("Understanding Proposal", str(exc))

    def review_proposal(self) -> None:
        if self._proposal is None:
            return
        self._proposal = review_understanding_proposal(self._observation, self._proposal)
        self._replace_summary(format_understanding_proposal(self._proposal))
        self.activity.set("Proposal marked reviewed. Reviewed does not mean approved.")


class RipConsole(tk.Tk):
    POLL_INTERVAL_MS = 100

    def __init__(self) -> None:
        super().__init__()
        self.title("RIP Reasoning Console")
        self.geometry("980x720")
        self.minsize(760, 520)

        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._busy = False
        self._last_response = ""
        self._last_details = ""
        self._details_visible = False
        self._voice = VoiceManager()
        self._voice.set_state_callback(lambda state: self._events.put(("voice_state", state)))
        self._muted = False
        self._primary_evidence: list[str] = []
        self._excluded_evidence: list[str] = []
        self._use_only_selected = tk.BooleanVar(value=False)
        self._candidate_limit = tk.IntVar(value=3)
        self._discovery_details = ""

        self._build_ui()
        self.after(self.POLL_INTERVAL_MS, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(12, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="RIP Reasoning Console", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        self.status_label = ttk.Label(header, text="Idle")
        self.status_label.grid(row=0, column=1, sticky="e")
        ttk.Button(header, text="Organization Onboarding", command=self.open_onboarding).grid(row=1, column=1, sticky="e", pady=(4, 0))

        history_frame = ttk.Frame(self, padding=(12, 0, 12, 8))
        history_frame.grid(row=1, column=0, sticky="nsew")
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)

        self.history = tk.Text(
            history_frame,
            wrap="word",
            state="disabled",
            padx=14,
            pady=12,
            font=("Segoe UI", 10),
        )
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history.yview)
        self.history.configure(yscrollcommand=scrollbar.set)
        self.history.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.history.tag_configure("speaker", font=("Segoe UI", 10, "bold"), spacing1=8)
        self.history.tag_configure("answer", spacing3=12)
        self.history.tag_configure("error", foreground="#8b0000", spacing3=12)

        controls = ttk.Frame(self, padding=(12, 4, 12, 8))
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)

        self.question = tk.Text(controls, height=4, wrap="word", font=("Segoe UI", 10), padx=8, pady=8)
        self.question.grid(row=0, column=0, columnspan=7, sticky="ew")
        self.question.bind("<Return>", self._on_return)
        self.bind("<F4>", self._on_talk_shortcut)
        self.question.focus_set()

        self.send_button = ttk.Button(controls, text="Send", command=self.send_question)
        self.send_button.grid(row=1, column=6, sticky="e", pady=(8, 0))
        ttk.Button(controls, text="Clear", command=self.clear_conversation).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.copy_button = ttk.Button(controls, text="Copy Last Response", command=self.copy_last_response, state="disabled")
        self.copy_button.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        self.details_button = ttk.Button(controls, text="Show Details", command=self.toggle_details, state="disabled")
        self.details_button.grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))
        self.voice_status_button = ttk.Button(controls, text="Voice Status", command=self.show_voice_status)
        self.voice_status_button.grid(row=1, column=3, sticky="w", padx=(8, 0), pady=(8, 0))
        self.talk_button = ttk.Button(controls, text="Talk (F4)", command=self.talk)
        self.talk_button.grid(row=1, column=4, sticky="w", padx=(8, 0), pady=(8, 0))
        self.mute_button = ttk.Button(controls, text="Mute", command=self.toggle_mute)
        self.mute_button.grid(row=1, column=5, sticky="w", padx=(8, 0), pady=(8, 0))

        evidence = ttk.LabelFrame(controls, text="Primary Evidence — Automatic Discovery", padding=(6, 4))
        evidence.grid(row=2, column=0, columnspan=7, sticky="ew", pady=(8, 0))
        evidence.columnconfigure(0, weight=1)
        self.evidence_list = tk.Listbox(evidence, height=3)
        self.evidence_list.grid(row=0, column=0, rowspan=2, sticky="ew")
        ttk.Button(evidence, text="Include Artifacts", command=self.add_primary_evidence).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(evidence, text="Remove", command=self.remove_primary_evidence).grid(row=1, column=1, padx=(8, 0))
        ttk.Button(evidence, text="Clear", command=self.clear_primary_evidence).grid(row=0, column=2, rowspan=2, padx=(8, 0))
        self.use_only_check = ttk.Checkbutton(evidence, text="Use Only Selected Artifacts", variable=self._use_only_selected)
        self.use_only_check.grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(evidence, text="Candidate Limit:").grid(row=2, column=1, sticky="e", pady=(6, 0))
        ttk.Spinbox(evidence, from_=1, to=20, textvariable=self._candidate_limit, width=4).grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Button(evidence, text="Exclude Artifacts", command=self.add_excluded_evidence).grid(row=3, column=1, padx=(8, 0), pady=(6, 0))
        self.excluded_list = tk.Listbox(evidence, height=2)
        self.excluded_list.grid(row=3, column=0, rowspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(evidence, text="Remove Exclusion", command=self.remove_excluded_evidence).grid(row=4, column=1, padx=(8, 0))
        self.discovery_list = tk.Listbox(evidence, height=3)
        self.discovery_list.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        self.discovery_button = ttk.Button(evidence, text="Discovery Details", command=self.show_discovery_details, state="disabled")
        self.discovery_button.grid(row=5, column=1, padx=(8, 0))

        self.details_frame = ttk.LabelFrame(self, text="Reasoning Details", padding=(12, 8))
        self.details_text = tk.Text(self.details_frame, height=7, wrap="word", state="disabled", font=("Consolas", 9))
        self.details_text.pack(fill="both", expand=True)

        ttk.Label(
            self,
            text="Enter sends. Shift+Enter inserts a new line.",
            padding=(12, 0, 12, 8),
        ).grid(row=4, column=0, sticky="w")

    def _on_return(self, event: tk.Event) -> str | None:
        if event.state & 0x0001:  # Shift key
            return None
        self.send_question()
        return "break"

    def add_primary_evidence(self) -> None:
        root = find_repository_root()
        selected = filedialog.askopenfilenames(initialdir=root, title="Select primary evidence")
        try:
            for path in selected:
                relative = repository_relative_evidence(path, root)
                if relative not in self._primary_evidence: self._primary_evidence.append(relative)
            self._refresh_primary_evidence()
        except ValueError as exc: messagebox.showerror("Primary Evidence", str(exc))

    def add_excluded_evidence(self) -> None:
        root = find_repository_root()
        try:
            for path in filedialog.askopenfilenames(initialdir=root, title="Exclude discovery artifacts"):
                relative = repository_relative_evidence(path, root)
                if relative not in self._excluded_evidence: self._excluded_evidence.append(relative)
            self._refresh_excluded_evidence()
        except ValueError as exc: messagebox.showerror("Primary Evidence", str(exc))

    def remove_primary_evidence(self) -> None:
        for index in reversed(self.evidence_list.curselection()): self._primary_evidence.pop(index)
        self._refresh_primary_evidence()

    def clear_primary_evidence(self) -> None:
        self._primary_evidence.clear(); self._refresh_primary_evidence()

    def remove_excluded_evidence(self) -> None:
        for index in reversed(self.excluded_list.curselection()): self._excluded_evidence.pop(index)
        self._refresh_excluded_evidence()

    def _refresh_primary_evidence(self) -> None:
        self.evidence_list.delete(0, tk.END)
        for path in self._primary_evidence: self.evidence_list.insert(tk.END, path)

    def _refresh_excluded_evidence(self) -> None:
        self.excluded_list.delete(0, tk.END)
        for path in self._excluded_evidence: self.excluded_list.insert(tk.END, path)

    def _on_talk_shortcut(self, _event: tk.Event) -> str:
        self.talk()
        return "break"

    def send_question(self) -> None:
        if self._busy:
            return
        question = self.question.get("1.0", "end").strip()
        if not question:
            return

        self.question.delete("1.0", "end")
        self._append_message("You", question)
        self._set_busy(True)
        self._voice.transition(VoiceState.REASONING)

        worker = threading.Thread(target=self._run_reasoning, args=(question, tuple(self._primary_evidence), tuple(self._excluded_evidence), self._use_only_selected.get(), self._candidate_limit.get()), daemon=True)
        worker.start()

    def talk(self) -> None:
        if self._voice.state == VoiceState.LISTENING:
            self._voice.request_stop()
            return
        if self._busy:
            return
        self._set_busy(True)
        threading.Thread(target=self._run_voice_input, daemon=True).start()

    def _run_voice_input(self) -> None:
        file_descriptor, temporary_path = tempfile.mkstemp(suffix=".wav")
        os.close(file_descriptor)
        try:
            text = self._voice.listen_once(Path(temporary_path))
            self._events.put(("voice_input", text))
        except Exception as exc:
            self._events.put(("voice_error", str(exc) or "Transcription failed."))
        finally:
            Path(temporary_path).unlink(missing_ok=True)

    def _run_reasoning(self, question: str, includes: tuple[str, ...] = (), excludes: tuple[str, ...] = (), use_only: bool = False, candidate_limit: int = 3) -> None:
        started = time.perf_counter()
        try:
            result = ask_repository(
                question,
                discovery_includes=list(includes), discovery_excludes=list(excludes), use_only_selected_artifacts=use_only, discovery_candidate_limit=candidate_limit,
                discovery_callback=lambda decision: self._events.put(("discovery", decision)),
                status_callback=lambda status: self._events.put(("status", status)),
            )
            elapsed = time.perf_counter() - started
            response = ConsoleResponse(result.answer, format_details(result, elapsed))
            self._events.put(("result", response))
        except Exception as exc:  # UI boundary: present unexpected provider/runtime errors cleanly.
            self._events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                event_type, payload = self._events.get_nowait()
                if event_type == "status":
                    self._set_status(str(payload))
                elif event_type == "voice_state":
                    self._render_voice_state(payload)
                elif event_type == "result":
                    self._handle_result(payload)
                elif event_type == "error":
                    self._handle_error(str(payload))
                elif event_type == "discovery":
                    self._handle_discovery(payload)
                elif event_type == "voice_input":
                    self._set_busy(False)
                    if payload:
                        self.question.insert("1.0", str(payload))
                        self.send_question()
                    else:
                        self._set_status("Idle")
                elif event_type == "voice_error":
                    self._handle_error(str(payload))
                elif event_type == "voice_complete":
                    self._set_busy(False)
                    self._voice.reset()
        except queue.Empty:
            pass
        finally:
            self.after(self.POLL_INTERVAL_MS, self._poll_events)

    def _handle_result(self, payload: object) -> None:
        if not isinstance(payload, ConsoleResponse):
            self._handle_error("RIP returned an unexpected response.")
            return
        self._last_response = payload.answer
        self._last_details = payload.details
        self._append_message("RIP", payload.answer)
        self._replace_details(payload.details)
        self.copy_button.configure(state="normal")
        self.details_button.configure(state="normal")
        if not self._muted:
            threading.Thread(target=self._speak, args=(payload.answer,), daemon=True).start()
        else:
            self._set_busy(False)
            self._set_status("Ready")

    def _speak(self, text: str) -> None:
        try:
            result = self._voice.speak(text, play=True)
            if not result.success or not result.playback:
                self._events.put(("voice_error", result.message))
                return
            self._events.put(("voice_complete", None))
        except Exception:
            self._events.put(("voice_error", "Speech playback failed."))

    def _handle_error(self, message: str) -> None:
        self._append_message("Error", message, tag="error")
        self._set_busy(False)
        self._set_status("Error")
        self._voice.reset()

    def _handle_discovery(self, decision: object) -> None:
        if not isinstance(decision, DiscoveryDecision): return
        self._discovery_details = format_discovery_details(decision)
        self.discovery_list.delete(0, tk.END)
        label = "Automatic Discovery BYPASSED" if not decision.discovery_performed else ("Foundation-only" if decision.foundation_only else "Discovered candidates")
        self.discovery_list.insert(tk.END, label)
        for path in decision.resolved_paths: self.discovery_list.insert(tk.END, path)
        self.discovery_button.configure(state="normal")

    def _append_message(self, speaker: str, body: str, *, tag: str = "answer") -> None:
        self.history.configure(state="normal")
        self.history.insert("end", f"{speaker}\n", "speaker")
        self.history.insert("end", body.rstrip() + "\n\n", tag)
        self.history.configure(state="disabled")
        self.history.see("end")

    def _replace_details(self, details: str) -> None:
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", "end")
        self.details_text.insert("1.0", details)
        self.details_text.configure(state="disabled")

    def _set_status(self, status: str) -> None:
        self.status_label.configure(text=status)

    def _render_voice_state(self, state: object) -> None:
        labels = {VoiceState.IDLE: "Idle", VoiceState.LISTENING: "🎤 Listening...", VoiceState.TRANSCRIPT_FINALIZING: "🤫 Silence detected...", VoiceState.TRANSCRIBING: "📝 Transcribing...", VoiceState.REASONING: "🧠 Reasoning...", VoiceState.SYNTHESIZING: "🔊 Generating speech...", VoiceState.PLAYING: "▶ Playing...", VoiceState.ERROR: "❌ Error"}
        if not isinstance(state, VoiceState):
            return
        self._set_status(labels[state])
        if state == VoiceState.LISTENING:
            self.talk_button.configure(text="Stop", state="normal")
        elif state == VoiceState.IDLE:
            self.talk_button.configure(text="Talk (F4)", state="normal")
        else:
            self.talk_button.configure(text="Talk (F4)", state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_button.configure(state="disabled" if busy else "normal")
        self.question.configure(state="disabled" if busy else "normal")
        self.talk_button.configure(state="disabled" if busy else "normal")
        if not busy:
            self.question.focus_set()

    def copy_last_response(self) -> None:
        if not self._last_response:
            return
        self.clipboard_clear()
        self.clipboard_append(self._last_response)
        self.update_idletasks()
        self._set_status("Response copied to clipboard")

    def toggle_mute(self) -> None:
        self._muted = not self._muted
        self.mute_button.configure(text="Unmute" if self._muted else "Mute")
        self._set_status("Muted" if self._muted else "Ready")

    def show_voice_status(self) -> None:
        try:
            contents = format_voice_status(self._voice.get_status())
        except Exception:
            contents = "Voice status is unavailable."
        window = tk.Toplevel(self)
        window.title("RIP Voice Status")
        window.transient(self)
        ttk.Label(window, text=contents, justify="left", padding=16).pack(fill="both", expand=True)
        ttk.Button(window, text="Close", command=window.destroy).pack(pady=(0, 12))

    def clear_conversation(self) -> None:
        if self._busy:
            return
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.configure(state="disabled")
        self._last_response = ""
        self._last_details = ""
        self.copy_button.configure(state="disabled")
        self.details_button.configure(state="disabled")
        if self._details_visible:
            self.toggle_details()
        self._replace_details("")
        self._set_status("Ready")

    def toggle_details(self) -> None:
        if not self._last_details:
            return
        if self._details_visible:
            self.details_frame.grid_remove()
            self.details_button.configure(text="Show Details")
            self._details_visible = False
        else:
            self.details_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
            self.details_button.configure(text="Hide Details")
            self._details_visible = True

    def show_discovery_details(self) -> None:
        if not self._discovery_details: return
        window = tk.Toplevel(self); window.title("Discovery Details"); window.transient(self)
        text = tk.Text(window, height=18, width=100, wrap="word"); text.insert("1.0", self._discovery_details); text.configure(state="disabled"); text.pack(fill="both", expand=True, padx=12, pady=12)

    def open_onboarding(self) -> None:
        OnboardingWindow(self)


def main() -> int:
    app = RipConsole()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
