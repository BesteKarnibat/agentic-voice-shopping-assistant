"""LangGraph node: spoken_summary -> tts_audio_path (see contracts/state.py)."""
from __future__ import annotations

import os
import time
from typing import Optional

from config.paths import AUDIO_DIR
from contracts.state import AgentState, log_step

from .summary import build_spoken_summary
from .synthesizer import TTSBackend, synthesize_to_file

OUT_DIR = os.getenv("TTS_OUT_DIR", str(AUDIO_DIR / "tts"))


def make_tts_node(backend: Optional[TTSBackend] = None, out_dir: str = OUT_DIR):
    def tts_node(state: AgentState) -> dict:
        text = build_spoken_summary(state.get("spoken_summary") or "",
                                    state.get("final_answer") or "",
                                    state.get("clarification_question") or "")
        if not text:
            return {"tts_audio_path": None, "errors": ["tts: nothing to speak"],
                    **log_step("tts", "No text to speak")}
        name = f"{state.get('session_id', 'session')}-{int(time.time())}"
        t0 = time.perf_counter()
        try:
            path = synthesize_to_file(text, out_dir, name, backend)
        except Exception as e:  # on-screen answer still works without audio
            return {"tts_audio_path": None,
                    "errors": [f"tts: {type(e).__name__}: {e}"],
                    **log_step("tts", "Speech synthesis failed", error=str(e), text=text)}
        return {"tts_audio_path": path,
                **log_step("tts", f"Spoke {len(text.split())} words", text=text,
                           path=path, latency_s=round(time.perf_counter() - t0, 2))}
    return tts_node


tts_node = make_tts_node()
