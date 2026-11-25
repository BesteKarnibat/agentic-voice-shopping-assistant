"""TTS backends. Owner: Alekhya.

OpenAI TTS is the default (natural voice, streams bytes as they are generated).
pyttsx3 is an offline fallback (no API key; robotic but always available).
"""
from __future__ import annotations

import os
import struct
import wave
from pathlib import Path
from typing import Iterator, Optional, Protocol

from config.paths import PROMPTS_DIR


class TTSBackend(Protocol):
    extension: str

    def stream(self, text: str) -> Iterator[bytes]: ...


# Voice style for gpt-4o TTS models; disclosed in prompts/tts_instructions.md and loaded from there.
TTS_INSTRUCTIONS = (PROMPTS_DIR / "tts_instructions.md").read_text(encoding="utf-8").strip()

LEAD_IN_MS = int(os.getenv("TTS_LEAD_IN_MS", "500"))  # silence before speech


class OpenAITTS:
    # Raw 24 kHz 16-bit mono PCM, so we can prepend silence and wrap it as WAV.
    extension = "wav"
    pcm_rate = 24_000

    def __init__(self, model: str = os.getenv("TTS_MODEL", "gpt-4o-mini-tts"),
                 voice: str = os.getenv("TTS_VOICE", "alloy"),
                 instructions: str = TTS_INSTRUCTIONS):
        self.model, self.voice, self.instructions = model, voice, instructions
        self._client = None

    def stream(self, text: str) -> Iterator[bytes]:
        if self._client is None:
            from openai import OpenAI  # needs OPENAI_API_KEY

            self._client = OpenAI()
        kwargs = {"model": self.model, "voice": self.voice, "input": text,
                  "response_format": "pcm"}
        if self.model.startswith("gpt-4o"):  # `instructions` unsupported by tts-1
            kwargs["instructions"] = self.instructions
        with self._client.audio.speech.with_streaming_response.create(**kwargs) as resp:
            yield from resp.iter_bytes(chunk_size=4096)


class OfflineTTS:
    extension = "wav"  # complete WAV file

    def __init__(self, rate: int = 175):
        self.rate = rate

    def stream(self, text: str) -> Iterator[bytes]:
        import tempfile

        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "out.wav"
            engine.save_to_file(text, str(p))
            engine.runAndWait()
            yield p.read_bytes()


def default_backend() -> TTSBackend:
    return OpenAITTS() if os.getenv("OPENAI_API_KEY") else OfflineTTS()


def _pad_wav(path: Path, lead_in_ms: int) -> None:
    """Prepend silence to an existing WAV file."""
    with wave.open(str(path), "rb") as r:
        params, frames = r.getparams(), r.readframes(r.getnframes())
    silence = b"\x00" * (int(params.framerate * lead_in_ms / 1000) * params.sampwidth * params.nchannels)
    with wave.open(str(path), "wb") as w:
        w.setparams(params)
        w.writeframes(silence + frames)


def synthesize_to_file(text: str, out_dir: str, name: str,
                       backend: Optional[TTSBackend] = None,
                       lead_in_ms: int = LEAD_IN_MS) -> str:
    """Synthesize `text` to a file, with `lead_in_ms` of silence first so the
    player has time to wake up and the first words aren't clipped."""
    backend = backend or default_backend()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.{backend.extension}"
    rate = getattr(backend, "pcm_rate", None)
    with open(path, "wb") as f:
        if rate:  # raw PCM stream -> write WAV header, silence, then audio
            f.write(struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 0, b"WAVE", b"fmt ", 16,
                                1, 1, rate, rate * 2, 2, 16, b"data", 0))
            f.write(b"\x00" * (int(rate * lead_in_ms / 1000) * 2))
        for chunk in backend.stream(text):
            f.write(chunk)
        if rate:  # patch sizes now that the length is known
            size = f.tell()
            f.seek(4)
            f.write(struct.pack("<I", size - 8))
            f.seek(40)
            f.write(struct.pack("<I", size - 44))
    if not rate and backend.extension == "wav" and lead_in_ms > 0:
        _pad_wav(path, lead_in_ms)
    return str(path)
