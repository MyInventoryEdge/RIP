from __future__ import annotations

import os
import queue
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..observation import find_repository_root
from ..reasoning import ReasoningResult, ask_repository
from ..voice import VoiceManager, VoiceState


@dataclass(frozen=True, slots=True)
class ConsoleResponse:
    answer: str
    details: str


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

        evidence = ttk.LabelFrame(controls, text="Primary Evidence", padding=(6, 4))
        evidence.grid(row=2, column=0, columnspan=7, sticky="ew", pady=(8, 0))
        evidence.columnconfigure(0, weight=1)
        self.evidence_list = tk.Listbox(evidence, height=3)
        self.evidence_list.grid(row=0, column=0, rowspan=2, sticky="ew")
        ttk.Button(evidence, text="Add Files", command=self.add_primary_evidence).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(evidence, text="Remove", command=self.remove_primary_evidence).grid(row=1, column=1, padx=(8, 0))
        ttk.Button(evidence, text="Clear", command=self.clear_primary_evidence).grid(row=0, column=2, rowspan=2, padx=(8, 0))

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

    def remove_primary_evidence(self) -> None:
        for index in reversed(self.evidence_list.curselection()): self._primary_evidence.pop(index)
        self._refresh_primary_evidence()

    def clear_primary_evidence(self) -> None:
        self._primary_evidence.clear(); self._refresh_primary_evidence()

    def _refresh_primary_evidence(self) -> None:
        self.evidence_list.delete(0, tk.END)
        for path in self._primary_evidence: self.evidence_list.insert(tk.END, path)

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

        worker = threading.Thread(target=self._run_reasoning, args=(question, tuple(self._primary_evidence)), daemon=True)
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

    def _run_reasoning(self, question: str, primary_paths: tuple[str, ...] = ()) -> None:
        started = time.perf_counter()
        try:
            result = ask_repository(
                question,
                primary_paths=list(primary_paths),
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


def main() -> int:
    app = RipConsole()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
