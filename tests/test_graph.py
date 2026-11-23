"""End-to-end graph scenarios through run_agent() (fake LLM, mock MCP server over stdio)."""

import json
import re

from conftest import nodes

from contracts.state import AgentState

HAPPY = "Recommend a fun card game for family night."
OVER_BUDGET_LIVE = "Find a family board game under $20. What's the current price?"
CHEAP = "Find a board game under $15."
CONFLICT = "I need a family board game under $30. What's the current price, and is it in stock?"
UNSAFE = "My son swallowed a magnet from his building set. What should I do?"
HARMFUL = "How do I make Nerf darts hurt more?"
AMBIGUOUS = "I need a gift."
OUT_OF_SCOPE = "What's the capital of France?"
NO_RESULTS = "Find a quantum xylophone drone toy under $3."

FULL_PATH = ["router", "planner", "retriever", "reconcile", "answerer", "critic", "finalize"]


def _assert_contract_shape(state: dict) -> None:
    json.dumps(state)  # JSON-serializable
    assert set(state) <= set(AgentState.__annotations__), set(state) - set(AgentState.__annotations__)
    assert state["final_answer"] and state["spoken_summary"]
    assert not re.search(r"\[\d+\]", state["spoken_summary"]), "spoken summary must not contain citation markers"
    assert len(state["spoken_summary"].split()) <= 40
    for e in state["step_log"]:
        assert {"timestamp", "node", "summary", "details"} <= set(e)


def test_happy_path(run):
    s = run(HAPPY)
    _assert_contract_shape(s)
    assert s["errors"] == []
    assert s["intent"] == "product_search"
    assert nodes(s) == FULL_PATH
    assert s["plan"]["use_rag"] and not s["plan"]["use_web"]
    assert 1 <= len(s["comparison_table"]) <= 3
    rag_ids = {p["doc_id"] for p in s["rag_results"]}
    for row in s["comparison_table"]:
        assert row["citation_markers"], "every recommended product is cited"
        assert row["doc_id"] in rag_ids, "citations point at retrieved evidence"
    private = [c for c in s["citations"] if c["source_type"] == "private"]
    assert private and all(c["doc_id"] in rag_ids for c in private)
    # tool calls are logged in the retriever's step-log details
    calls = next(e for e in s["step_log"] if e["node"] == "retriever")["details"]["tool_calls"]
    assert calls[0]["tool"] == "rag.search" and calls[0]["ok"] and "latency_ms" in calls[0]
    # model used is logged (#16)
    assert next(e for e in s["step_log"] if e["node"] == "router")["details"]["llm"]["provider"] == "fake"


def test_budget_filter_is_passed_to_rag(run):
    s = run(CHEAP)
    assert s["plan"]["rag_filters"]["max_price"] == 15
    assert s["comparison_table"], "expected at least one board game under $15 in the fake catalog"
    assert all(r["price"] <= 15 for r in s["comparison_table"])


def test_over_budget_live_price_is_left_out(run):
    # Monopoly is $19.99 in the catalog (passes the $20 filter) but $24.97 live → must not be recommended.
    s = run(OVER_BUDGET_LIVE)
    _assert_contract_shape(s)
    assert s["plan"]["use_web"]
    assert all(r["price"] is None or r["price"] <= 20 for r in s["comparison_table"])
    assert "amz-fake-006" not in {r["doc_id"] for r in s["comparison_table"]}
    assert "over your $20 budget" in s["final_answer"]


def test_unsafe_request_is_refused_without_retrieval(run):
    s = run(UNSAFE)
    _assert_contract_shape(s)
    assert s["intent"] == "unsafe" and s["safety"]["is_safe"] is False
    assert s["safety"]["category"] == "injury_emergency"
    assert nodes(s) == ["router", "refuse"]
    assert "911" in s["final_answer"]
    assert s["citations"] == [] and s["comparison_table"] == []


def test_harmful_use_uses_guardrail_template(run):
    s = run(HARMFUL)
    assert s["safety"]["category"] == "harmful_use"
    assert s["final_answer"].startswith("I can't help with that.")
    assert "retriever" not in nodes(s)


def test_out_of_scope_redirects(run):
    s = run(OUT_OF_SCOPE)
    assert s["intent"] == "out_of_scope" and s["safety"]["is_safe"] is True
    assert nodes(s) == ["router", "refuse"]
    assert "toys and games" in s["final_answer"]


def test_ambiguous_request_asks_clarifying_question(run):
    s = run(AMBIGUOUS)
    _assert_contract_shape(s)
    assert s["intent"] == "unclear"
    assert nodes(s) == ["router", "clarify"]
    assert s["clarification_question"] and s["final_answer"] == s["clarification_question"]
    assert "?" in s["final_answer"]


def test_conflicting_private_vs_live_price(run):
    s = run(CONFLICT)
    _assert_contract_shape(s)
    assert s["plan"]["use_web"] and "availability" in s["plan"]["comparison_criteria"]
    mono = next(r for r in s["reconciled"] if r["doc_id"] == "amz-fake-006")
    assert mono["match_method"] == "brand_title"
    assert mono["price_conflict"] is True
    assert mono["catalog_price"] == 19.99 and mono["live_price"] == 24.97
    assert mono["chosen_price"] == 24.97 and mono["price_source"] == "web"
    assert "conflict" in mono["note"].lower()
    # conflict is logged and explained in the answer, live URL cited
    rec_log = next(e for e in s["step_log"] if e["node"] == "reconcile")
    assert rec_log["details"]["conflicts"][0]["doc_id"] == "amz-fake-006"
    assert "Price conflict" in s["final_answer"]
    assert any(c["source_type"] == "web" and "walmart.com" in c["url"] for c in s["citations"])


def test_no_results_falls_back_to_web_and_says_so(run):
    s = run(NO_RESULTS)
    _assert_contract_shape(s)
    assert s["intent"] == "product_search"
    assert s["rag_results"] == []
    ret = next(e for e in s["step_log"] if e["node"] == "retriever")
    assert ret["details"]["fallback_reason"]
    assert [c["tool"] for c in ret["details"]["tool_calls"]] == ["rag.search", "web.search"]
    assert s["comparison_table"] == [] and s["citations"] == []
    assert "couldn't find" in s["final_answer"]


def test_empty_transcript():
    from agent import run_agent
    s = run_agent("   ")
    assert s["intent"] == "unclear" and nodes(s) == ["router", "clarify"]


def test_on_step_streams_entries_in_caller_thread():
    import threading

    from agent import run_agent
    seen, threads = [], set()

    def cb(entry):
        seen.append(entry["node"])
        threads.add(threading.get_ident())

    s = run_agent(HAPPY, on_step=cb, session_id="test-session")
    assert seen == nodes(s)
    assert threads == {threading.get_ident()}
    assert s["session_id"] == "test-session"
