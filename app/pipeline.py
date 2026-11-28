"""Runs one voice turn: ASR -> run_agent(transcript) -> TTS, and returns the final AgentState.

The UI owns the voice steps; the LangGraph workflow is reached only through the entry point
`agent.run_agent(transcript, session_id=..., asr_segments=...) -> state` (agent/run.py), which never
raises and always returns a state with a final_answer. Set AGENT_ENTRY="package.module:function" to
point at a different one (default "agent:run_agent").

If the entry point can't be imported, only ASR runs: the transcript is real and no answer is produced.
No sample data is ever shown.
"""
from __future__ import annotations

import importlib
import os
import uuid
from typing import Callable, Optional

from asr.node import make_asr_node
from tts.node import make_tts_node

AGENT_ENTRY = os.getenv("AGENT_ENTRY", "agent:run_agent")


def load_agent() -> Optional[Callable]:
    """Return the run_agent callable, or None if it can't be imported."""
    mod_name, _, fn_name = AGENT_ENTRY.partition(":")
    try:
        return getattr(importlib.import_module(mod_name), fn_name)
    except (ImportError, AttributeError):
        return None


def _merge(state: dict, update: dict) -> dict:
    """Apply a partial update (step_log / errors append, other keys overwrite)."""
    for k, v in (update or {}).items():
        if k in ("step_log", "errors"):
            state[k] = list(state.get(k) or []) + list(v or [])
        else:
            state[k] = v
    return state


def has_reply(state: dict) -> bool:
    """True if the agent produced something to show and speak (answer, refusal or clarification)."""
    return bool(state.get("final_answer") or state.get("clarification_question"))


def run_turn(audio_path: Optional[str] = None, text: Optional[str] = None,
             session_id: Optional[str] = None, agent: Optional[Callable] = None,
             tts_node: Optional[Callable] = None, on_step: Optional[Callable] = None) -> tuple:
    """Returns (final_state, mode) where mode is 'agent' or 'asr_only'.

    on_step(entry) is called in the caller's thread as each graph node finishes (live progress)."""
    state: dict = {"session_id": session_id or uuid.uuid4().hex[:8], "step_log": [], "errors": []}
    if audio_path:
        state["audio_path"] = audio_path
    if text:
        state["transcript"] = text

    agent = agent or load_agent()
    mode = "agent" if agent else "asr_only"

    # 1. ASR (skipped automatically when the user typed text)
    state = _merge(state, make_asr_node()(state))
    if not state.get("transcript") or agent is None:
        return state, mode

    # 2. LangGraph workflow
    try:
        extra = {"on_step": on_step} if on_step else {}
        result = agent(state["transcript"], session_id=state["session_id"],
                       asr_segments=state.get("asr_segments") or [], **extra) or {}
    except Exception as e:  # show the failure in the chat instead of crashing the page
        return _merge(state, {"errors": [f"agent: {type(e).__name__}: {e}"]}), "agent"
    # Keep our ASR fields and step-log entry; take everything else from the agent's state.
    result = dict(result)
    for k in ("session_id", "audio_path", "transcript", "asr_segments"):
        result.pop(k, None)
    state = _merge(state, result)

    # 3. TTS (unless the graph already produced audio)
    if has_reply(state) and not state.get("tts_audio_path"):
        state = _merge(state, (tts_node or make_tts_node())(state))
    return state, "agent"
