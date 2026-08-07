from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from ..paths import voice_configuration_path

VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse", "marin", "cedar")
TEST_PHRASE = "Hello. I am RIP. My voice interface is active."
LOGGER = logging.getLogger(__name__)


class VoiceState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIPT_FINALIZING = "TRANSCRIPT_FINALIZING"
    TRANSCRIBING = "TRANSCRIBING"
    REASONING = "REASONING"
    SYNTHESIZING = "SYNTHESIZING"
    PLAYING = "PLAYING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool = True
    provider: str = "openai"
    model: str = "gpt-4o-mini-tts"
    voice: str = "alloy"
    speed: float = 1.0
    instructions: str = ""
    audio_format: str = "wav"
    playback_enabled: bool = True
    microphone_device: int | None = None
    transcription_model: str = "gpt-4o-mini-transcribe"
    maximum_recording_seconds: float = 60
    minimum_speech_seconds: float = 0.5
    silence_timeout_seconds: float = 1.5
    silence_threshold: float = 0.015
    show_timing: bool = True
    auto_stop_enabled: bool = True


@dataclass(frozen=True)
class VoiceResult:
    success: bool
    provider: str
    model: str
    voice: str
    output_path: str | None = None
    playback: bool = False
    category: str | None = None
    message: str = ""
    recording_seconds: float | None = None
    transcription_seconds: float | None = None
    reasoning_seconds: float | None = None
    synthesis_seconds: float | None = None
    playback_seconds: float | None = None
    total_seconds: float | None = None
    state_history: tuple[VoiceState, ...] = field(default_factory=tuple)


class OpenAISpeechProvider:
    def list_voices(self): return VOICES
    def ready(self): return bool(os.getenv("OPENAI_API_KEY"))
    def synthesize(self, config: VoiceConfig, text: str, output: Path):
        if not self.ready(): raise RuntimeError("OPENAI_API_KEY is not set. Set it in the process environment before speaking.")
        from openai import OpenAI
        try:
            request = {"model": config.model, "voice": config.voice, "input": text, "response_format": config.audio_format, "speed": config.speed}
            if config.instructions: request["instructions"] = config.instructions
            OpenAI().audio.speech.create(**request).stream_to_file(output)
        except Exception as exc:
            raise RuntimeError(f"Speech provider failed: {type(exc).__name__}: {_sanitize_error(str(exc))}") from exc


