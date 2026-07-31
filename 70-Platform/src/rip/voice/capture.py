from __future__ import annotations

import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MicrophoneDevice:
    index: int
    name: str
    channels: int
    sample_rate: int
    default: bool = False


@dataclass(frozen=True)
class RecordingResult:
    output_path: Path
    duration_seconds: float
    stop_reason: str


class AudioCapture:
    """PCM microphone capture with local voice-activity stopping."""

    def devices(self):
        import sounddevice as sd

        default = sd.default.device[0]
        return tuple(
            MicrophoneDevice(i, item["name"], int(item["max_input_channels"]), int(item["default_samplerate"]), i == default)
            for i, item in enumerate(sd.query_devices())
            if item["max_input_channels"] > 0
        )

    def record(
        self,
        output: Path,
        *,
        device=None,
        sample_rate: int = 16000,
        channels: int = 1,
        maximum_seconds: float = 60,
        minimum_speech_seconds: float = 0.5,
        silence_timeout_seconds: float = 1.5,
        silence_threshold: float = 0.015,
        auto_stop_enabled: bool = True,
        stop_event: threading.Event | None = None,
        status_callback=None,
    ) -> RecordingResult:
        import sounddevice as sd

        output.parent.mkdir(parents=True, exist_ok=True)
        frames: list[bytes] = []
        completed = threading.Event()
        stop_event = stop_event or threading.Event()
        started = time.perf_counter()
        speech_started: float | None = None
        last_speech: float | None = None
        stop_reason = "maximum duration reached"

        def callback(indata, _frames, _time_info, _status) -> None:
            nonlocal speech_started, last_speech, stop_reason
            now = time.perf_counter()
            frames.append(indata.copy().tobytes())
            # InputStream provides int16 samples; normalize so the configured
            # threshold is stable across devices and sample formats.
            level = float(abs(indata).max()) / 32768.0
            if level >= silence_threshold:
                speech_started = speech_started or now
                last_speech = now
            elif (
                auto_stop_enabled
                and speech_started is not None
                and last_speech is not None
                and now - speech_started >= minimum_speech_seconds
                and now - last_speech >= silence_timeout_seconds
            ):
                stop_reason = "silence detected"
                completed.set()

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="int16",
                device=device,
                callback=callback,
            ):
                while not completed.is_set() and not stop_event.is_set():
                    if time.perf_counter() - started >= maximum_seconds:
                        completed.set()
                        break
                    time.sleep(0.05)
        except KeyboardInterrupt as exc:
            raise RuntimeError("Recording cancelled.") from exc
        except Exception as exc:
            raise RuntimeError(f"Microphone unavailable: {exc}") from exc

        if stop_event.is_set():
            stop_reason = "manual stop"
        duration = time.perf_counter() - started
        if status_callback and stop_reason == "silence detected":
            status_callback("silence detected")
        if not frames:
            raise RuntimeError("No speech detected.")
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"".join(frames))
        return RecordingResult(output, duration, stop_reason)
