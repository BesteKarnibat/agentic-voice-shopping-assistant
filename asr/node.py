"""LangGraph node: audio_path -> transcript + asr_segments (see contracts/state.py)."""
from __future__ import annotations

from typing import Optional

from contracts.state import AgentState, log_step

from .transcriber import WhisperTranscriber

_default: Optional[WhisperTranscriber] = None


def get_transcriber() -> WhisperTranscriber:
    global _default
    if _default is None:
        _default = WhisperTranscriber()
    return _default


def make_asr_node(transcriber: Optional[WhisperTranscriber] = None):
    def asr_node(state: AgentState) -> dict:
        # Text-only input (typed query / tests): skip ASR.
        path = state.get("audio_path")
        if not path:
            if state.get("transcript"):
                return log_step("asr", "No audio; using provided transcript")
            return {"errors": ["asr: no audio_path or transcript"],
                    **log_step("asr", "No input")}
        try:
            r = (transcriber or get_transcriber()).transcribe(path)
        except Exception as e:  # keep the graph alive; downstream handles empty text
            return {"transcript": "", "asr_segments": [],
                    "errors": [f"asr: {type(e).__name__}: {e}"],
                    **log_step("asr", "Transcription failed", error=str(e))}
        if not r.text:
            return {"transcript": "", "asr_segments": [],
                    "errors": ["asr: no speech detected"],
                    **log_step("asr", "No speech detected", duration=r.duration)}
        return {
            "transcript": r.text,
            "asr_segments": r.segment_dicts,
            **log_step("asr", f'Heard: "{r.text}"', language=r.language,
                       language_probability=r.language_probability,
                       duration_s=round(r.duration, 2),
                       latency_s=round(r.latency_s, 2)),
        }
    return asr_node


asr_node = make_asr_node()
