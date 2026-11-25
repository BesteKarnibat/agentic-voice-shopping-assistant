"""Streaming ASR: feed raw PCM chunks from a mic, get a final utterance on silence.

Uses simple energy-based endpointing; the final buffer is transcribed with the
full (VAD-filtered) Whisper pass, so accuracy matches file mode.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .transcriber import SAMPLE_RATE, TranscriptionResult, WhisperTranscriber


class StreamingASR:
    def __init__(
        self,
        transcriber: WhisperTranscriber,
        silence_s: float = 1.0,
        energy_threshold: float = 0.01,
        max_utterance_s: float = 30.0,
    ):
        self.t = transcriber
        self.silence_s = silence_s
        self.energy_threshold = energy_threshold
        self.max_samples = int(max_utterance_s * SAMPLE_RATE)
        self.reset()

    def reset(self) -> None:
        self._chunks: list = []
        self._n = 0
        self._heard_speech = False
        self._silent_run = 0

    def feed(self, pcm16: bytes) -> Optional[TranscriptionResult]:
        """Feed 16 kHz mono int16 little-endian PCM. Returns a result when an
        utterance ends (silence after speech, or max length), else None."""
        x = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if x.size == 0:
            return None
        loud = float(np.sqrt(np.mean(x**2))) >= self.energy_threshold
        if loud:
            self._heard_speech, self._silent_run = True, 0
        elif self._heard_speech:
            self._silent_run += x.size
        if not self._heard_speech:
            return None  # ignore leading silence
        self._chunks.append(x)
        self._n += x.size
        if self._silent_run >= self.silence_s * SAMPLE_RATE or self._n >= self.max_samples:
            return self.flush()
        return None

    def flush(self) -> Optional[TranscriptionResult]:
        if not self._chunks:
            return None
        audio = np.concatenate(self._chunks)
        self.reset()
        return self.t.transcribe(audio)
