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
