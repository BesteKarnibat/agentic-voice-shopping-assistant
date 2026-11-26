"""Answerer and Critic unit tests (#46, #47). Offline: fake provider, hand-built state."""

import os

os.environ.setdefault("LLM_PROVIDER", "fake")

from agent.nodes.answerer import WARNING_NOTE, answerer_node  # noqa: E402
from agent.nodes.critic import critic_node  # noqa: E402


def _product(doc_id, title, price, rating=4.5, min_age=None, max_age=None, warnings=None, features=""):
    rag = {"doc_id": doc_id, "sku": None, "title": title, "brand": title.split()[0], "category": "Toys & Games",
           "price": price, "rating": rating, "min_age_years": min_age, "max_age_years": max_age,
           "safety_warnings": warnings, "features_snippet": features, "score": 1.0}
    rec = {"doc_id": doc_id, "title": title, "brand": rag["brand"], "catalog_price": price, "live_price": None,
           "live_url": None, "availability": None, "match_method": "none", "match_score": 0.0,
           "price_conflict": False, "chosen_price": price, "price_source": "catalog", "note": None}
    return rag, rec


def _state(products, **constraints):
    return {"transcript": "test request", "intent": "product_search",
            "constraints": {"preferences": [], "exclude_features": [], **constraints},
            "rag_results": [p[0] for p in products], "web_results": [], "reconciled": [p[1] for p in products],
            "revision_count": 0, "step_log": [], "errors": []}


GAME = _product("d-game", "Family Card Game Night Edition", 12.99, 4.7, 7, None, None, "2-6 players")
PRICEY = _product("d-pricey", "Deluxe Strategy Board Game", 45.00, 4.9, 10)
BLOCKS = _product("d-blocks", "Brick Builder Starter Set", 19.99, 4.6, 4, 99, ["choking hazard: small parts"])
STACKER = _product("d-stack", "Rainbow Baby Stacking Rings", 8.99, 4.8, 0.5, 3, None, "Five soft rings")


def _run(state):
    state.update(answerer_node(state))
    return state


def test_answerer_drops_over_budget_and_cites_every_row():
    s = _run(_state([PRICEY, GAME], budget_max=30))
    ids = [r["doc_id"] for r in s["comparison_table"]]
    assert ids == ["d-game"]
    assert "over your $30 budget" in s["final_answer"]
    row = s["comparison_table"][0]
    assert row["citation_markers"] == ["[1]"] and s["citations"][0]["doc_id"] == "d-game"
    assert "[1]" in s["final_answer"]


def test_answerer_applies_age_and_small_parts_rules_for_toddler():
    s = _run(_state([BLOCKS, STACKER], child_age_years=1))
    assert [r["doc_id"] for r in s["comparison_table"]] == ["d-stack"]
    assert WARNING_NOTE in s["final_answer"]
    assert "warning" in s["spoken_summary"].lower()


def test_answerer_excluded_feature_and_spoken_summary_rules():
    s = _run(_state([BLOCKS, GAME], exclude_features=["small parts"]))
    assert [r["doc_id"] for r in s["comparison_table"]] == ["d-game"]
    assert len(s["spoken_summary"].split()) <= 40
    assert "[" not in s["spoken_summary"]


def test_answerer_no_match_says_so():
    s = _run(_state([PRICEY], budget_max=5))
    assert s["comparison_table"] == [] and s["citations"] == []
    assert "couldn't find" in s["final_answer"]


def test_critic_approves_a_clean_draft():
    s = _run(_state([GAME], budget_max=30))
    out = critic_node(s)
    assert out["critic"]["approved"], out["critic"]["feedback"]
    assert out["revision_count"] == 0


