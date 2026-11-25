"""Runs one voice turn: ASR -> run_agent(transcript) -> TTS, and returns the final AgentState.

The UI owns the voice steps; the LangGraph workflow is reached only through Devanshu's entry point
`run_agent(transcript) -> state` (docs_assignment/task-planning.md, handoff 5). Set
AGENT_ENTRY="package.module:function" to point at it (default "graph:run_agent").

Until run_agent exists, only ASR runs: the transcript is real and no answer is produced.
No sample data is ever shown.
"""
from __future__ import annotations

import importlib
import os
import uuid
from typing import Callable, Optional

from asr.node import make_asr_node
from tts.node import make_tts_node

AGENT_ENTRY = os.getenv("AGENT_ENTRY", "graph:run_agent")


def load_agent() -> Optional[Callable]:
    """Return run_agent(transcript) -> state, or None if it can't be imported yet."""
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
             tts_node: Optional[Callable] = None) -> tuple:
    """Returns (final_state, mode) where mode is 'agent' or 'asr_only'."""
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
        result = agent(state["transcript"]) or {}
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
