"""ProofAgent adapter (#55): offline, through run_agent() with the fake LLM and mock MCP server (see conftest)."""

import importlib.util
import json

from config.paths import ROOT


def _load_adapter(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("eval_agent", ROOT / "eval" / "agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_log_path", tmp_path / "turns.jsonl")
    monkeypatch.setattr(mod, "EVAL_TURNS_DIR", tmp_path)
    return mod


def test_compose_transcript_adds_recent_turns_only():
    spec = importlib.util.spec_from_file_location("eval_agent_c", ROOT / "eval" / "agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    history = [{"user": "old", "products": []}, {"user": "puzzles under $25", "products": ["Castle Puzzle"]}]
    assert mod.compose_transcript("hi", [], 2) == "hi"
    assert mod.compose_transcript("hi", history, 0) == "hi"
    t = mod.compose_transcript("which is cheapest?", history, 1)
    assert "old" not in t and "puzzles under $25" in t and "Castle Puzzle" in t
    assert t.endswith("Current request: which is cheapest?")


def test_adapter_returns_tools_retrievals_and_logs_turns(tmp_path, monkeypatch):
    mod = _load_adapter(tmp_path, monkeypatch)
    r = mod.agent("Recommend a fun card game for family night.")
    assert r.text and "[1]" in r.text
    assert [t["name"] for t in r.tools_called] == ["rag.search"]
    assert r.tools_called[0]["result"]["ok"] is True
    assert r.retrievals and r.retrievals[0]["source"].startswith("amz-fake-")
    assert r.memory_snapshot["intent"] == "product_search"
    assert r.memory_snapshot["nodes"][-1] == "finalize"

    r2 = mod.agent("My son swallowed a magnet. What should I do?")
    assert "911" in r2.text and r2.tools_called == []
    r3 = mod.agent("Which one is the cheapest?")
    lines = [json.loads(x) for x in (tmp_path / "turns.jsonl").read_text().splitlines()]
    assert [x["turn"] for x in lines] == [1, 2, 3]
    assert lines[1]["transcript"].startswith("Earlier in this conversation:")
    # the emergency turn is not carried forward; the shopping turn is
    assert "swallowed" not in lines[2]["transcript"] and "card game" in lines[2]["transcript"]
    assert lines[0]["state"]["final_answer"] == r.text

    mod.agent.reset()
    assert mod._history == []
    assert mod.compose_transcript("x", mod._history, 2) == "x"
