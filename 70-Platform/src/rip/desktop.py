"""Single-window Customer Zero operator shell.

Presentation owns navigation, task presentation, notifications, and window
management only.  It does not interpret evidence or mutate authority state.
"""
from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import json
import ntpath
import queue
import threading
import traceback
import uuid
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk, messagebox

from .desktop_pages.home import HomeOverview, refresh_home
from .desktop_pages.work_queue import WorkItem
from .desktop_pages.primary_action import resolve_primary_action
from .desktop_pages.repository_memory import RepositoryMemory, build_repository_memory, render_repository_memory
from .desktop_pages.repository_intelligence import answer_question, render_answer
from .desktop_pages.architect import render_architect
from .desktop_pages.runs import RunSummary, load_runs, run_display_text
from .desktop_pages.history import load_history
from .desktop_pages.investigate import EvidenceView, open_evidence, render_evidence, render_workspace, review_evidence, append_investigation_note
from .desktop_pages.platform import PlatformHealth, verify_platform
from .desktop_pages.autonomy import render_autonomy_status
from .autonomy import AuthenticatedHuman, SDAWorkflow, first_sda_decision_draft
from .governed_memory import MemoryStore, seed_observed_projection
from .paths import storage_directory
from .elevation import elevation_failure_reason
from .onboarding import create_organization_workspace, observe_organization, recommend_reasoning_capability, restart_onboarding_run, continue_retained_post_integrity_run
from .platform_provisioning import provision_trust_authority_context


@dataclass(frozen=True, slots=True)
class ShellPage:
    name: str
    question: str
    detail: str


PAGES = (
    ShellPage("Home", "What needs attention?", "RIP presents the current workspace, platform health, and operator notifications here."),
    ShellPage("Observe", "What can RIP observe safely?", "Observation remains read-only and is performed only through the existing onboarding service."),
    ShellPage("Runs", "What is the state of current and retained work?", "Run state is evidence-backed. This screen does not reconstruct or advance lifecycle state."),
    ShellPage("History", "What happened and why?", "Historical records remain owned by their existing Authorities and are presented here as read-only evidence."),
    ShellPage("Investigate", "What does the retained evidence show?", "Investigation invokes existing reasoning services; no new interpretation authority exists in the shell."),
    ShellPage("Repository Memory", "What has RIP observed about this repository?", "Repository Memory is a deterministic, read-only projection of retained observation evidence."),
    ShellPage("Ask Repository", "What does retained Repository Memory show?", "Repository Intelligence answers only deterministic facts represented by retained Repository Memory."),
    ShellPage("Architect", "What is the next evidence-backed engineering milestone?", "Architect produces read-only, bounded guidance from Repository Memory."),
    ShellPage("Platform", "Is the platform ready?", "Platform health, background tasks, and diagnostics appear here without exposing command shells."),
    ShellPage("Autonomy & Budget", "What may RIP do autonomously?", "This view projects the current authority, budget, and retained execution evidence. It cannot grant authority or spend a budget."),
    ShellPage("What I Know", "What governed knowledge is currently applicable?", "Memory is scoped, evidence-backed, and separate from raw conversation history."),
    ShellPage("Search", "What evidence matches this question?", "Search is a presentation of existing retrieval and reasoning results."),
)


class _SingleInstance:
    def __init__(self) -> None:
        self._handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\RIP.CustomerZero.OperatorShell")
        self.already_running = ctypes.windll.kernel32.GetLastError() == 183

    def close(self) -> None:
        if self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


