from __future__ import annotations

import os
from pathlib import Path

class OpenAITranscriptionProvider:
    def transcribe(self, audio: Path, *, model="gpt-4o-mini-transcribe", language=None):
        if not os.getenv("OPENAI_API_KEY"): raise RuntimeError("OPENAI_API_KEY is not set.")
        from openai import OpenAI
        try:
            with audio.open("rb") as stream:
                response = OpenAI().audio.transcriptions.create(model=model, file=stream, **({"language": language} if language else {}))
            text = (getattr(response, "text", "") or "").strip()
            if not text: raise RuntimeError("Transcription returned no text.")
            return text
        except RuntimeError: raise
        except Exception as exc: raise RuntimeError(f"Transcription failed: {type(exc).__name__}: {exc}") from exc
