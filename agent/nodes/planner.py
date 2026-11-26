"""Planner node (#33): pick rag.search / web.search and build the plan.

Prompts: system.md + planner_system.md. Filters and the web trigger are enforced in code.
"""

from __future__ import annotations

import json

from agent.llm import invoke_structured
from agent.prompts import system_prompt_for
from agent.schemas import PlannerDraft
from config.graph import DEFAULT_TOP_K
from contracts.state import AgentState, Plan, log_step


def rag_filters_from(constraints: dict) -> dict:
    """Constraints → RagSearchInput filters. Free-text category goes in the query instead."""
    filters = {
        "min_price": constraints.get("budget_min"),
        "max_price": constraints.get("budget_max"),
        "brand": constraints.get("brand"),
        "min_rating": constraints.get("min_rating"),
        "child_age_years": constraints.get("child_age_years"),
        "exclude_features": constraints.get("exclude_features") or None,
    }
    return {k: v for k, v in filters.items() if v is not None}


def planner_node(state: AgentState) -> dict:
    transcript = state.get("transcript", "")
    intent = state.get("intent", "product_search")
    constraints = state.get("constraints") or {}
    user = json.dumps({"transcript": transcript, "intent": intent, "constraints": constraints}, indent=2)
    errors: list[str] = []
    meta: dict = {}
    try:
        draft, meta = invoke_structured("planner", PlannerDraft, system_prompt_for("planner_system"), user,
                                        fake_input={"transcript": transcript, "intent": intent,
                                                    "constraints": constraints})
    except Exception as e:  # noqa: BLE001
        errors.append(f"planner: LLM call failed, using fallback plan: {e}")
        draft = PlannerDraft(rag_query=" ".join(filter(None, [constraints.get("category"), transcript]))[:200],
                             use_web=False, comparison_criteria=["price", "rating"],
                             reasoning="Fallback plan (planner LLM failed): catalog search on the transcript.")

    rag_query = draft.rag_query.strip() or transcript
    if constraints.get("category") and constraints["category"].lower() not in rag_query.lower():
        rag_query = f"{constraints['category']} {rag_query}"
    forced_web = bool(constraints.get("wants_current_info")) or intent == "price_check"
    use_web = draft.use_web or forced_web
    reasoning = draft.reasoning
    if forced_web and not draft.use_web:
        reasoning += " (web.search added: the user asked for current price/availability.)"
    criteria = list(dict.fromkeys(draft.comparison_criteria or ["price", "rating"]))
    if use_web and "availability" not in criteria:
        criteria.append("availability")

    plan: Plan = {
        "use_rag": True,
        "use_web": use_web,
        "rag_query": rag_query,
        "rag_filters": rag_filters_from(constraints),
        "web_query": (draft.web_query or f"{rag_query} price") if use_web else None,
        "comparison_criteria": criteria,
        "top_k": DEFAULT_TOP_K,
        "reasoning": reasoning,
    }
    tools = "rag.search + web.search" if use_web else "rag.search only"
    out = {"plan": plan, **log_step("planner", f"{tools}: {reasoning}", plan=plan, **meta)}
    if errors:
        out["errors"] = errors
    return out