class RipDesktop(tk.Tk):
    """One main window; all pages are in-window frames, never utility windows."""

    @staticmethod
    def _trace_workspace(event: str, **values: object) -> None:
        """Retain the installed-product Open Workspace handoff without changing it."""
        directory = storage_directory("Diagnostics")
        directory.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **values}
        with (directory / "desktop-open-workspace-trace.jsonl").open("a", encoding="utf-8") as trace:
            trace.write(json.dumps(payload, sort_keys=True, default=str) + "\n")

    def __init__(self) -> None:
        super().__init__()
        self.title("RIP")
        self.geometry("1180x760")
        self.minsize(900, 600)
        self._events: queue.Queue[tuple[str, str]] = queue.Queue()
        self._page = tk.StringVar(value="Home")
        self._status = tk.StringVar(value="Ready")
        self._notification = tk.StringVar(value="No new notifications")
        self._home_loaded = False
        self._home_overview: HomeOverview | None = None
        self._observe_source = tk.StringVar(value=r"C:\RIP")
        self._observe_organization = tk.StringVar(value="customer-zero")
        self._observe_status = tk.StringVar(value="Ready to observe")
        self._evidence_context = tk.StringVar()
        self._runs: tuple[RunSummary, ...] = ()
        self._history = ()
        self._observe_refresh_after: str | None = None
        self._build()
        self._show_page("Home")
        self.after(100, self._poll)

    def _build(self) -> None:
        style = ttk.Style(self)
        style.configure("Shell.TFrame", background="#f5f6f7")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Question.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 12, "bold"))
        root = ttk.Frame(self, style="Shell.TFrame", padding=(24, 18)); root.pack(fill="both", expand=True)
        header = ttk.Frame(root); header.pack(fill="x")
        ttk.Label(header, text="RIP", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Customer Zero", foreground="#5b6570").pack(side="left", padx=(10, 0), pady=(5, 0))
        navigation = ttk.Frame(root, padding=(0, 18, 0, 14)); navigation.pack(fill="x")
        for page in PAGES:
            ttk.Radiobutton(navigation, text=page.name, value=page.name, variable=self._page,
                            command=lambda name=page.name: self._show_page(name)).pack(side="left", padx=(0, 8))
        self._content = ttk.Frame(root, padding=28); self._content.pack(fill="both", expand=True)
        self._content.columnconfigure(0, weight=1); self._content.rowconfigure(2, weight=1)
        self._question = ttk.Label(self._content, style="Question.TLabel"); self._question.grid(row=0, column=0, sticky="w")
        self._detail = ttk.Label(self._content, wraplength=900, justify="left"); self._detail.grid(row=1, column=0, sticky="nw", pady=(12, 24))
        self._task_frame = ttk.LabelFrame(self._content, text="Background Tasks", padding=14); self._task_frame.grid(row=3, column=0, sticky="nsew", pady=(18, 0))
        self._tasks = tk.Listbox(self._task_frame, height=8, activestyle="none", relief="flat"); self._tasks.pack(fill="both", expand=True)
        self._tasks.insert("end", "No active background tasks")
        status = ttk.Frame(root, padding=(0, 12, 0, 0)); status.pack(fill="x")
        ttk.Label(status, text="Platform Health: ").pack(side="left")
        ttk.Label(status, textvariable=self._status).pack(side="left")
        ttk.Label(status, textvariable=self._notification, foreground="#5b6570").pack(side="right")

    def _show_page(self, name: str) -> None:
        self._page.set(name)
        if name != "Autonomy & Budget": self._task_frame.grid()
        page = next(item for item in PAGES if item.name == name)
        self._question.configure(text=page.question)
        self._detail.configure(text=page.detail)
        self._status.set(f"{name} ready")
        for child in self._content.winfo_children():
            if child not in {self._question, self._detail, self._task_frame}:
                child.destroy()
        if name == "Observe":
            self._build_observe_page()
            return
        if name == "Runs":
            self._build_runs_page(); return
        if name == "History":
            self._build_history_page(); return
        if name == "Investigate":
            RipDesktop._trace_workspace("page-builder-invoked", page=name, active_investigation_context=self._evidence_context.get().strip())
            self._build_investigate_page(); return
        if name == "Repository Memory":
            self._build_repository_memory_page(); return
        if name == "Ask Repository":
            self._build_repository_intelligence_page(); return
        if name == "Architect":
            self._build_architect_page(); return
        if name == "Platform":
            self._build_platform_page(); return
        if name == "Autonomy & Budget":
            self._build_autonomy_page(); return
        if name == "What I Know":
            self._build_memory_page(); return
        if name == "Home" and self._home_overview is not None:
            self._question.configure(text="Operator Work Queue")
            self._detail.configure(text="What requires attention, what completed, and the next recommended operator action.")
            self._render_work_queue(self._home_overview.work_items)
            return
        if name == "Home" and not self._home_loaded:
            self._tasks.delete(0, tk.END); self._tasks.insert("end", "Refreshing platform readiness…")
            threading.Thread(target=self._refresh_home, daemon=True).start()

    def _build_observe_page(self) -> None:
        self._question.configure(text="What is RIP seeing right now?")
        self._detail.configure(text="Observe reads the selected source and presents retained observation evidence. Customer sources remain read-only.")
        form = ttk.Frame(self._content); form.grid(row=2, column=0, sticky="new")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Organization").grid(row=0, column=0, sticky="w", pady=4)
        organization_entry = ttk.Entry(form, textvariable=self._observe_organization); organization_entry.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Current source").grid(row=1, column=0, sticky="w", pady=4)
        source_entry = ttk.Entry(form, textvariable=self._observe_source); source_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self._observe_button = ttk.Button(form, text="Observe", command=self._start_observation)
        self._observe_button.grid(row=2, column=1, sticky="e", pady=(12, 6))
        ttk.Label(form, textvariable=self._observe_status, wraplength=880, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._observe_organization.trace_add("write", self._schedule_observe_refresh)
        self._observe_source.trace_add("write", self._schedule_observe_refresh)
        for entry in (organization_entry, source_entry):
            entry.bind("<FocusOut>", self._refresh_observe_action)
            entry.bind("<Return>", self._refresh_observe_action)
        self._refresh_observe_action()

    def _build_runs_page(self) -> None:
        self._question.configure(text="What work is RIP doing?")
        self._detail.configure(text="Runs presents retained operational state. It does not change work or interpret evidence.")
        frame=ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        self._runs_list=tk.Listbox(frame,height=12,activestyle="none",relief="flat"); self._runs_list.grid(row=0,column=0,sticky="nsew")
        self._runs_list.bind("<<ListboxSelect>>", self._show_run_summary)
        self._runs_list.bind("<Return>", self._open_run)
        self._runs_detail=tk.StringVar(value="Loading known work…")
        ttk.Label(frame,textvariable=self._runs_detail,wraplength=880).grid(row=1,column=0,sticky="w",pady=(10,0))
        ttk.Button(frame,text="Open Run",command=self._open_run).grid(row=2,column=0,sticky="e",pady=(10,0))
        self._load_runs_async()

    def _build_history_page(self) -> None:
        self._question.configure(text="What happened?")
        self._detail.configure(text="History presents a chronological record of retained platform activity. It does not explain causes or reconstruct evidence.")
        frame=ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        self._history_query=tk.StringVar(); ttk.Entry(frame,textvariable=self._history_query).grid(row=0,column=0,sticky="ew")
        ttk.Button(frame,text="Search History",command=self._load_history_async).grid(row=0,column=1,padx=(8,0))
        self._history_list=tk.Listbox(frame,height=12,activestyle="none",relief="flat"); self._history_list.grid(row=1,column=0,columnspan=2,sticky="nsew",pady=(12,0))
        self._history_list.bind("<<ListboxSelect>>", self._show_history_summary)
        self._history_list.bind("<Return>", self._open_history_evidence)
        self._history_detail=tk.StringVar(value="Loading chronological history…"); ttk.Label(frame,textvariable=self._history_detail,wraplength=880).grid(row=2,column=0,columnspan=2,sticky="w",pady=(10,0))
        ttk.Button(frame,text="Open Evidence",command=self._open_history_evidence).grid(row=3,column=1,sticky="e",pady=(10,0))
        self._load_history_async()
        self.after(5000, lambda: self._load_history_async() if self._page.get()=="History" else None)

    def _build_investigate_page(self) -> None:
        RipDesktop._trace_workspace("investigate-builder-entered", active_investigation_context=self._evidence_context.get().strip())
        self._question.configure(text="What decision did RIP make?")
        self._detail.configure(text="Investigate presents the retained decision and its supporting evidence. It does not create, replay, validate, or reinterpret evidence.")
        frame=ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        ttk.Entry(frame,textvariable=self._evidence_context).grid(row=0,column=0,sticky="ew")
        ttk.Button(frame,text="Open Decision",command=self._open_decision).grid(row=0,column=1,padx=(8,0))
        actions=ttk.Frame(frame); actions.grid(row=1,column=0,columnspan=2,sticky="w",pady=(10,0))
        for label, section in (("Review Changed Runtime Area", "difference"), ("Why is this governed?", "reasoning"), ("View Technical Evidence", "trust")):
            ttk.Button(actions,text=label,command=lambda selected=section: self._open_evidence_section(selected)).pack(side="left",padx=(0,8))
        advanced=ttk.Frame(frame); advanced.grid(row=2,column=0,columnspan=2,sticky="w",pady=(4,0))
        for label, section in (("Difference", "difference"), ("Reasoning", "reasoning"), ("Trust", "trust"), ("Journal", "journal")):
            ttk.Button(advanced,text=label,command=lambda selected=section: self._open_evidence_section(selected)).pack(side="left",padx=(0,8))
        note = ttk.Frame(frame); note.grid(row=3,column=0,columnspan=2,sticky="ew",pady=(10,0)); note.columnconfigure(0,weight=1)
        self._note_text=tk.StringVar(); ttk.Entry(note,textvariable=self._note_text).grid(row=0,column=0,sticky="ew")
        ttk.Button(note,text="Record Note",command=self._record_note).grid(row=0,column=1,padx=(8,0))
        self._evidence_text=tk.Text(frame,height=16,wrap="word",state="disabled",relief="flat"); self._evidence_text.grid(row=4,column=0,columnspan=2,sticky="nsew",pady=(12,0))
        if self._evidence_context.get().strip(): self._open_decision()

    def _open_evidence(self) -> None:
        self._open_decision()

    def _open_decision(self) -> None:
        context=self._evidence_context.get().strip()
        RipDesktop._trace_workspace("evidence-context-received", evidence_context=context)
        threading.Thread(target=lambda: self._events.put(("decision", self._decision_result(context))),daemon=True).start()

    def _open_evidence_section(self, section: str) -> None:
        context=self._evidence_context.get().strip()
        threading.Thread(target=lambda: self._events.put(("evidence-section", self._section_result(context, section))),daemon=True).start()

    def _record_note(self) -> None:
        context, text = self._evidence_context.get().strip(), self._note_text.get()
        threading.Thread(target=lambda: self._events.put(("note-recorded", self._note_result(context, text))),daemon=True).start()

    def _build_platform_page(self) -> None:
        self._question.configure(text="Is RIP healthy?")
        self._detail.configure(text="Platform presents existing verification results in operator language. It does not provision, configure, or repair the platform.")
        frame=ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        self._platform_list=tk.Listbox(frame,height=10,activestyle="none",relief="flat"); self._platform_list.grid(row=0,column=0,sticky="nsew")
        ttk.Button(frame,text="Verify Platform",command=self._verify_platform).grid(row=1,column=0,sticky="e",pady=(10,0))
        self._verify_platform()

    def _build_autonomy_page(self) -> None:
        self._question.configure(text="Autonomy & Budget")
        self._detail.configure(text="Supreme Decision Authority is exercised only by the authenticated human holder. Review and approval never occur automatically.")
        self._task_frame.grid_remove()
        frame=ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        self._pending_decision_card=ttk.LabelFrame(frame,text="PENDING CONSTITUTIONAL DECISION",padding=14); self._pending_decision_card.grid(row=0,column=0,columnspan=4,sticky="new"); self._pending_decision_card.columnconfigure(0,weight=1)
        self._autonomy_text=tk.Text(frame,height=7,wrap="word",state="normal",relief="flat"); self._autonomy_text.grid(row=1,column=0,columnspan=4,sticky="nsew",pady=(12,0))
        self._render_pending_decision_card()
        self._confirmation=tk.BooleanVar(value=False)
        self._render_autonomy()

    def _build_memory_page(self) -> None:
        frame=ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        ttk.Button(frame,text="Build Observed Inventory Edge Projection",command=self._seed_inventory_memory).grid(row=0,column=0,sticky="w")
        self._memory_knowledge=tk.Text(frame,height=20,wrap="word",state="normal",relief="flat"); self._memory_knowledge.grid(row=1,column=0,sticky="nsew",pady=(12,0))
        self._render_memory_knowledge()

    def _render_memory_knowledge(self) -> None:
        if not hasattr(self,"_memory_knowledge"): return
        records=MemoryStore().load("inventory-edge","inventory-edge")
        text="WHAT I KNOW\n\n" + ("No governed Inventory Edge memory is available." if not records else "\n\n".join(f"{item.statement}\nStatus: {item.status}\nConfidence: {item.confidence}\nEvidence: {len(item.supporting_evidence)}\nLast validation: {item.last_validated_at}\nWHY DO YOU KNOW THIS? " + "; ".join(item.source_records) for item in records))
        self._memory_knowledge.configure(state="normal"); self._memory_knowledge.delete("1.0",tk.END); self._memory_knowledge.insert("1.0",text); self._memory_knowledge.configure(state="disabled")

    def _seed_inventory_memory(self) -> None:
        try:
            memories=build_repository_memory()
            if not memories: self._memory_knowledge.configure(state="normal"); self._memory_knowledge.insert(tk.END,"\n\nEvidence unavailable: no retained Repository Memory profile exists."); self._memory_knowledge.configure(state="disabled"); return
            seed_observed_projection(store=MemoryStore(),organization_id="inventory-edge",repository_id="inventory-edge",repository_memory=memories[0]); self._render_memory_knowledge()
        except Exception as error:
            self._memory_knowledge.configure(state="normal"); self._memory_knowledge.insert(tk.END,f"\n\nMemory projection failed: {error}"); self._memory_knowledge.configure(state="disabled")

    def _render_pending_decision_card(self) -> None:
        for child in self._pending_decision_card.winfo_children(): child.destroy()
        published = storage_directory("State") / "sda-published-decision.json"
        if published.exists():
            ttk.Label(self._pending_decision_card,text="No pending constitutional decisions. The first SDA decision is active.").grid(row=0,column=0,sticky="w")
            ttk.Button(self._pending_decision_card,text="RETURN HOME",command=self._return_home_after_sda,style="Primary.TButton").grid(row=1,column=0,sticky="ew",pady=(10,0),ipady=6)
            return
        holder=AuthenticatedHuman.current_windows_user().identity
        draft=first_sda_decision_draft(holder)
        summary="Authorize bounded producer admission, Engineering Decision Authority, and initial autonomy-budget rules."
        ttk.Label(self._pending_decision_card,text=draft.title,style="Question.TLabel",wraplength=760).grid(row=0,column=0,sticky="w")
        ttk.Label(self._pending_decision_card,text=f"Decision ID: {draft.decision_id}\nStatus: Awaiting authenticated human decision\nSummary: {summary}",justify="left",wraplength=760).grid(row=1,column=0,sticky="w",pady=(6,10))
        if getattr(self, "_pending_sda_decision", None) is None:
            ttk.Button(self._pending_decision_card,text="REVIEW DECISION",command=self._review_sda_decision,style="Primary.TButton").grid(row=2,column=0,sticky="ew",ipady=6)
            ttk.Button(self._pending_decision_card,text="Bootstrap SDA",command=self._bootstrap_sda).grid(row=3,column=0,sticky="w",pady=(8,0))
        else:
            ttk.Checkbutton(self._pending_decision_card,text="I confirm this decision is prospective and immutable after publication.",variable=self._confirmation,command=self._refresh_approval).grid(row=2,column=0,sticky="w",pady=(4,8))
            actions=ttk.Frame(self._pending_decision_card); actions.grid(row=3,column=0,sticky="ew"); actions.columnconfigure(0,weight=1)
            self._approve_sda_button=ttk.Button(actions,text="APPROVE AND PUBLISH",command=self._approve_sda_decision,state="disabled",style="Primary.TButton"); self._approve_sda_button.grid(row=0,column=0,sticky="ew",ipady=6)
            ttk.Button(actions,text="Cancel",command=self._cancel_sda_review).grid(row=0,column=1,sticky="e",padx=(8,0))
            if not (storage_directory("State") / "sda-bootstrap.json").exists():
                ttk.Button(self._pending_decision_card,text="Bootstrap SDA before publication",command=self._bootstrap_sda).grid(row=4,column=0,sticky="w",pady=(8,0))

    def _render_autonomy(self, extra: str = "") -> None:
        if not hasattr(self, "_autonomy_text"): return
        self._autonomy_text.configure(state="normal"); self._autonomy_text.delete("1.0",tk.END)
        self._autonomy_text.insert("1.0", render_autonomy_status() + ("\n\n" + extra if extra else "")); self._autonomy_text.configure(state="disabled")
        if hasattr(self, "_pending_decision_card"): self._render_pending_decision_card()

    def _return_home_after_sda(self) -> None:
        self._home_loaded = False; self._home_overview = None
        self._show_page("Home")

    def _sda_workflow(self, *, bootstrap: bool = False):
        # Provisioning is called only from the explicitly confirmed bootstrap path.
        from .platform_provisioning import provision_trust_authority_context, load_trust_authority_context
        state = storage_directory("State")
        context = load_trust_authority_context() if (state / "sda-bootstrap.json").exists() or not bootstrap else provision_trust_authority_context()
        return SDAWorkflow(context, state)

    def _refresh_approval(self) -> None:
        reviewed = getattr(self, "_pending_sda_decision", None) is not None
        if hasattr(self, "_approve_sda_button"): self._approve_sda_button.configure(state="normal" if reviewed and self._confirmation.get() else "disabled")

    def _cancel_sda_review(self) -> None:
        self._pending_sda_decision = None; self._confirmation.set(False); self._refresh_approval()
        self._render_autonomy("Decision review cancelled. No decision was signed or published.")

    def _bootstrap_sda(self) -> None:
        if not messagebox.askyesno("Bootstrap Supreme Decision Authority", "This creates the one-time SDA trust anchor for your authenticated Windows identity and admits SDA decisions to the Journal. Continue?"): return
        try:
            holder=self._sda_workflow(bootstrap=True).bootstrap(human=AuthenticatedHuman.current_windows_user(), confirmed=True)
            self._render_autonomy(f"Bootstrap completed. Authenticated holder: {holder}. Review the pending decision before approving it.")
        except Exception as error: self._render_autonomy(f"Bootstrap was not completed: {error}")

    def _review_sda_decision(self) -> None:
        try:
            state = storage_directory("State") / "sda-bootstrap.json"
            if state.exists():
                workflow=self._sda_workflow(); holder, draft=workflow.status()
            else:
                holder=AuthenticatedHuman.current_windows_user().identity; draft=first_sda_decision_draft(holder)
            if not draft:
                self._render_autonomy("The first SDA decision is Active. View Journal Evidence from the retained receipt."); return
            self._pending_sda_decision=draft
            self._refresh_approval()
            self._render_autonomy("PENDING SDA DECISION\n\nDecision ID: " + draft.decision_id + "\nTitle: " + draft.title + "\nStatus: Awaiting authenticated human decision\nAuthenticated holder expected: " + holder + "\nEffective scope: " + json.dumps(draft.scope, sort_keys=True) + "\n\nWhat changes: " + draft.decision_text + "\n\nWhy: " + draft.reason + "\n\nNew authorities: Engineering Decision Authority is authorized, not implemented.\nLimits: delegation is bounded and revocable; initial autonomy remains deterministic, read-only, and zero-network.\nHistorical evidence: unchanged. This decision is prospective only.\nAfter publication: the authorized work becomes active for implementation; it does not make Producer Policy v2 or Engineering Decision Capture operational.\n\nTechnical details\nSchemas: " + draft.schema + "; rip.authority-charter.v1; rip.execution-budget.v1\nProducer: " + draft.producer_identity + " version " + draft.producer_version + "\nAuthorized changes: " + "; ".join(draft.authorized_changes) + "\nCompatibility rules: " + "; ".join(draft.compatibility_rules) + "\nDelegation terms: " + json.dumps(draft.delegation_terms, sort_keys=True) + "\nReferenced artifacts: " + "; ".join(draft.referenced_artifacts))
        except Exception as error: self._render_autonomy(f"Decision review is unavailable: {error}")

    def _approve_sda_decision(self) -> None:
        decision=getattr(self,"_pending_sda_decision",None)
        if decision is None or not self._confirmation.get():
            self._render_autonomy("Approval refused: review the decision and explicitly confirm prospective, immutable publication."); return
        if not messagebox.askyesno("Approve and Publish SDA Decision", "Final confirmation\n\n" + decision.title + "\n\nEffect: this prospective decision will be signed and immutably published to the Journal. Continue?"):
            self._render_autonomy("Approval cancelled. No decision was signed or published."); return
        try:
            receipt=self._sda_workflow().approve_and_publish(human=AuthenticatedHuman.current_windows_user(), decision=decision, confirmed=True)
            self._approve_sda_button.configure(state="disabled")
            self._home_loaded = False; self._home_overview = None
            self._render_autonomy("SUPREME DECISION PUBLISHED\n\nDecision: " + receipt["title"] + "\nDecision ID: " + receipt["decision_id"] + "\nAuthenticated holder: " + receipt["holder_identity"] + "\nEffective time: " + receipt["effective_at"] + "\nJournal publication: " + receipt["receipt"] + "\nStatus: Active\nAuthorized changes: Producer Admission Certificate v2 work, Engineering Decision Authority charter, and initial autonomy limits are authorized.\nHistorical evidence: Unchanged\n\nAvailable views: Published Decision; Journal Evidence; Active Authorities; Autonomy Policy.")
        except Exception as error: self._render_autonomy(f"Decision was not published: {error}")

    def _build_repository_memory_page(self) -> None:
        self._question.configure(text="Repository Memory")
        self._detail.configure(text="Deterministic repository knowledge derived only from retained observations. Evidence remains the source of truth.")
        frame = ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        ttk.Button(frame,text="Refresh Repository Memory",command=self._load_repository_memory).grid(row=0,column=0,sticky="e")
        self._memory_text=tk.Text(frame,height=22,wrap="word",state="disabled",relief="flat"); self._memory_text.grid(row=1,column=0,sticky="nsew",pady=(12,0))
        self._load_repository_memory()

    def _load_repository_memory(self) -> None:
        threading.Thread(target=lambda: self._events.put(("repository-memory", self._memory_result())),daemon=True).start()

    def _build_repository_intelligence_page(self) -> None:
        frame = ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        self._intelligence_question = tk.StringVar(value="What constitutional capabilities exist?")
        ttk.Entry(frame,textvariable=self._intelligence_question).grid(row=0,column=0,sticky="ew")
        ttk.Button(frame,text="Ask Repository",command=self._ask_repository).grid(row=0,column=1,padx=(8,0))
        examples = ttk.Frame(frame); examples.grid(row=1,column=0,columnspan=2,sticky="w",pady=(10,0))
        for question in ("What does this repository do?", "What constitutional capabilities exist?", "What runtime paths exist?", "What changed since the last observation?", "What has RIP never observed?"):
            ttk.Button(examples,text=question,command=lambda selected=question: self._ask_repository(selected)).pack(side="left",padx=(0,6))
        self._intelligence_text=tk.Text(frame,height=18,wrap="word",state="disabled",relief="flat"); self._intelligence_text.grid(row=2,column=0,columnspan=2,sticky="nsew",pady=(12,0))
        self._ask_repository()

    def _build_architect_page(self) -> None:
        frame=ttk.Frame(self._content); frame.grid(row=2,column=0,sticky="nsew"); frame.columnconfigure(0,weight=1)
        ttk.Button(frame,text="Refresh Architect Guidance",command=self._load_architect).grid(row=0,column=0,sticky="e")
        self._architect_text=tk.Text(frame,height=22,wrap="word",state="disabled",relief="flat"); self._architect_text.grid(row=1,column=0,sticky="nsew",pady=(12,0)); self._load_architect()

    def _load_architect(self) -> None:
        threading.Thread(target=lambda:self._events.put(("architect", self._architect_result())),daemon=True).start()

    @staticmethod
    def _architect_result():
        try:
            memory=build_repository_memory()
            return render_architect(memory[0]) if memory else "Not yet observed."
        except Exception as error:
            return f"Operation failed: Architect guidance could not be loaded ({type(error).__name__})."

    def _ask_repository(self, question: str | None = None) -> None:
        selected = question or self._intelligence_question.get()
        if question is not None: self._intelligence_question.set(question)
        threading.Thread(target=lambda: self._events.put(("repository-intelligence", self._intelligence_result(selected))),daemon=True).start()

    @staticmethod
    def _intelligence_result(question: str):
        try:
            memory = build_repository_memory()
            if not memory: return "Answer\nNot yet observed.\n\nEvidence\nNo retained Repository Memory profile is available.\n\nConfidence\nUnknown"
            return render_answer(answer_question(memory[0], question))
        except Exception as error:
            reference = uuid.uuid4().hex; directory = storage_directory("Diagnostics"); directory.mkdir(parents=True, exist_ok=True)
            (directory / f"desktop-repository-intelligence-{reference}.json").write_text(json.dumps({"operation":"repository-intelligence", "exception_type":type(error).__name__, "message":str(error), "traceback":traceback.format_exc()}),encoding="utf-8")
            return f"Operation failed: Repository Intelligence could not answer (reference {reference})."

    @staticmethod
    def _memory_result():
        try:
            return build_repository_memory()
        except Exception as error:
            reference = uuid.uuid4().hex
            directory = storage_directory("Diagnostics"); directory.mkdir(parents=True, exist_ok=True)
            (directory / f"desktop-repository-memory-{reference}.json").write_text(json.dumps({"operation":"repository-memory", "exception_type":type(error).__name__, "message":str(error), "traceback":traceback.format_exc()}),encoding="utf-8")
            return f"Operation failed: Repository Memory could not be loaded (reference {reference})."

    def _verify_platform(self) -> None:
        self._tasks.delete(0,tk.END); self._tasks.insert(tk.END,"Verifying platform health…")
        threading.Thread(target=lambda: self._events.put(("platform",verify_platform())),daemon=True).start()

    @staticmethod
    def _evidence_result(context: str):
        try:
            return open_evidence(context)
        except ValueError as error:
            return str(error) if str(error).startswith("Evidence unavailable:") else f"Evidence unavailable: {error}"
        except Exception as error:
            reference = uuid.uuid4().hex
            directory = storage_directory("Diagnostics"); directory.mkdir(parents=True, exist_ok=True)
            (directory / f"desktop-open-evidence-{reference}.json").write_text(json.dumps({"operation": "open-evidence", "exception_type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}), encoding="utf-8")
            return f"Operation failed: evidence could not be opened (reference {reference})."

    @staticmethod
    def _decision_result(context: str):
        result = RipDesktop._evidence_result(context)
        rendered = render_workspace(result) if isinstance(result, EvidenceView) else result
        RipDesktop._trace_workspace("decision-summary-produced", evidence_context=context, result_type=type(rendered).__name__, rendered_view=str(rendered))
        return rendered

    @staticmethod
    def _section_result(context: str, section: str):
        try:
            return review_evidence(context, section)
        except ValueError as error:
            return str(error) if str(error).startswith("Evidence unavailable:") else f"Evidence unavailable: {error}"
        except Exception as error:
            reference = uuid.uuid4().hex
            directory = storage_directory("Diagnostics"); directory.mkdir(parents=True, exist_ok=True)
            (directory / f"desktop-evidence-section-{reference}.json").write_text(json.dumps({"operation": "open-evidence-section", "exception_type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}), encoding="utf-8")
            return f"Operation failed: evidence could not be opened (reference {reference})."

    @staticmethod
    def _note_result(context: str, text: str):
        try:
            return append_investigation_note(context, text)
        except ValueError as error:
            return str(error) if str(error).startswith("Evidence unavailable:") else f"Evidence unavailable: {error}"
        except Exception as error:
            reference = uuid.uuid4().hex
            directory = storage_directory("Diagnostics"); directory.mkdir(parents=True, exist_ok=True)
            (directory / f"desktop-investigation-note-{reference}.json").write_text(json.dumps({"operation": "record-investigation-note", "exception_type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}), encoding="utf-8")
            return f"Operation failed: note could not be recorded (reference {reference})."

    @staticmethod
    def _resume_completion_text(result: object) -> str:
        if isinstance(result, dict) and result.get("state") == "paused-affected-scope" and result.get("trust_action") == "pause-affected-scope":
            return "Run completed\n\nDecision:\nPaused — affected scope\n\nAffected paths:\n1"
        return "Run completed. Open Decision to review the retained result."

    def _load_history_async(self) -> None:
        query=self._history_query.get() if hasattr(self,"_history_query") else ""
        threading.Thread(target=lambda: self._events.put(("history",load_history(query))),daemon=True).start()

    def _load_runs_async(self) -> None:
        threading.Thread(target=lambda: self._events.put(("runs", load_runs())),daemon=True).start()
        self.after(5000, lambda: self._load_runs_async() if self._page.get()=="Runs" else None)

    def _open_run(self) -> None:
        selected = self._selected_item(self._runs_list, getattr(self, "_runs", ()))
        if selected is None:
            self._runs_detail.set("Select a run to view its retained operational summary in this workspace.")
            return
        self._evidence_context.set(selected.name)
        self._show_page("Investigate")
        self._open_evidence()

    @staticmethod
    def _selected_item(widget, items):
        selection = widget.curselection()
        return items[selection[0]] if selection and selection[0] < len(items) else None

    def _show_run_summary(self, _event=None) -> None:
        selected = self._selected_item(self._runs_list, getattr(self, "_runs", ()))
        if selected is not None:
            self._runs_detail.set(selected.detail)

    def _show_history_summary(self, _event=None) -> None:
        selected = self._selected_item(self._history_list, getattr(self, "_history", ()))
        if selected is not None:
            self._history_detail.set(selected.detail)

    def _open_history_evidence(self, _event=None) -> None:
        selected = self._selected_item(self._history_list, getattr(self, "_history", ()))
        if selected is None or selected.run == "-":
            self._history_detail.set("Select a retained run event before opening evidence.")
            return
        self._evidence_context.set(selected.run)
        self._show_page("Investigate")
        self._open_evidence()

    def _start_observation(self) -> None:
        if not self._observe_organization.get().strip() or not self._observe_source.get().strip():
            self._observe_status.set("An organization and source are required before observation can begin.")
            return
        if getattr(self, "_observe_mode", "observe") == "new" and not messagebox.askyesno("Start new observation", "A retained run exists. Start a new observation without changing its evidence?", parent=self):
            return
        self._observe_button.configure(state="disabled")
        self._observe_status.set("Observation started. RIP is reading the source without modifying it.")
        self._tasks.delete(0, tk.END); self._tasks.insert("end", "Observation in progress…")
        threading.Thread(target=self._observe_worker, args=(self._observe_source.get().strip(), self._observe_organization.get().strip()), daemon=True).start()

    @staticmethod
    def _normalized_windows_path(value: str) -> str:
        return ntpath.normcase(ntpath.normpath(value.strip())) if value.strip() else ""

    def _schedule_observe_refresh(self, *_args) -> None:
        if self._observe_refresh_after is not None:
            self.after_cancel(self._observe_refresh_after)
        self._observe_refresh_after = self.after(250, self._refresh_observe_action)

    def _refresh_observe_action(self, _event=None) -> None:
        self._observe_refresh_after = None
        organization = self._observe_organization.get().strip()
        source = self._normalized_windows_path(self._observe_source.get())
        matching = [run for run in load_runs() if run.name.startswith(organization + " /") and self._normalized_windows_path(run.source) == source]
        run = matching[0] if matching else None
        self._observe_mode = "observe"
        if run is None:
            self._observe_button.configure(text="Observe", command=self._start_observation); return
        if run.status == "Attention required":
            self._evidence_context.set(run.run_id)
            self._observe_status.set("Attention required. Last completed stage: Integrity Verification. Reason: Platform provisioning required.")
            self._observe_mode = "provision"
            self._observe_button.configure(text="Provision Platform", command=self._provision_platform); return
        if run.lifecycle_state == "observed":
            self._observe_mode = "new"; self._observe_button.configure(text="New Observation", command=self._start_observation); return
        self._observe_button.configure(text="Open Run", command=self._open_run)

    def _provision_platform(self) -> None:
        self._observe_button.configure(state="disabled")
        threading.Thread(target=self._provision_worker, daemon=True).start()

    def _provision_worker(self) -> None:
        try:
            provision_trust_authority_context()
            self._events.put(("platform-provisioned", "Platform provisioned. Resume Run is now available; RIP did not resume it automatically."))
        except Exception as error:
            self._events.put(("observe-error", f"Platform provisioning stopped: {type(error).__name__}: {error}"))

    def _resume_run(self) -> None:
        run_id = self._evidence_context.get()
        threading.Thread(target=self._resume_worker, args=(run_id,), daemon=True).start()

    def _resume_worker(self, run_id: str) -> None:
        try:
            runs = {run.run_id: run for run in load_runs()}
            run = runs[run_id]
            workspace = create_organization_workspace(r"C:\RIP\Workspace", organization_id=self._observe_organization.get().strip(), display_name=self._observe_organization.get().strip(), repository_path=run.source)
            context = __import__("rip.onboarding.resume_orchestration", fromlist=["_load_context"])._load_context(workspace.workspace_path, workspace.organization_id, run_id)
            result = continue_retained_post_integrity_run(context)
            self._events.put(("resume-complete", result))
        except Exception as error:
            self._events.put(("observe-error", f"Resume Run stopped: {type(error).__name__}: {error}"))

    def _observe_worker(self, source: str, organization: str) -> None:
        try:
            workspace = create_organization_workspace(r"C:\RIP\Workspace", organization_id=organization, display_name=organization, repository_path=source)
            context = restart_onboarding_run(workspace, repository_path=source, reasoning_capability=recommend_reasoning_capability())
            result = observe_organization(context, progress_callback=lambda event: self._events.put(("observe-progress", event.message)))
            self._events.put(("observe-complete", result))
        except Exception as error:
            self._events.put(("observe-error", f"Observation stopped: {type(error).__name__}: {error}"))

    def _refresh_home(self) -> None:
        try:
            self._events.put(("home", refresh_home()))
        except Exception:
            self._events.put(("home-error", "Platform readiness could not be established from retained evidence."))

    def _open_work_item(self, item: WorkItem) -> None:
        before = self._evidence_context.get().strip()
        RipDesktop._trace_workspace("home-open-workspace-callback", callback="_open_work_item", work_item={"repository": item.repository, "run_id": item.run_id, "evidence_context": item.evidence_context, "primary_action": item.primary_action}, active_context_before=before)
        if item.primary_action == "REVIEW CONSTITUTIONAL DECISION":
            self._show_page("Autonomy & Budget")
            self._review_sda_decision()
            return
        if item.primary_action == "Provision Platform":
            threading.Thread(target=self._provision_worker, daemon=True).start()
            return
        if item.primary_action == "Observe Progress":
            self._show_page("Runs")
            return
        self._evidence_context.set(item.evidence_context or item.run_id)
        RipDesktop._trace_workspace("active-context-set", active_context_before=before, active_context_after=self._evidence_context.get().strip())
        self._show_page("Investigate")

    def _render_work_queue(self, items: tuple[WorkItem, ...]) -> None:
        frame = ttk.Frame(self._content); frame.grid(row=2, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        primary = resolve_primary_action(items)
        panel = ttk.LabelFrame(frame, text="YOUR NEXT ACTION", padding=16); panel.grid(row=0, column=0, sticky="ew", pady=(0, 18)); panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text=primary.summary, style="Question.TLabel", wraplength=760).grid(row=0, column=0, sticky="w")
        ttk.Label(panel, text="Why this matters: " + primary.reason + ("\nEstimated time: " + primary.estimated_time if primary.estimated_time else ""), justify="left", wraplength=760).grid(row=1, column=0, sticky="w", pady=(8, 12))
        if primary.work_item is not None:
            button = ttk.Button(panel, text=primary.button_label, command=lambda selected=primary.work_item: self._open_work_item(selected), style="Primary.TButton")
            button.grid(row=2, column=0, sticky="ew", ipady=8)
        if primary.has_more_work:
            ttk.Button(panel, text="View Full Work Queue", command=lambda: self._show_full_work_queue(items)).grid(row=3, column=0, sticky="w", pady=(10, 0))

    def _show_full_work_queue(self, items: tuple[WorkItem, ...]) -> None:
        for child in self._content.winfo_children():
            if child not in {self._question, self._detail, self._task_frame}: child.destroy()
        self._question.configure(text="Full Work Queue")
        self._detail.configure(text="All retained operator work, ordered by its existing recommendation classification.")
        self._render_full_work_queue(items)

    def _render_full_work_queue(self, items: tuple[WorkItem, ...], *, parent=None, row: int = 0) -> None:
        frame = parent or ttk.Frame(self._content)
        if parent is None: frame.grid(row=2, column=0, sticky="nsew")
        groups = (("Needs Attention", {"Critical", "Needs Attention", "In Progress"}),
                  ("Recently Completed", {"Completed Today"}), ("Healthy", {"Healthy"}))
        for offset, (title, classifications) in enumerate(groups):
            ttk.Label(frame, text=title, style="Question.TLabel").grid(row=row + offset * 2, column=0, sticky="w", pady=(0, 6))
            group = tuple(item for item in items if item.classification in classifications)
            if not group:
                ttk.Label(frame, text="No retained work in this category.").grid(row=row + offset * 2 + 1, column=0, sticky="w", pady=(0, 14))
                continue
            cards = ttk.Frame(frame); cards.grid(row=row + offset * 2 + 1, column=0, sticky="ew", pady=(0, 14)); cards.columnconfigure(0, weight=1)
            for index, item in enumerate(group):
                card = ttk.LabelFrame(cards, text=f"{item.classification} — {item.run_id}", padding=10); card.grid(row=index, column=0, sticky="ew", pady=(0, 8)); card.columnconfigure(0, weight=1)
                ttk.Label(card, text=f"Repository: {item.repository}\nCurrent constitutional state: {item.constitutional_state}\n{item.explanation}\nRecommended action: {item.recommendation}", justify="left", wraplength=800).grid(row=0, column=0, sticky="w")
                ttk.Button(card, text=item.primary_action, command=lambda selected=item: self._open_work_item(selected)).grid(row=0, column=1, sticky="e", padx=(12, 0))

    def notify(self, message: str) -> None:
        self._events.put(("notification", message))

    def _poll(self) -> None:
        try:
            while True:
                kind, value = self._events.get_nowait()
                if kind == "notification": self._notification.set(value)
                elif kind == "home" and isinstance(value, HomeOverview):
                    self._home_loaded = True
                    self._home_overview = value
                    self._question.configure(text="Operator Work Queue")
                    self._detail.configure(text="What requires attention, what completed, and the next recommended operator action.")
                    self._render_work_queue(value.work_items)
                    self._tasks.delete(0, tk.END); self._tasks.insert("end", "No active background tasks")
                    self._status.set(value.health); self._notification.set("Work queue refreshed")
                elif kind == "home-error":
                    self._tasks.delete(0, tk.END); self._tasks.insert("end", "Platform readiness requires attention")
                    self._status.set("Attention required"); self._notification.set(value)
                elif kind == "observe-progress":
                    self._observe_status.set(str(value)); self._tasks.delete(0, tk.END); self._tasks.insert("end", str(value))
                elif kind == "observe-complete":
                    self._observe_status.set("Observation completed. Evidence is available for review.")
                    self._tasks.delete(0, tk.END); self._tasks.insert("end", "No active background tasks")
                    self._notification.set("Observation completed")
                    if hasattr(self, "_observe_button"): self._observe_button.configure(state="normal", text="Resume Observation")
                elif kind == "observe-error":
                    if hasattr(self, "_observe_status"): self._observe_status.set(str(value))
                    self._tasks.delete(0, tk.END); self._tasks.insert("end", "Observation requires attention")
                    self._notification.set("Observation requires attention")
                    if hasattr(self, "_observe_button"): self._observe_button.configure(state="normal")
                elif kind == "platform-provisioned":
                    if hasattr(self, "_observe_status"): self._observe_status.set(str(value))
                    if hasattr(self, "_observe_button"): self._observe_button.configure(state="normal", text="Resume Run", command=self._resume_run)
                    self._notification.set("Platform provisioned; continuation awaits operator action")
                elif kind == "resume-complete":
                    run_id = str(value.get("run_id", self._evidence_context.get())) if isinstance(value, dict) else self._evidence_context.get()
                    self._evidence_context.set(run_id)
                    self._observe_status.set(self._resume_completion_text(value))
                    self._observe_button.configure(state="normal", text="Open Decision", command=self._open_decision)
                    self._notification.set("Retained continuation completed")
                elif kind == "runs" and self._page.get() == "Runs" and hasattr(self, "_runs_list"):
                    self._runs = tuple(value)
                    self._runs_list.delete(0, tk.END)
                    for run in value:
                        self._runs_list.insert(tk.END, run_display_text(run))
                    if not value: self._runs_list.insert(tk.END, "No known runs")
                    self._runs_detail.set(f"Last updated automatically. {len(value)} known run(s).")
                elif kind == "history" and self._page.get() == "History" and hasattr(self,"_history_list"):
                    self._history = tuple(value)
                    self._history_list.delete(0,tk.END)
                    for event in value: self._history_list.insert(tk.END,f"{event.timestamp}  —  {event.title}  —  {event.status}  —  Evidence {event.evidence}")
                    if not value: self._history_list.insert(tk.END,"No matching history")
                    self._history_detail.set(f"{len(value)} event(s) available. Select an event to review its retained evidence summary.")
                elif kind == "evidence" and self._page.get() == "Investigate" and hasattr(self,"_evidence_text"):
                    self._evidence_text.configure(state="normal"); self._evidence_text.delete("1.0","end")
                    if isinstance(value,EvidenceView):
                        self._evidence_text.insert("1.0", render_evidence(value))
                        self._notification.set("Evidence opened")
                    else:
                        self._evidence_text.insert("1.0", str(value))
                        self._notification.set("Evidence unavailable")
                    self._evidence_text.configure(state="disabled")
                elif kind in {"decision", "evidence-section"} and self._page.get() == "Investigate" and hasattr(self,"_evidence_text"):
                    self._evidence_text.configure(state="normal"); self._evidence_text.delete("1.0","end")
                    self._evidence_text.insert("1.0", str(value)); self._evidence_text.configure(state="disabled")
                    self._notification.set("Decision opened" if kind == "decision" else "Evidence opened")
                    if kind == "decision": RipDesktop._trace_workspace("decision-summary-rendered", active_investigation_context=self._evidence_context.get().strip(), rendered_view=str(value))
                elif kind == "note-recorded" and self._page.get() == "Investigate":
                    if isinstance(value, dict):
                        if hasattr(self, "_note_text"): self._note_text.set("")
                        self._notification.set("Investigation note retained")
                        self._open_decision()
                    elif hasattr(self, "_evidence_text"):
                        self._evidence_text.configure(state="normal"); self._evidence_text.delete("1.0", "end"); self._evidence_text.insert("1.0", str(value)); self._evidence_text.configure(state="disabled")
                        self._notification.set("Note not recorded")
                elif kind == "repository-memory" and self._page.get() == "Repository Memory" and hasattr(self, "_memory_text"):
                    self._memory_text.configure(state="normal"); self._memory_text.delete("1.0", "end")
                    if isinstance(value, tuple):
                        self._memory_text.insert("1.0", "\n\n".join(render_repository_memory(item) for item in value) if value else "Not yet observed.")
                        self._notification.set("Repository Memory refreshed")
                    else:
                        self._memory_text.insert("1.0", str(value)); self._notification.set("Repository Memory unavailable")
                    self._memory_text.configure(state="disabled")
                elif kind == "repository-intelligence" and self._page.get() == "Ask Repository" and hasattr(self, "_intelligence_text"):
                    self._intelligence_text.configure(state="normal"); self._intelligence_text.delete("1.0", "end"); self._intelligence_text.insert("1.0", str(value)); self._intelligence_text.configure(state="disabled")
                    self._notification.set("Repository Intelligence answered")
                elif kind == "architect" and self._page.get() == "Architect" and hasattr(self,"_architect_text"):
                    self._architect_text.configure(state="normal"); self._architect_text.delete("1.0","end"); self._architect_text.insert("1.0",str(value)); self._architect_text.configure(state="disabled"); self._notification.set("Architect guidance refreshed")
                elif kind == "platform" and self._page.get()=="Platform" and hasattr(self,"_platform_list"):
                    self._platform_list.delete(0,tk.END)
                    for name,status,detail in value.components: self._platform_list.insert(tk.END,f"{name}  —  {status}  —  {detail}")
                    overall="Healthy" if all(status=="Healthy" for _,status,_ in value.components) else "Attention Required"
                    self._status.set(overall); self._notification.set("Platform verification completed")
                    self._tasks.delete(0,tk.END); self._tasks.insert(tk.END,"No active background tasks")
        except queue.Empty:
            pass
        self.after(100, self._poll)


def main() -> int:
    reason = elevation_failure_reason()
    if reason:
        ctypes.windll.user32.MessageBoxW(None, reason, "RIP requires Administrator elevation", 0x10)
        return 1
    instance = _SingleInstance()
    if instance.already_running:
        window = ctypes.windll.user32.FindWindowW(None, "RIP")
        if window:
            ctypes.windll.user32.ShowWindow(window, 9)
            ctypes.windll.user32.SetForegroundWindow(window)
        instance.close()
        return 0
    try:
        app = RipDesktop(); app.mainloop()
    finally:
        instance.close()
    return 0
