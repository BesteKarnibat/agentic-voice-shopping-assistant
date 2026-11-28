"""Unit tests: LLM config, prompts, reconciliation, Critic loop wiring, MCP discovery, failure handling."""

import asyncio

import pytest

from agent.nodes.reconcile import reconcile_product
from mocks.fake_catalog import FAKE_PRODUCTS, FAKE_WEB_RESULTS

PRODUCTS = {p["doc_id"]: p for p in FAKE_PRODUCTS}


# ---------------------------------------------------------------- model-agnostic config (#16)

def test_llm_settings_from_env(monkeypatch):
    from config.llm import get_llm_settings
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    s = get_llm_settings("router")
    assert (s.provider, s.model, s.temperature) == ("anthropic", "claude-haiku-5-5", 0.2)
    assert get_llm_settings("spoken_summary").max_tokens == 220
    monkeypatch.setenv("LLM_MODEL", "some-other-model")
    monkeypatch.setenv("LLM_MAX_TOKENS_PLANNER", "123")
    assert get_llm_settings("planner").model == "some-other-model"
    assert get_llm_settings("planner").max_tokens == 123


@pytest.mark.parametrize("provider,cls_name", [("openai", "ChatOpenAI"), ("anthropic", "ChatAnthropic")])
def test_provider_swap_is_config_only(monkeypatch, provider, cls_name):
    """Builds the client object only: no network call, dummy key."""
    from agent.llm import get_chat_model
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", "test-dummy-key")
    model = get_chat_model("router")
    assert type(model).__name__ == cls_name
    assert model.with_structured_output is not None


# ---------------------------------------------------------------- prompts (#60)

def test_prompts_load_without_placeholders():
    from agent.prompts import load_prompt, prompt_section, system_prompt_for
    router = system_prompt_for("router_system", guardrails=prompt_section("guardrails"))
    assert "Your job: Router" in router and "injury_emergency" in router and "{{" not in router
    assert "Your job: Planner" in load_prompt("planner_system")


def test_guardrail_templates_parsed_from_betes_file():
    from agent.prompts import guardrail_templates
    t = guardrail_templates()
    assert {"injury_emergency", "harmful_use", "minor_exploitation", "prompt_injection", "out_of_scope"} <= set(t)
    assert "911" in t["injury_emergency"]


# ---------------------------------------------------------------- reconciliation (#49)

def test_sku_match_no_conflict():
    r = reconcile_product(PRODUCTS["amz-fake-001"], FAKE_WEB_RESULTS, prefer_live=False)
    assert r["match_method"] == "sku" and r["match_score"] == 1.0
    assert not r["price_conflict"] and r["price_source"] == "catalog"


def test_same_brand_different_product_does_not_match():
    connect4 = PRODUCTS["amz-fake-011"]
    monopoly_listing = [w for w in FAKE_WEB_RESULTS if "monopoly" in w["url"]]
    r = reconcile_product(connect4, monopoly_listing, prefer_live=True)
    assert r["match_method"] == "none" and r["live_price"] is None and r["price_source"] == "catalog"


def test_out_of_stock_and_conflict_noted():
    r = reconcile_product(PRODUCTS["amz-fake-002"], FAKE_WEB_RESULTS, prefer_live=True)
    assert r["availability"] == "out_of_stock" and r["price_conflict"]
    assert "out of stock" in r["note"]


VOILA = {"doc_id": "x1", "sku": "B01B2O2NS4", "brand": "Brain", "price": 15.59,
         "title": "Brain Games Voila! Board Game - A Fast and Fun Family Board Game - Play with Kids, Teenagers "
                  "and Adults - Award Winning Games for Children, Families & Casual Gamers"}
EBAY_VOILA = {"title": "Voilà! Board Game VOILA 2015 Brain Games - New / Sealed", "url": "https://www.ebay.com/itm/1",
              "snippet": "Brain Games Voila $2.99 Buy It Now", "source_domain": "ebay.com", "price": 2.99,
              "availability": "unknown"}
