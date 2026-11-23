"""Placeholder Answerer and Critic (no LLM). Beste replaces these (#46, #47, #48).

Interface the real nodes must match (swap the import in agent/graph.py):

    answerer_node(state) -> draft_answer, final_answer, comparison_table (top 3),
                            citations, spoken_summary (<= ~40 words, no [n]) + log_step
    critic_node(state)   -> critic (CriticVerdict), revision_count (+1 when rejected) + log_step

On a revision the Answerer reads critic["feedback"]. Use agent.llm for the model.
"""

from __future__ import annotations

import re

from config.graph import SPOKEN_SUMMARY_MAX_WORDS, TOP_N_ANSWER
from contracts.state import AgentState, Citation, ComparisonRow, log_step


def _short(title: str, n: int = 6) -> str:
    base = re.split(r" - |, | \(|:", title)[0]
    words = base.split()
    return " ".join(words[:n])


def _age_range(p: dict) -> str | None:
    lo, hi = p.get("min_age_years"), p.get("max_age_years")
    if lo is None and hi is None:
        return None
    fmt = lambda x: f"{x:g}"  # noqa: E731
    if hi is None or hi >= 99:
        return f"{fmt(lo)}+ years"
    return f"{fmt(lo or 0)}-{fmt(hi)} years"


def _limit_words(text: str, n: int) -> str:
    words = text.split()
    return text if len(words) <= n else " ".join(words[:n]).rstrip(",.;") + "."


def answerer_node(state: AgentState) -> dict:
    constraints = state.get("constraints") or {}
    budget = constraints.get("budget_max")
    age = constraints.get("child_age_years")
    rag_by_id = {p["doc_id"]: p for p in state.get("rag_results") or []}
    rejected = " ".join((state.get("critic") or {}).get("constraint_violations") or [])

    picks, skipped = [], []
    for r in state.get("reconciled") or []:
        if r["doc_id"] in rejected:
            continue
        if budget is not None and r["chosen_price"] is not None and r["chosen_price"] > budget:
            skipped.append(f"{_short(r['title'])} is now ${r['chosen_price']:.2f}, over your ${budget:g} budget")
            continue
        picks.append(r)
    picks.sort(key=lambda r: r.get("availability") == "out_of_stock")
    picks = picks[:TOP_N_ANSWER]

    citations: list[Citation] = []
    rows: list[ComparisonRow] = []
    lines: list[str] = []
    for rank, r in enumerate(picks, start=1):
        p = rag_by_id.get(r["doc_id"], {})
        markers = []
        citations.append({"marker": f"[{len(citations) + 1}]", "source_type": "private", "doc_id": r["doc_id"],
                          "url": None, "title": r["title"]})
        markers.append(citations[-1]["marker"])
        if r.get("live_url"):
            citations.append({"marker": f"[{len(citations) + 1}]", "source_type": "web", "doc_id": None,
                              "url": r["live_url"], "title": f"Live listing: {_short(r['title'])}"})
            markers.append(citations[-1]["marker"])
        rows.append({"rank": rank, "title": r["title"], "brand": r.get("brand"), "price": r["chosen_price"],
                     "price_source": r["price_source"], "rating": p.get("rating"), "age_range": _age_range(p),
                     "safety_warnings": p.get("safety_warnings"), "doc_id": r["doc_id"],
                     "live_url": r.get("live_url"), "citation_markers": markers})
        price = f"${r['chosen_price']:.2f} ({r['price_source']})" if r["chosen_price"] is not None else "price not listed"
        bits = [price]
        if p.get("rating") is not None:
            bits.append(f"{p['rating']} stars")
        if _age_range(p):
            bits.append(f"ages {_age_range(p)}")
        line = f"{rank}. {r['title']}: " + ", ".join(bits) + " " + "".join(markers)
        if p.get("safety_warnings"):
            line += f". Listing warnings: {'; '.join(p['safety_warnings'])}"
        if r.get("note"):
            line += f". {r['note']}"
        lines.append(line)

    if picks:
        answer = f"Here {'are' if len(picks) > 1 else 'is'} the top {len(picks)} option{'s' if len(picks) > 1 else ''}:\n" + "\n".join(lines)
        if skipped:
            answer += "\nLeft out: " + "; ".join(skipped) + "."
        if (age is not None and age < 3) or any(rag_by_id.get(r["doc_id"], {}).get("safety_warnings") for r in picks):
            answer += "\nCheck the age grade and warnings on the package."
        top = picks[0]
        spoken = f"My top pick is {_short(top['title'])}"
        if top["chosen_price"] is not None:
            spoken += f" at ${top['chosen_price']:.2f}"
        spoken += "."
        if top.get("price_conflict"):
            spoken += " Its live price differs from our catalog."
        if len(picks) > 1:
            spoken += f" I also found {len(picks) - 1} more option{'s' if len(picks) > 2 else ''}."
        spoken += " Details and sources are on screen."
    else:
        answer = "I couldn't find a product in our catalog that matches all of your requirements."
        if skipped:
            answer += " " + "; ".join(skipped) + "."
        answer += " Want me to try a different budget or type of toy?"
        spoken = _limit_words(answer, SPOKEN_SUMMARY_MAX_WORDS)

    spoken = _limit_words(re.sub(r"\[\d+\]", "", spoken), SPOKEN_SUMMARY_MAX_WORDS)
    return {"draft_answer": answer, "final_answer": answer, "comparison_table": rows, "citations": citations,
            "spoken_summary": spoken,
            **log_step("answerer", f"[STUB] {len(rows)} products, {len(citations)} citations"
                       + (f", revision {state.get('revision_count', 0)}" if state.get("revision_count") else ""),
                       doc_ids=[r["doc_id"] for r in rows], skipped=skipped)}


def critic_node(state: AgentState) -> dict:
    constraints = state.get("constraints") or {}
    budget = constraints.get("budget_max")
    age = constraints.get("child_age_years")
    rag_by_id = {p["doc_id"]: p for p in state.get("rag_results") or []}
    violations, missing = [], []
    for row in state.get("comparison_table") or []:
        tag = f"[{row['rank']}] ({row['doc_id']})"
        if not row.get("citation_markers"):
            missing.append(f"Product {tag} has no citation.")
        if budget is not None and row.get("price") is not None and row["price"] > budget:
            violations.append(f"Product {tag} is ${row['price']:.2f}, budget is ${budget:g}.")
        min_age = rag_by_id.get(row["doc_id"], {}).get("min_age_years")
        if age is not None and min_age is not None and min_age > age:
            violations.append(f"Product {tag} is for ages {min_age:g}+, child is {age:g}.")
    approved = not (violations or missing)
    verdict = {"approved": approved, "unsupported_claims": [], "missing_citations": missing,
               "constraint_violations": violations, "safety_issues": [],
               "feedback": "" if approved else "Fix: " + " ".join(violations + missing)}
    revision = state.get("revision_count", 0) + (0 if approved else 1)
    return {"critic": verdict, "revision_count": revision,
            **log_step("critic", f"[STUB] {'approved' if approved else 'rejected'}"
                       + ("" if approved else f": {len(violations) + len(missing)} issue(s)"), verdict=verdict)}