def test_critic_rejects_over_budget_draft_then_answerer_fixes_it():
    s = _run(_state([PRICEY, GAME]))  # no budget yet, so both are picked
    s["constraints"]["budget_max"] = 30  # budget the draft ignored
    out = critic_node(s)
    v = out["critic"]
    assert not v["approved"] and out["revision_count"] == 1
    assert any("d-pricey" in x for x in v["constraint_violations"])
    s.update(out)
    s = _run(s)  # revision: the flagged product is dropped
    assert [r["doc_id"] for r in s["comparison_table"]] == ["d-game"]
    assert critic_node(s)["critic"]["approved"]


def test_critic_rejects_uncited_and_invented_facts():
    s = _run(_state([GAME]))
    s["final_answer"] = "Family Card Game Night Edition costs $9.99 and has 4.2 stars."
    v = critic_node(s)["critic"]
    assert not v["approved"]
    assert v["missing_citations"], "no markers in the text"
    assert any("$9.99" in x for x in v["unsupported_claims"])
    assert any("4.2" in x for x in v["unsupported_claims"])


def test_critic_rejects_phantom_citation_and_unknown_marker():
    s = _run(_state([GAME]))
    s["citations"][0]["doc_id"] = "not-retrieved"
    s["final_answer"] += " See also [7]."
    v = critic_node(s)["critic"]
    assert any("not-retrieved" in x for x in v["unsupported_claims"])
    assert any("[7]" in x for x in v["unsupported_claims"])


def test_critic_flags_over_age_product_as_safety_issue():
    s = _run(_state([PRICEY]))  # picked without an age constraint
    s["constraints"]["child_age_years"] = 6
    v = critic_node(s)["critic"]
    assert any("ages 10+" in x for x in v["safety_issues"])


def test_table_keeps_only_products_the_answer_cites():
    from agent.nodes.answerer import build_table, keep_cited
    picks = [(GAME[1], GAME[0]), (PRICEY[1], PRICEY[0]), (STACKER[1], STACKER[0])]
    rows, citations = build_table(picks)
    picks2, rows2, cits2 = keep_cited("Try the card game [1] or the rings [3].", picks, rows, citations)
    assert [r["doc_id"] for r in rows2] == ["d-game", "d-stack"]
    assert [r["rank"] for r in rows2] == [1, 2]
    assert {c["marker"] for c in cits2} == {"[1]", "[3]"}
    # an answer with no markers keeps everything (the Critic reports it)
    assert keep_cited("No markers here.", picks, rows, citations)[1] == rows


def test_llm_review_issues_must_quote_the_draft_and_skip_code_checked_facts():
    from agent.nodes.critic import CriticReview, filter_review
    review = CriticReview(issues=[
        {"kind": "unsupported_claim", "quote": "made from BPA-free plastic", "problem": "[1] evidence has no BPA."},
        {"kind": "safety_issue", "quote": "not in the text at all", "problem": "[1] drops a warning."},
        {"kind": "safety_issue", "quote": "ages 7 and up", "problem": "Recommends [1] (age 7+) for a 6-year-old."},
    ])
    answer = "UNO is made from BPA-free plastic, ages 7 and up [1]."
    unsupported, safety, dropped = filter_review(review, answer, "")
    assert len(unsupported) == 1 and "BPA" in unsupported[0]
    assert safety == []
    assert [d["why"] for d in dropped] == ["quote not found in the draft", "code-checked fact"]


def test_llm_answer_without_markers_falls_back_to_cited_template(monkeypatch):
    import agent.nodes.answerer as ans

    class Settings:
        provider = "openai"
    monkeypatch.setattr(ans, "get_llm_settings", lambda node: Settings())
    monkeypatch.setattr(ans, "llm_answer", lambda *a: ("A great pick with no markers.", "Spoken.", {}))
    s = ans.answerer_node(_state([GAME]))
    assert "[1]" in s["final_answer"]
    assert s["step_log"][0]["details"]["source"].startswith("template")


def test_left_out_filler_is_removed():
    from agent.nodes.answerer import drop_filler
    assert drop_filler("Two games [1][2].\nI left out no products.\nWant more?", []) == "Two games [1][2].\nWant more?"
