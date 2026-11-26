"""ProofAgent adapter (#55). Owner: Beste. See docs/components/evaluation.md.

ProofAgent loads this file and calls `agent(message)` once per turn of one continuous conversation. Each call
runs the full LangGraph agent through `run_agent()` and returns an `AgentResponse` with:

- `text`: the on-screen answer (`final_answer`),
- `tools_called`: the MCP calls the Retriever made (`rag.search`, `web.search`), so Tool Use is scored on
  real calls,
- `retrievals`: the catalog products and live results the answer could draw on,
- `memory_snapshot`: intent, constraints, safety verdict, Critic verdict and errors for this turn.

Every turn is also appended to data/proofagent/turns/<run>.jsonl (message, transcript sent, final state), which
the deterministic checks in the evaluation plan read.

    uv run proof run eval/agent.py ...    # usually through `uv run doit eval` / `eval_dry_run`
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from proofagent_harness import AgentResponse

from agent.run import run_agent
from config import eval as cfg
from config.paths import EVAL_TURNS_DIR

SESSION_ID = f"proofagent-{uuid.uuid4().hex[:8]}"
_history: list[dict] = []  # earlier shopping turns of this conversation: {"user": str, "products": [titles]}
# Only shopping turns are remembered. A refused or emergency turn is not carried forward, or the Router keeps
# seeing it and refuses every later request (seen in the first dry run).
SHOPPING_INTENTS = {"product_search", "product_comparison", "product_question", "price_check"}
_log_path = EVAL_TURNS_DIR / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{SESSION_ID}.jsonl"


def compose_transcript(message: str, history: list[dict], keep: int) -> str:
    """The current message, plus the last `keep` user turns so follow-ups ('which is cheapest?') make sense."""
    recent = history[-keep:] if keep > 0 else []
    if not recent:
        return message
    lines = ["Earlier in this conversation:"]
    for h in recent:
        lines.append(f"- User said: {h['user']}")
        if h["products"]:
            lines.append(f"  You recommended: {'; '.join(h['products'])}")
    lines.append(f"New message: {message}")  # not "Current ...": that word triggers the live-price keyword
    return "\n".join(lines)


def tools_called(state: dict) -> list[dict]:
    """MCP calls from the Retriever's step log, in ProofAgent's {name, args, result} shape."""
    out = []
    for e in state.get("step_log") or []:
        if e.get("node") != "retriever":
            continue
        for call in (e.get("details") or {}).get("tool_calls") or []:
            result = {k: v for k, v in call.items() if k not in ("tool", "args")}
            out.append({"name": call.get("tool"), "args": call.get("args") or {}, "result": result})
    return out


def retrievals(state: dict) -> list[dict]:
    out = []
    for p in state.get("rag_results") or []:
        chunk = " | ".join(str(x) for x in (
            p.get("title"), p.get("brand"), p.get("price") and f"${p['price']:.2f}",
            p.get("rating") and f"{p['rating']} stars",
            p.get("min_age_years") is not None and f"min age {p['min_age_years']:g}",
            p.get("safety_warnings") and "warnings: " + "; ".join(p["safety_warnings"]),
            p.get("features_snippet")) if x)
        out.append({"source": p["doc_id"], "chunk": chunk, "score": p.get("score")})
    for w in state.get("web_results") or []:
        chunk = " | ".join(str(x) for x in (w.get("title"), w.get("price") and f"${w['price']:.2f}",
                                            w.get("availability"), w.get("snippet")) if x)
        out.append({"source": w["url"], "chunk": chunk})
    return out


def snapshot(state: dict, latency_s: float) -> dict:
    critic = state.get("critic") or {}
    return {
        "intent": state.get("intent"),
        "constraints": state.get("constraints"),
        "safety": state.get("safety"),
        "nodes": [e.get("node") for e in state.get("step_log") or []],
        "critic_approved": critic.get("approved"),
        "revision_count": state.get("revision_count"),
        "citations": [c.get("doc_id") or c.get("url") for c in state.get("citations") or []],
        "spoken_summary": state.get("spoken_summary"),
        "errors": state.get("errors") or [],
        "latency_s": round(latency_s, 2),
    }


def _log_turn(record: dict) -> None:
    EVAL_TURNS_DIR.mkdir(parents=True, exist_ok=True)
    with _log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


_turn = 0


def reset() -> None:
    """Start a new conversation. ProofAgent calls agent.reset() after its calibration probes."""
    global SESSION_ID
    _history.clear()
    SESSION_ID = f"proofagent-{uuid.uuid4().hex[:8]}"
    _log_turn({"event": "reset", "session_id": SESSION_ID})


def agent(message: str) -> AgentResponse:
    transcript = compose_transcript(message, _history, cfg.HISTORY_TURNS)
    start = time.perf_counter()
    try:
        state = run_agent(transcript, session_id=SESSION_ID)
    except Exception as e:  # noqa: BLE001  never crash the harness; the failure is part of the evidence
        state = {"final_answer": "Sorry, something went wrong on my side. Please try again.",
                 "errors": [f"run_agent raised: {e}"]}
    latency = time.perf_counter() - start

    text = state.get("final_answer") or "Sorry, I don't have an answer for that."
    global _turn
    _turn += 1
    if state.get("intent") in SHOPPING_INTENTS:
        _history.append({"user": message, "products": [r["title"] for r in state.get("comparison_table") or []]})
    _log_turn({"turn": _turn, "session_id": SESSION_ID, "message": message, "transcript": transcript,
               "latency_s": round(latency, 2), "state": state})
    return AgentResponse(text=text, tools_called=tools_called(state), retrievals=retrievals(state),
                         memory_snapshot=snapshot(state, latency))


agent.reset = reset  # the harness looks for `agent.reset`
