"""LangGraph workflow (#17, #31). Owner: Devanshu. See docs/components/langgraph.md.

router → refuse | clarify | planner → retriever → reconcile → answerer ⇄ critic → finalize
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

# Swap for Beste's real nodes here (#48).
from agent.nodes.answerer_stub import answerer_node, critic_node
from agent.nodes.planner import planner_node
from agent.nodes.reconcile import reconcile_node
from agent.nodes.respond import clarify_node, refuse_node
from agent.nodes.retriever import retriever_node
from agent.nodes.router import router_node
from contracts.state import MAX_CRITIC_REVISIONS, AgentState, log_step


def route_after_router(state: AgentState) -> str:
    intent = state.get("intent")
    if intent in ("unsafe", "out_of_scope") or not (state.get("safety") or {}).get("is_safe", True):
        return "refuse"
    if intent == "unclear":
        return "clarify"
    return "planner"


def route_after_critic(state: AgentState) -> str:
    """At most MAX_CRITIC_REVISIONS rewrites."""
    if (state.get("critic") or {}).get("approved", True):
        return "finalize"
    if state.get("revision_count", 0) > MAX_CRITIC_REVISIONS:
        return "finalize"
    return "answerer"


def finalize_node(state: AgentState) -> dict:
    critic = state.get("critic") or {}
    approved = critic.get("approved", True)
    summary = (f"done: {len(state.get('comparison_table') or [])} products, "
               f"{len(state.get('citations') or [])} citations, revisions={state.get('revision_count', 0)}")
    out = log_step("finalize", summary if approved else summary + " (critic never approved; returning last draft)",
                   critic_approved=approved)
    if not approved:
        out["errors"] = [f"critic: not approved after {MAX_CRITIC_REVISIONS} revisions: {critic.get('feedback', '')}"]
    return out


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("router", router_node)
    g.add_node("refuse", refuse_node)
    g.add_node("clarify", clarify_node)
    g.add_node("planner", planner_node)
    g.add_node("retriever", retriever_node)
    g.add_node("reconcile", reconcile_node)
    g.add_node("answerer", answerer_node)
    g.add_node("critic", critic_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "router")
    g.add_conditional_edges("router", route_after_router,
                            {"refuse": "refuse", "clarify": "clarify", "planner": "planner"})
    g.add_edge("refuse", END)
    g.add_edge("clarify", END)
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "reconcile")
    g.add_edge("reconcile", "answerer")
    g.add_edge("answerer", "critic")
    g.add_conditional_edges("critic", route_after_critic, {"answerer": "answerer", "finalize": "finalize"})
    g.add_edge("finalize", END)
    return g.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()
