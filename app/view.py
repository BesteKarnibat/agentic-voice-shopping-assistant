"""Pure helpers that turn an AgentState into display-ready data (no Streamlit here, so testable)."""
from __future__ import annotations

from typing import Any


TABLE_TOP_N = 3  # deliverables.md 1.4: top 3, Product | Price | Rating | Ingredients | Source | Citation

_SOURCE_LABEL = {"catalog": "Catalog", "web": "Live web", "unknown": "Unknown"}


def comparison_rows(state: dict, top_n: int = TABLE_TOP_N) -> list:
    """Rows for the comparison table: top `top_n` products by rank, in the agreed columns."""
    table = sorted(state.get("comparison_table") or [], key=lambda r: r.get("rank") or 10**6)
    rows = []
    for r in table[:top_n]:
        price = r.get("price")
        rows.append({
            "Product": r.get("title"),
            "Price": f"${price:.2f}" if price is not None else "n/a",
            "Rating": r.get("rating") if r.get("rating") is not None else "n/a",
            "Ingredients": ", ".join(r["ingredients"]) if r.get("ingredients") else "unknown",
            "Source": _SOURCE_LABEL.get(r.get("price_source") or "unknown", r.get("price_source")),
            "Citation": " ".join(r.get("citation_markers") or []),
        })
    return rows


def reply_text(state: dict) -> str:
    """What the assistant says in the chat: the answer (incl. refusals), else the clarifying question."""
    return state.get("final_answer") or state.get("clarification_question") or ""


def route_summary(state: dict) -> str:
    """One markdown line on intent and safety, or '' if the Router hasn't run."""
    parts = []
    if state.get("intent"):
        parts.append(f"Intent: `{state['intent']}`")
    safety = state.get("safety") or {}
    if safety:
        if safety.get("is_safe") is False:
            parts.append(f"Safety: blocked ({safety.get('category') or 'unsafe'})"
                         + (f": {safety['reason']}" if safety.get("reason") else ""))
        else:
            parts.append("Safety: passed")
    if state.get("clarification_question"):
        parts.append(f"Asked to clarify: _{state['clarification_question']}_")
    return "  \n".join(parts)


def split_citations(state: dict) -> tuple:
    """(private_citations, web_citations) from state['citations']."""
    cites = state.get("citations") or []
    return ([c for c in cites if c.get("source_type") == "private"],
            [c for c in cites if c.get("source_type") == "web"])


def private_doc_ids(state: dict) -> list:
    """Unique catalog doc_ids used as evidence (citations, table, retrieval), in order."""
    seen: dict = {}
    for c in split_citations(state)[0]:
        seen.setdefault(c.get("doc_id"), None)
    for r in state.get("comparison_table") or []:
        seen.setdefault(r.get("doc_id"), None)
    return [d for d in seen if d]


def live_links(state: dict) -> list:
    """Unique live URLs with a title, from web citations, the table and web results."""
    out: dict = {}
    for c in split_citations(state)[1]:
        if c.get("url"):
            out.setdefault(c["url"], c.get("title") or c["url"])
    for r in state.get("comparison_table") or []:
        if r.get("live_url"):
            out.setdefault(r["live_url"], r.get("title") or r["live_url"])
    for w in state.get("web_results") or []:
        if w.get("url"):
            out.setdefault(w["url"], w.get("title") or w["url"])
    return [{"url": u, "title": t} for u, t in out.items()]


def step_rows(state: dict) -> list:
    """Step-log entries as (time, node, summary, details) for the trace panel."""
    rows = []
    for e in state.get("step_log") or []:
        ts = (e.get("timestamp") or "")[11:19]
        rows.append({"time": ts, "node": e.get("node", "?"),
                     "summary": e.get("summary", ""), "details": e.get("details") or {}})
    return rows


def has_answer(state: dict) -> bool:
    return bool(state.get("final_answer"))


def safe_get(state: dict, key: str, default: Any = None) -> Any:
    v = state.get(key)
    return default if v is None else v
