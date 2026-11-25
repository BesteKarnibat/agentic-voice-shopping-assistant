"""Build the ProofAgent inputs from the repo (#55). Owner: Beste.

Generated, not committed, so they always match what the agent actually runs:

    data/proofagent/context/system_prompt.md   every LLM prompt the agent uses (from prompts/)
    data/proofagent/context/tools.json         rag.search / web.search schemas (from contracts/tool_schemas.py)
    data/proofagent/context/agent.yaml         role, goal, business case (copied from eval/agent.yaml)
    data/proofagent/knowledge/catalog.md       the catalog the agent is grounded on

    uv run python -m eval.build_context                 # real catalog (products.parquet)
    EVAL_CATALOG=mock uv run python -m eval.build_context
"""

from __future__ import annotations

import json
import shutil
import sys

from agent.prompts import prompt_section, system_prompt_for
from config import eval as cfg
from config.paths import EVAL_CONTEXT_DIR, EVAL_KNOWLEDGE_DIR, PRODUCTS_PARQUET, ROOT
from contracts.tool_schemas import TOOLS

NODE_PROMPTS = (("Router", "router_system"), ("Planner", "planner_system"),
                ("Answerer", "answerer_system"), ("Critic", "critic_system"))


def system_prompt() -> str:
    guardrails = prompt_section("guardrails")
    parts = ["# Toy shopping assistant: system prompts\n",
             "The agent is a LangGraph pipeline. Each LLM node gets the shared system prompt plus its own prompt."]
    for title, name in NODE_PROMPTS:
        values = {"guardrails": guardrails} if "{{guardrails}}" in prompt_section(name) else {}
        parts.append(f"\n## {title} node\n\n{system_prompt_for(name, **values)}")
    return "\n".join(parts) + "\n"


def tools() -> list[dict]:
    return [{"type": "function", "function": {"name": name, "description": spec["description"],
                                              "parameters": spec["input"].model_json_schema()}}
            for name, spec in TOOLS.items()]


def _product_line(p: dict) -> str:
    facts = [f"doc_id {p['doc_id']}", p.get("brand") and f"brand {p['brand']}",
             p.get("price") is not None and f"price ${p['price']:.2f}",
             p.get("rating") is not None and f"rating {p['rating']}",
             p.get("min_age_years") is not None and f"min age {p['min_age_years']:g}",
             p.get("max_age_years") is not None and f"max age {p['max_age_years']:g}",
             p.get("safety_warnings") and "warnings: " + "; ".join(p["safety_warnings"]),
             p.get("features_snippet") or p.get("features")]
    return f"- **{p['title']}**: " + " | ".join(str(f) for f in facts if f)


def catalog_products() -> list[dict]:
    if cfg.CATALOG == "mock":
        from mocks.fake_catalog import FAKE_PRODUCTS
        return FAKE_PRODUCTS
    if not PRODUCTS_PARQUET.exists():
        sys.exit(f"{PRODUCTS_PARQUET} not found. Run `uv run doit preprocess` first, or set EVAL_CATALOG=mock.")
    import polars as pl
    df = pl.read_parquet(PRODUCTS_PARQUET)
    if "doc_id" not in df.columns and "id" in df.columns:
        df = df.rename({"id": "doc_id"})
    for col in ("safety_warnings",):
        if col in df.columns and df[col].dtype == pl.Utf8:
            df = df.with_columns(pl.col(col).map_elements(lambda s: [s] if s else None, return_dtype=pl.List(pl.Utf8)))
    return df.to_dicts()


def knowledge_md(products: list[dict]) -> str:
    head = (f"# Product catalog ({'mock' if cfg.CATALOG == 'mock' else 'Amazon Product Dataset 2020, Toys & Games'})\n\n"
            "The only product facts the agent may state come from this catalog (cited by doc_id) or from live web "
            "results (cited by URL). Prices are 2020 catalog prices unless the answer says it used a live price.\n\n")
    return head + "\n".join(_product_line(p) for p in products) + "\n"


def build() -> None:
    EVAL_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_CONTEXT_DIR / "system_prompt.md").write_text(system_prompt(), encoding="utf-8")
    (EVAL_CONTEXT_DIR / "tools.json").write_text(json.dumps(tools(), indent=2), encoding="utf-8")
    shutil.copy(ROOT / "eval" / "agent.yaml", EVAL_CONTEXT_DIR / "agent.yaml")
    products = catalog_products()
    (EVAL_KNOWLEDGE_DIR / "catalog.md").write_text(knowledge_md(products), encoding="utf-8")
    print(f"Context → {EVAL_CONTEXT_DIR} | knowledge → {EVAL_KNOWLEDGE_DIR} "
          f"({len(products)} products, catalog={cfg.CATALOG})")


if __name__ == "__main__":
    build()
