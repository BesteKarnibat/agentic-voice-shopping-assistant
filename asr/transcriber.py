"""Whisper-based ASR (faster-whisper). Owner: Alekhya.

Accepts a WAV/MP3/etc. file path (decoded by PyAV, bundled with faster-whisper,
so no system ffmpeg is needed) or a 16 kHz mono float32 numpy array.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np

from config.paths import PROMPTS_DIR

SAMPLE_RATE = 16_000

# Biases decoding toward shopping vocabulary, brands and prices; helps with
# accented speech where "thirteen" / "thirty" or brand names are easily confused.
# Disclosed in prompts/asr_initial_prompt.md and loaded from there.
DEFAULT_PROMPT = (PROMPTS_DIR / "asr_initial_prompt.md").read_text(encoding="utf-8").strip()


@dataclass
class Segment:
    start: float
    end: float
    text: str
    avg_logprob: Optional[float] = None
    no_speech_prob: Optional[float] = None
    words: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {"start": round(self.start, 2), "end": round(self.end, 2), "text": self.text}
        if self.avg_logprob is not None:
            d["avg_logprob"] = round(self.avg_logprob, 3)
        if self.no_speech_prob is not None:
            d["no_speech_prob"] = round(self.no_speech_prob, 3)
        if self.words:
            d["words"] = self.words
        return d


@dataclass
class TranscriptionResult:
    text: str
    segments: list
    language: Optional[str]
    language_probability: Optional[float]
    duration: float
    latency_s: float

    @property
    def segment_dicts(self) -> list:
        return [s.to_dict() for s in self.segments]


class WhisperTranscriber:
    """Lazy-loading wrapper around faster-whisper's WhisperModel.

    model_size: tiny/base/small/medium/large-v3 (or "distil-large-v3").
      "small" is a good CPU default; use "large-v3" on GPU for best accent
      robustness.
    language: "en" (most accurate for English) or None to auto-detect, which
      handles non-English / code-switched speakers.
    """

    def __init__(
        self,
        model_size: str = os.getenv("ASR_MODEL", "small"),
        device: str = os.getenv("ASR_DEVICE", "auto"),
        compute_type: str = os.getenv("ASR_COMPUTE", "default"),
        language: Optional[str] = "en",
        initial_prompt: Optional[str] = DEFAULT_PROMPT,
        word_timestamps: bool = False,
        beam_size: int = 5,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.initial_prompt = initial_prompt
        self.word_timestamps = word_timestamps
        self.beam_size = beam_size
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, audio: Union[str, os.PathLike, np.ndarray]) -> TranscriptionResult:
        if isinstance(audio, (str, os.PathLike)) and not os.path.isfile(audio):
            raise FileNotFoundError(f"Audio file not found: {audio}")
        model = self._load()
        t0 = time.perf_counter()
        seg_iter, info = model.transcribe(
            audio if isinstance(audio, np.ndarray) else str(audio),
            language=self.language,
            beam_size=self.beam_size,
            initial_prompt=self.initial_prompt,
            vad_filter=True,                     # drop silence / noise, cuts hallucinations
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,    # avoids repetition loops
            temperature=[0.0, 0.2, 0.4],         # fallback for hard/accented audio
            word_timestamps=self.word_timestamps,
        )
        segments = []
        for s in seg_iter:
            words = [
                {"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word,
                 "probability": round(w.probability, 3)}
                for w in (s.words or [])
            ]
            segments.append(Segment(s.start, s.end, s.text.strip(), s.avg_logprob,
                                    s.no_speech_prob, words))
        text = " ".join(s.text for s in segments if s.text).strip()
        return TranscriptionResult(
            text=text,
            segments=segments,
            language=info.language,
            language_probability=info.language_probability,
            duration=info.duration,
            latency_s=time.perf_counter() - t0,
        )
