"""run_agent(): entry point for the UI and ProofAgent (#21, #34). Owner: Devanshu.

    state = run_agent("Recommend a board game for four players under $30")

Sync, never raises (failures go to state["errors"]), returns a JSON-serializable AgentState.
on_step(entry) is called in the caller's thread as each node finishes.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import queue
import threading
import uuid
from concurrent.futures import wait as wait_futures
from typing import Callable, Optional

from agent.graph import get_graph
from agent.mcp_client import close_all_clients
from config.graph import RUN_TIMEOUT_S
from contracts.state import AgentState, StepLogEntry, log_step

log = logging.getLogger(__name__)

FALLBACK_ANSWER = "Sorry, something went wrong on my side. Please try again in a moment."

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """Background event loop that also owns the MCP subprocess."""
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="agent-loop", daemon=True).start()
        return _loop


@atexit.register
def shutdown() -> None:
    """Close the MCP server and stop the loop (runs at exit)."""
    global _loop
    if _loop is None or _loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(close_all_clients(), _loop).result(timeout=15)
    except Exception:  # noqa: BLE001
        pass
    _loop.call_soon_threadsafe(_loop.stop)
    _loop = None


def run_agent(
    transcript: str,
    *,
    session_id: Optional[str] = None,
    asr_segments: Optional[list[dict]] = None,
    on_step: Optional[Callable[[StepLogEntry], None]] = None,
) -> AgentState:
    """Run the graph on one user turn and return the final state."""
    initial: AgentState = {
        "session_id": session_id or str(uuid.uuid4()),
        "transcript": transcript or "",
        "asr_segments": asr_segments or [],
        "revision_count": 0,
        "step_log": [],
        "errors": [],
    }
    events: "queue.Queue[StepLogEntry]" = queue.Queue()
    latest: dict = {"state": dict(initial)}

    async def _stream() -> None:
        seen = 0
        async for value in get_graph().astream(initial, stream_mode="values"):
            latest["state"] = value
            entries = value.get("step_log") or []
            for entry in entries[seen:]:
                events.put(entry)
            seen = len(entries)

    future = asyncio.run_coroutine_threadsafe(asyncio.wait_for(_stream(), RUN_TIMEOUT_S), _get_loop())

    def _drain() -> None:
        while True:
            try:
                entry = events.get_nowait()
            except queue.Empty:
                return
            if on_step is not None:
                try:
                    on_step(entry)
                except Exception:  # noqa: BLE001
                    log.exception("on_step callback failed")

    # Poll so on_step runs in this thread. Check done() because the poll timeout and the
    # run timeout are both TimeoutError on 3.11+.
    while not future.done():
        wait_futures([future], timeout=0.1)
        _drain()
    extra_errors: list[str] = []
    try:
        future.result()
    except TimeoutError:
        extra_errors.append(f"run_agent: timed out after {RUN_TIMEOUT_S:.0f}s")
    except Exception as e:  # noqa: BLE001
        log.exception("graph run failed")
        extra_errors.append(f"run_agent: {type(e).__name__}: {e}")
    _drain()

    state = dict(latest["state"])
    if extra_errors:
        state["errors"] = list(state.get("errors") or []) + extra_errors
        entry = log_step("run_agent", "run failed, returning partial state", errors=extra_errors)["step_log"][0]
        state["step_log"] = list(state.get("step_log") or []) + [entry]
        if on_step is not None:
            try:
                on_step(entry)
            except Exception:  # noqa: BLE001
                pass
    if not state.get("final_answer"):
        state["final_answer"] = FALLBACK_ANSWER
        state["spoken_summary"] = FALLBACK_ANSWER
    state.setdefault("spoken_summary", state["final_answer"])
    return json.loads(json.dumps(state, default=str))