class VoiceManager:
    """The public, state-owning boundary between the console and voice services."""
    def __init__(self, path: Path | None = None, provider=None, playback=None):
        self.path = path or voice_configuration_path()
        self.provider = provider or OpenAISpeechProvider()
        self.playback = playback or _play
        self._state = VoiceState.IDLE
        self._state_history: list[VoiceState] = [self._state]
        self._stop_event: threading.Event | None = None
        self._state_callback = None
        self._timeline: dict[str, float] = {}

    @property
    def state(self) -> VoiceState: return self._state
    @property
    def timeline(self) -> dict[str, float]: return dict(self._timeline)

    def _set_state(self, state: VoiceState, callback=None) -> None:
        self._state = state
        self._state_history.append(state)
        LOGGER.info("[VOICE] State -> %s", state.value)
        (callback or self._state_callback) and (callback or self._state_callback)(state)

    def set_state_callback(self, callback) -> None: self._state_callback = callback
    def transition(self, state: VoiceState) -> None: self._set_state(state)
    def reset(self) -> None: self._set_state(VoiceState.IDLE)
    def request_stop(self) -> bool:
        if self._state != VoiceState.LISTENING or self._stop_event is None: return False
        self._stop_event.set(); return True

    def list_microphones(self):
        from .capture import AudioCapture
        return AudioCapture().devices()
    def get_microphone(self): return self.load().microphone_device
    def set_microphone(self, device):
        if device not in {item.index for item in self.list_microphones()}: raise ValueError("Configured microphone is unavailable. Run 'rip voice microphones'.")
        return self.update(microphone_device=device)
    def clear_microphone(self): return self.update(microphone_device=None)
    def get_status(self):
        config = self.load(); devices = {item.index: item for item in self.list_microphones()}; selected = devices.get(config.microphone_device)
        return {"enabled": config.enabled, "muted": not config.playback_enabled, "voice": config.voice, "speech_provider": config.provider, "transcription_provider": "openai", "transcription_model": config.transcription_model, "microphone": config.microphone_device, "microphone_name": selected.name if selected else None, "playback_enabled": config.playback_enabled, "state": self.state.value}

    def record(self, output_path, **overrides):
        from .capture import AudioCapture
        config = self.load(); selected = overrides.pop("device", config.microphone_device)
        return AudioCapture().record(Path(output_path), device=selected, **{**{"maximum_seconds": config.maximum_recording_seconds, "minimum_speech_seconds": config.minimum_speech_seconds, "silence_timeout_seconds": config.silence_timeout_seconds, "silence_threshold": config.silence_threshold, "auto_stop_enabled": config.auto_stop_enabled}, **overrides})
    def transcribe(self, audio_path, *, language=None):
        from .transcription import OpenAITranscriptionProvider
        return OpenAITranscriptionProvider().transcribe(Path(audio_path), model=self.load().transcription_model, language=language)
    def listen_once(self, output_path, *, language=None, state_callback=None):
        started = time.perf_counter(); self._state_history = [VoiceState.IDLE]; self._timeline = {}; self._stop_event = threading.Event()
        try:
            self._set_state(VoiceState.LISTENING, state_callback)
            recording = self.record(output_path, stop_event=self._stop_event)
            self._timeline["recording_seconds"] = recording.duration_seconds
            self._set_state(VoiceState.TRANSCRIPT_FINALIZING, state_callback)
            self._set_state(VoiceState.TRANSCRIBING, state_callback)
            transcribing_started = time.perf_counter()
            text = self.transcribe(recording.output_path, language=language)
            self._timeline["transcription_seconds"] = time.perf_counter() - transcribing_started
            self._timeline["total_seconds"] = time.perf_counter() - started
            LOGGER.info("[VOICE] Recording %.2fs; transcription %.2fs; total %.2fs", self._timeline["recording_seconds"], self._timeline["transcription_seconds"], self._timeline["total_seconds"])
            return text
        except Exception:
            self._set_state(VoiceState.ERROR, state_callback)
            raise
        finally:
            self._stop_event = None

    def load(self):
        if not self.path.exists(): return VoiceConfig()
        try: value = json.loads(self.path.read_text(encoding="utf-8")); config = VoiceConfig(**value); self.validate(config); return config
        except Exception as exc: raise ValueError(f"Invalid voice configuration at {self.path}: {exc}") from exc
    def save(self, config):
        self.validate(config); self.path.parent.mkdir(parents=True, exist_ok=True); temp = self.path.with_suffix(".tmp"); temp.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8"); json.loads(temp.read_text(encoding="utf-8")); temp.replace(self.path)
    def validate(self, config):
        if config.provider != "openai" or config.voice not in self.provider.list_voices() or not 0.25 <= config.speed <= 4 or config.audio_format != "wav": raise ValueError("Invalid voice configuration")
        if config.maximum_recording_seconds <= 0 or config.minimum_speech_seconds < 0 or config.silence_timeout_seconds <= 0 or config.silence_threshold < 0: raise ValueError("Invalid voice recording configuration")
    def update(self, **values): config = VoiceConfig(**(asdict(self.load()) | values)); self.save(config); return config
    def speak(self, text, *, output_path=None, play=None, state_callback=None):
        config = self.load(); started = time.perf_counter(); self._state_history = [self.state]
        if not config.enabled: return VoiceResult(False, config.provider, config.model, config.voice, category="configuration", message="Voice output is disabled.")
        output = Path(output_path) if output_path else Path(tempfile.mkstemp(suffix=".wav")[1])
        try:
            self._set_state(VoiceState.SYNTHESIZING, state_callback); synth_started = time.perf_counter(); self.provider.synthesize(config, text, output); synthesis = time.perf_counter() - synth_started
            should_play = config.playback_enabled if play is None else play; playback_seconds = None
            if should_play:
                self._set_state(VoiceState.PLAYING, state_callback); play_started = time.perf_counter(); self.playback(output); playback_seconds = time.perf_counter() - play_started
            self._set_state(VoiceState.IDLE, state_callback)
            total = time.perf_counter()-started; self._timeline = {"synthesis_seconds": synthesis, "playback_seconds": playback_seconds or 0.0, "total_seconds": total}; LOGGER.info("[VOICE] Synthesis %.2fs; playback launch %.2fs; total %.2fs", synthesis, playback_seconds or 0.0, total)
            return VoiceResult(True, config.provider, config.model, config.voice, str(output), bool(should_play), message="Audio generated.", synthesis_seconds=synthesis, playback_seconds=playback_seconds, total_seconds=total, state_history=tuple(self._state_history))
        except Exception as exc:
            self._set_state(VoiceState.ERROR, state_callback)
            return VoiceResult(False, config.provider, config.model, config.voice, str(output) if output.exists() else None, category="playback" if output.exists() else "provider", message=f"Audio saved; playback failed: {exc}" if output.exists() else str(exc), total_seconds=time.perf_counter()-started, state_history=tuple(self._state_history))


def _play(path):
    if os.name != "nt": raise RuntimeError("Default Windows audio playback is unavailable on this platform.")
    try: os.startfile(str(path))
    except OSError as exc: raise RuntimeError(f"Could not launch the default audio player: {exc}") from exc


def _sanitize_error(message: str) -> str:
    message = re.sub(r"(?i)(authorization\s*[:=]\s*)([^\s,]+)", r"\1[redacted]", message)
    return re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", message)
