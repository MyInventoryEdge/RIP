from pathlib import Path
import tempfile
import unittest

from rip.voice.manager import VoiceManager


class Provider:
    def list_voices(self): return ("alloy",)
    def ready(self): return True
    def synthesize(self, config, text, output): Path(output).write_bytes(b"wav")


class VoicePlaybackTests(unittest.TestCase):
    def test_playback_is_invoked_and_audio_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            played = []
            manager = VoiceManager(Path(temp) / "config.json", Provider(), lambda path: played.append(path))
            output = Path(temp) / "voice.wav"
            result = manager.speak("hello", output_path=output)
            self.assertTrue(result.success); self.assertTrue(result.playback); self.assertEqual([output], played); self.assertTrue(output.exists())

    def test_playback_failure_preserves_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "voice.wav"
            manager = VoiceManager(Path(temp) / "config.json", Provider(), lambda path: (_ for _ in ()).throw(OSError("blocked")))
            result = manager.speak("hello", output_path=output)
            self.assertFalse(result.success); self.assertEqual("playback", result.category); self.assertTrue(output.exists())
