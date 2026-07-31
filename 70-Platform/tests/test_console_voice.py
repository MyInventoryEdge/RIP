from __future__ import annotations

import queue
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

from rip.console.app import RipConsole
from rip.voice import VoiceState


class _VoiceManager:
    def __init__(self) -> None:
        self.recording_path: Path | None = None

    def listen_once(self, output_path: Path) -> str:
        self.recording_path = output_path
        output_path.write_bytes(b"wav")
        return "What changed in the repository?"

    state = VoiceState.IDLE


class _SpeechResult:
    success = True
    playback = True


class _SpeechManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def speak(self, text: str, *, play: bool) -> _SpeechResult:
        self.calls.append((text, play))
        return _SpeechResult()


class ConsoleVoiceWorkerTests(unittest.TestCase):
    def test_talk_activation_sets_busy_and_starts_one_worker(self) -> None:
        console = object.__new__(RipConsole)
        console._busy = False
        console._voice = _VoiceManager()
        console._set_busy = Mock()
        console._set_status = Mock()

        with patch("rip.console.app.threading.Thread") as thread:
            console.talk()

        console._set_busy.assert_called_once_with(True)
        console._set_status.assert_not_called()
        thread.assert_called_once_with(target=console._run_voice_input, daemon=True)
        thread.return_value.start.assert_called_once_with()

    def test_talk_is_ignored_while_busy(self) -> None:
        console = object.__new__(RipConsole)
        console._busy = True
        console._voice = _VoiceManager()
        console._set_busy = Mock()

        with patch("rip.console.app.threading.Thread") as thread:
            console.talk()

        console._set_busy.assert_not_called()
        thread.assert_not_called()

    def test_f4_shortcut_calls_talk(self) -> None:
        console = object.__new__(RipConsole)
        console.talk = Mock()

        self.assertEqual(console._on_talk_shortcut(SimpleNamespace()), "break")
        console.talk.assert_called_once_with()

    def test_voice_input_uses_manager_and_removes_temporary_recording(self) -> None:
        console = object.__new__(RipConsole)
        manager = _VoiceManager()
        console._voice = manager
        console._events = queue.Queue()

        with tempfile.TemporaryDirectory() as directory:
            recording_path = Path(directory) / "voice-input.wav"
            with patch("rip.console.app.tempfile.mkstemp", return_value=(42, str(recording_path))), patch(
                "rip.console.app.os.close"
            ):
                console._run_voice_input()

            self.assertEqual(console._events.get_nowait(), ("voice_input", "What changed in the repository?"))
            self.assertEqual(manager.recording_path, recording_path)
            self.assertFalse(recording_path.exists())

    def test_voice_input_reports_a_generic_error(self) -> None:
        console = object.__new__(RipConsole)
        console._voice = object()
        console._events = queue.Queue()

        with tempfile.TemporaryDirectory() as directory:
            recording_path = Path(directory) / "voice-input.wav"
            with patch("rip.console.app.tempfile.mkstemp", return_value=(42, str(recording_path))), patch(
                "rip.console.app.os.close"
            ):
                console._run_voice_input()

            kind, message = console._events.get_nowait()
            self.assertEqual(kind, "voice_error")
            self.assertTrue(message)

    def test_recognized_text_is_submitted_through_send_question(self) -> None:
        console = object.__new__(RipConsole)
        console._events = queue.Queue()
        console._events.put(("voice_input", "Please summarize the repository."))
        console._set_busy = Mock()
        console._set_status = Mock()
        console.question = Mock()
        console.send_question = Mock()
        console.after = Mock()

        console._poll_events()

        console._set_busy.assert_called_once_with(False)
        console.question.insert.assert_called_once_with("1.0", "Please summarize the repository.")
        console.send_question.assert_called_once_with()

    def test_speech_uses_voice_manager_and_reports_completion(self) -> None:
        console = object.__new__(RipConsole)
        manager = _SpeechManager()
        console._voice = manager
        console._events = queue.Queue()

        console._speak("A grounded answer")

        self.assertEqual(manager.calls, [("A grounded answer", True)])
        self.assertEqual(console._events.get_nowait(), ("voice_complete", None))

    def test_mute_only_changes_playback_preference(self) -> None:
        console = object.__new__(RipConsole)
        console._muted = False
        console.mute_button = Mock()
        console._set_status = Mock()

        console.toggle_mute()

        self.assertTrue(console._muted)
        console.mute_button.configure.assert_called_once_with(text="Unmute")
        console._set_status.assert_called_once_with("Muted")


if __name__ == "__main__":
    unittest.main()