WALMART_VOILA = {"title": "Voila - Family Board Game", "url": "https://www.walmart.com/ip/Voila-Family-Board-Game/1",
                 "snippet": "Brain Games Voila! ... current price $9.84", "source_domain": "walmart.com",
                 "price": 9.84, "availability": "unknown"}


def test_long_marketing_title_still_matches_and_retailer_beats_marketplace():
    r = reconcile_product(VOILA, [EBAY_VOILA, WALMART_VOILA], prefer_live=True)
    assert r["match_method"] == "brand_title" and "walmart.com" in r["live_url"]
    assert r["chosen_price"] == 9.84 and r["price_conflict"]


def test_implausible_live_price_is_not_used():
    r = reconcile_product(VOILA, [EBAY_VOILA], prefer_live=True)
    assert r["live_price"] == 2.99 and r["chosen_price"] == 15.59 and r["price_source"] == "catalog"
    assert "different listing" in r["note"]


def test_catalog_price_kept_when_user_did_not_ask_for_current_info():
    r = reconcile_product(PRODUCTS["amz-fake-006"], FAKE_WEB_RESULTS, prefer_live=False)
    assert r["price_conflict"] and r["chosen_price"] == 19.99 and r["price_source"] == "catalog"
    assert "catalog price (2020)" in r["note"] and "current price at" in r["note"]


# Beste's v1b report T23: a Walmart category page ($14.97) was taken as the live price of Crayola Dough ($8.99).
CRAYOLA = {"doc_id": "c1", "sku": "B07FQ4N4PB", "brand": "Crayola", "price": 8.99,
           "title": "Crayola Dough, 3 lbs., Red, Modeling Dough for Kids"}
CRAYOLA_BROWSE = {"title": "Crayola Dough Clay and Slime | Multicolor", "source_domain": "walmart.com",
                  "url": "https://www.walmart.com/browse/arts-crafts/crayola-dough-clay-and-slime/1334134_5899871",
                  "snippet": "Shop Crayola Dough at Walmart. From $14.97", "price": 14.97, "availability": "unknown"}
CRAYOLA_PAGE = {"title": "Crayola Dough, 3 lbs., Red", "source_domain": "walmart.com",
                "url": "https://www.walmart.com/ip/Crayola-Dough-3-lbs-Red/123456789",
                "snippet": "Crayola Dough 3 lbs Red $9.47", "price": 9.47, "availability": "in_stock"}


def test_category_page_is_never_matched():
    r = reconcile_product(CRAYOLA, [CRAYOLA_BROWSE], prefer_live=True)
    assert r["match_method"] == "none" and r["live_price"] is None and r["live_url"] is None
    assert r["chosen_price"] == 8.99 and r["note"] == "Price: $8.99 catalog price (2020)."


def test_product_page_wins_over_category_page():
    r = reconcile_product(CRAYOLA, [CRAYOLA_BROWSE, CRAYOLA_PAGE], prefer_live=True)
    assert r["live_url"] == CRAYOLA_PAGE["url"] and r["chosen_price"] == 9.47 and r["price_source"] == "web"
    assert r["note"] == "Price: $9.47 current price at walmart.com."


@pytest.mark.parametrize("url,ok", [
    ("https://www.walmart.com/ip/Voila-Family-Board-Game/335200377", True),
    ("https://www.amazon.com/dp/B00NHQFA1I", True),
    ("https://www.amazon.com/clp/B002SQBB3O", True),
    ("https://www.amazon.com/gp/aw/d/B000PHQLME/ref=mp_s_a_1_1?qid=1386033423", True),
    ("https://www.target.com/p/connect-4-classic-grid/-/A-22222222", True),
    ("https://www.ebay.com/itm/267093687015", True),
    ("https://www.barnesandnoble.com/w/tsuro-by-tom-mcmurchie-calliope-games/1146366358", True),
    ("https://www.walmart.com/browse/toys/jigsaw-puzzles/cardinal/4171_4191_163840_4981610", False),
    ("https://business.walmart.com/search?q=TOMY%20Games", False),
    ("https://www.amazon.com/Toys-Games-Calliope/s?rh=n%3A165793011", False),
    ("https://www.amazon.com/s?k=crayola+dough", False),
    ("https://www.amazon.com/b?ie=UTF8&node=17462647011", False),
    ("https://www.amazon.com/stores/FoxMind/page/23719D87", False),
    ("https://www.target.com/s/crayola+dough", False),
    ("https://www.target.com/c/play-dough/-/N-5xt9t", False),
    ("https://www.nytimes.com/wirecutter/reviews/best-family-board-games/", False),
    ("https://example.com/about", False),
    (None, False),
])
def test_is_product_page(url, ok):
    from agent.nodes.reconcile import is_product_page
    assert is_product_page(url) is ok


