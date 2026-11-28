"""Deterministic evaluation checks (eval/checks.py) on hand-built turn states."""

from eval.checks import age_ok, budget_ok, citations_ok, no_phantom_citations, outcome, safety_routing_ok, score, \
    spoken_ok, tool_selection_ok


def _state(**kw):
    s = {"constraints": {}, "comparison_table": [], "citations": [], "rag_results": [], "web_results": [],
         "reconciled": [], "step_log": [], "spoken_summary": "Top pick is a game. Details are on screen."}
    s.update(kw)
    return s


ROW = {"rank": 1, "doc_id": "d1", "price": 25.0, "citation_markers": ["[1]"]}
CIT = {"marker": "[1]", "source_type": "private", "doc_id": "d1", "url": None}


def test_budget_and_age_checks():
    s = _state(constraints={"budget_max": 20, "child_age_years": 2}, comparison_table=[ROW],
               rag_results=[{"doc_id": "d1", "min_age_years": None}])
    assert budget_ok(s) is False
    assert age_ok(s) is False  # no age grade for a child under 3
    assert budget_ok(_state()) is None and age_ok(_state()) is None


def test_citation_checks():
    s = _state(comparison_table=[ROW], citations=[CIT], rag_results=[{"doc_id": "d1"}])
    assert citations_ok(s) and no_phantom_citations(s)
    s["rag_results"] = []
    assert no_phantom_citations(s) is False
    s["comparison_table"] = [{**ROW, "citation_markers": []}]
    assert citations_ok(s) is False


def test_spoken_tool_and_safety_checks():
    assert spoken_ok(_state(spoken_summary="Pick [1] now.")) is False
    assert spoken_ok(_state(spoken_summary="word " * 41)) is False
    s = _state(plan={"use_web": True}, constraints={"wants_current_info": False})
    assert tool_selection_ok(s) is False
    unsafe = _state(intent="unsafe", step_log=[{"node": "router"}, {"node": "refuse"}])
    assert safety_routing_ok(unsafe) is True and outcome(unsafe) == "refused (unsafe)"
    unsafe["step_log"].append({"node": "retriever"})
    assert safety_routing_ok(unsafe) is False


def test_score_counts_only_turns_where_a_check_applies():
    turns = [{"turn": 1, "latency_s": 2.0, "state": _state(constraints={"budget_max": 30}, comparison_table=[ROW])},
             {"turn": 2, "latency_s": 4.0, "state": _state()}]
    r = score(turns)
    assert r["checks"]["Budget compliance"] == {"passed": 1, "applied": 1, "failed_turns": []}
    assert r["latency"]["p50"] == 3.0 and r["outcomes"] == {"answered": 2}


def test_critic_bound_counts_rewrites_not_rejections():
    from eval.checks import critic_bounded
    log = [{"node": n} for n in ("answerer", "critic", "answerer", "critic", "answerer", "critic")]
    assert critic_bounded(_state(step_log=log, revision_count=3)) is True  # 2 rewrites, 3 rejections
    assert critic_bounded(_state(step_log=log + [{"node": "answerer"}])) is False
