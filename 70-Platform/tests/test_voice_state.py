from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from rip.voice import VoiceManager, VoiceState


class Provider:
    def list_voices(self): return ("alloy",)
    def ready(self): return True
    def synthesize(self, config, text, output): Path(output).write_bytes(b"wav")


class VoiceStateTests(unittest.TestCase):
    def test_listen_transitions_and_populates_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = VoiceManager(Path(directory) / "config.json", Provider(), lambda path: None)
            manager.record = lambda output_path, **_: SimpleNamespace(output_path=Path(output_path), duration_seconds=1.25)
            manager.transcribe = lambda *_args, **_kwargs: "recognized text"
            states = []

            self.assertEqual(manager.listen_once(Path(directory) / "input.wav", state_callback=states.append), "recognized text")

            self.assertEqual(states, [VoiceState.LISTENING, VoiceState.TRANSCRIPT_FINALIZING, VoiceState.TRANSCRIBING])
            self.assertEqual(manager.timeline["recording_seconds"], 1.25)
            self.assertGreaterEqual(manager.timeline["total_seconds"], 0)

    def test_speech_transitions_return_to_idle_with_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = VoiceManager(Path(directory) / "config.json", Provider(), lambda path: None)
            states = []
            result = manager.speak("answer", output_path=Path(directory) / "answer.wav", state_callback=states.append)

            self.assertTrue(result.success)
            self.assertEqual(states, [VoiceState.SYNTHESIZING, VoiceState.PLAYING, VoiceState.IDLE])
            self.assertEqual(manager.state, VoiceState.IDLE)
            self.assertIsNotNone(result.synthesis_seconds)
            self.assertIsNotNone(result.playback_seconds)

    def test_manual_stop_only_applies_while_listening(self) -> None:
        manager = VoiceManager(provider=Provider())
        self.assertFalse(manager.request_stop())
        manager._state = VoiceState.LISTENING
        import threading
        manager._stop_event = threading.Event()
        self.assertTrue(manager.request_stop())
        self.assertTrue(manager._stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