def test_price_labels_in_notes():
    live = reconcile_product(VOILA, [WALMART_VOILA], prefer_live=True)
    assert "$9.84 current price at walmart.com" in live["note"]
    assert "Price conflict: $9.84 current price at walmart.com vs $15.59 catalog price (2020)" in live["note"]
    no_live = reconcile_product(VOILA, [], prefer_live=False)
    assert no_live["note"] == "Price: $15.59 catalog price (2020)."


# ---------------------------------------------------------------- Critic loop (#17)

def test_route_after_critic():
    from agent.graph import route_after_critic
    from contracts.state import MAX_CRITIC_REVISIONS
    assert route_after_critic({"critic": {"approved": True}, "revision_count": 0}) == "finalize"
    assert route_after_critic({"critic": {"approved": False}, "revision_count": 1}) == "answerer"
    assert route_after_critic({"critic": {"approved": False}, "revision_count": MAX_CRITIC_REVISIONS}) == "answerer"
    assert route_after_critic({"critic": {"approved": False}, "revision_count": MAX_CRITIC_REVISIONS + 1}) == "finalize"


def test_critic_loop_caps_revisions(monkeypatch):
    """A Critic that always rejects → Answerer runs 1 + MAX_CRITIC_REVISIONS times, then finalize with an error."""
    import agent.graph as graph_mod
    from contracts.state import MAX_CRITIC_REVISIONS, log_step

    def always_reject(state):
        verdict = {"approved": False, "unsupported_claims": ["x"], "missing_citations": [],
                   "constraint_violations": [], "safety_issues": [], "feedback": "try again"}
        return {"critic": verdict, "revision_count": state.get("revision_count", 0) + 1,
                **log_step("critic", "rejected")}

    monkeypatch.setattr(graph_mod, "critic_node", always_reject)
    g = graph_mod.build_graph()
    state = asyncio.run(g.ainvoke({"transcript": "Recommend a card game for family night.",
                                   "revision_count": 0, "step_log": [], "errors": []}))
    names = [e["node"] for e in state["step_log"]]
    assert names.count("answerer") == 1 + MAX_CRITIC_REVISIONS
    assert names[-1] == "finalize"
    assert any("not approved" in e for e in state["errors"])


# ---------------------------------------------------------------- MCP (#20, #44)

def test_mcp_discovery_matches_contract():
    from agent.mcp_client import MCPToolClient, cfg_args
    from config.graph import MCP_SERVER_COMMAND
    from contracts.tool_schemas import TOOLS

    async def go():
        client = MCPToolClient(MCP_SERVER_COMMAND, cfg_args().split())
        await client.start()
        try:
            listed = await client._session.list_tools()
            return {t.name: t for t in listed.tools}
        finally:
            await client.aclose()

    tools = asyncio.run(go())
    assert set(tools) == {"rag.search", "web.search"}
    for name, spec in TOOLS.items():
        assert tools[name].inputSchema == spec["input"].model_json_schema()
        assert tools[name].description == spec["description"]


def test_mcp_server_down_is_reported_not_raised(monkeypatch):
    from agent import run_agent
    monkeypatch.setenv("MCP_SERVER_ARGS", "-m mocks.does_not_exist")
    s = run_agent("Recommend a card game for family night.")
    assert any("MCP server unavailable" in e for e in s["errors"])
    assert s["final_answer"] and s["comparison_table"] == []
