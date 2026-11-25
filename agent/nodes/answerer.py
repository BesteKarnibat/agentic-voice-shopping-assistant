"""Answerer node (#46). Owner: Beste. See prompts/answerer_system.md.

Code chooses the products and builds `comparison_table` and `citations` from the retrieved evidence, so every
citation points at a real `doc_id` or `url`. The LLM only writes `final_answer` and `spoken_summary` from that
evidence. With the fake provider, with no matching products, or if the LLM call fails, a fixed template is used.

On a revision the node reads `critic`: products named in the Critic's issues are dropped and the feedback is
passed to the LLM.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from agent.llm import invoke_structured
from agent.nodes.reconcile import short_title
from agent.prompts import prompt_section, system_prompt_for
from config.graph import SPOKEN_SUMMARY_MAX_WORDS, TOP_N_ANSWER
from config.llm import get_llm_settings
from contracts.state import AgentState, Citation, ComparisonRow, log_step

WARNING_NOTE = "Check the age grade and warnings on the package."
SPOKEN_WARNING = "Please check the package warnings."
SMALL_PARTS_WORDS = ("small part", "choking")
MARKER_RE = re.compile(r"\[\d+\]")


class AnswerDraft(BaseModel):
    """LLM output for the Answerer."""

    answer: str = Field(..., description="On-screen answer with the given [n] citation markers after each fact.")
    spoken_summary: str = Field(..., description="At most 35 words, no citation markers, for text-to-speech.")


# ---------------------------------------------------------------- helpers

def age_range(p: dict) -> str | None:
    lo, hi = p.get("min_age_years"), p.get("max_age_years")
    if lo is None and hi is None:
        return None
    fmt = lambda x: f"{x:g}"  # noqa: E731
    if hi is None or hi >= 99:
        return f"{fmt(lo)}+ years"
    return f"{fmt(lo or 0)}-{fmt(hi)} years"


def limit_words(text: str, n: int) -> str:
    words = text.split()
    return text if len(words) <= n else " ".join(words[:n]).rstrip(",.;:") + "."


def clean_spoken(text: str, needs_warning: bool) -> str:
    text = " ".join(MARKER_RE.sub("", text).split())
    if needs_warning and "warning" not in text.lower():
        budget = SPOKEN_SUMMARY_MAX_WORDS - len(SPOKEN_WARNING.split())
        return limit_words(text, budget) + " " + SPOKEN_WARNING
    return limit_words(text, SPOKEN_SUMMARY_MAX_WORDS)


def _mentions(text: str | None, words) -> bool:
    low = (text or "").lower()
    return any(w in low for w in words)


def flagged_doc_ids(critic: dict, known_ids) -> set[str]:
    """doc_ids named in the Critic's issues (the Answerer drops them on a revision)."""
    # Only constraint and safety problems remove a product; wording problems are fixed by rewriting.
    issues = " ".join((critic.get("constraint_violations") or []) + (critic.get("safety_issues") or []))
    return {d for d in known_ids if d in issues}


# ---------------------------------------------------------------- product choice

def select_products(state: AgentState) -> tuple[list[tuple[dict, dict]], list[str], list[str]]:
    """(picks as (reconciled, rag product), user-facing reasons for left-out products, doc_ids dropped on critic's request)."""
    c = state.get("constraints") or {}
    budget, age = c.get("budget_max"), c.get("child_age_years")
    min_rating = c.get("min_rating")
    excluded = [e.lower() for e in c.get("exclude_features") or []]
    rag_by_id = {p["doc_id"]: p for p in state.get("rag_results") or []}
    reconciled = state.get("reconciled") or []
    flagged = flagged_doc_ids(state.get("critic") or {}, [r["doc_id"] for r in reconciled])

    picks, left_out, dropped = [], [], []
    for r in reconciled:
        p = rag_by_id.get(r["doc_id"], {})
        name = short_title(r["title"], 6)
        warnings = " ".join(p.get("safety_warnings") or [])
        price, min_age = r.get("chosen_price"), p.get("min_age_years")
        if r["doc_id"] in flagged:
            dropped.append(r["doc_id"])
            continue
        if budget is not None and price is not None and price > budget:
            left_out.append(f"{name} is ${price:.2f}, over your ${budget:g} budget")
        elif age is not None and min_age is not None and min_age > age:
            left_out.append(f"{name} is for ages {min_age:g}+")
        elif age is not None and age < 3 and _mentions(warnings, SMALL_PARTS_WORDS):
            left_out.append(f"{name} has a small-parts warning")
        elif excluded and (feat := next((e for e in excluded
                                         if _mentions(warnings + " " + (p.get("features_snippet") or ""), [e])), None)):
            left_out.append(f"{name} lists {feat}")
        elif min_rating is not None and p.get("rating") is not None and p["rating"] < min_rating:
            left_out.append(f"{name} is rated {p['rating']:g}, below {min_rating:g}")
        else:
            picks.append((r, p))
    picks.sort(key=lambda rp: rp[0].get("availability") == "out_of_stock")  # stable: keeps relevance order
    return picks[:TOP_N_ANSWER], left_out, dropped


def build_table(picks: list[tuple[dict, dict]]) -> tuple[list[ComparisonRow], list[Citation]]:
    citations: list[Citation] = []
    rows: list[ComparisonRow] = []
    for rank, (r, p) in enumerate(picks, start=1):
        markers = []
        citations.append({"marker": f"[{len(citations) + 1}]", "source_type": "private", "doc_id": r["doc_id"],
                          "url": None, "title": r["title"]})
        markers.append(citations[-1]["marker"])
        if r.get("live_url"):
            citations.append({"marker": f"[{len(citations) + 1}]", "source_type": "web", "doc_id": None,
                              "url": r["live_url"], "title": f"Live listing: {short_title(r['title'], 6)}"})
            markers.append(citations[-1]["marker"])
        rows.append({"rank": rank, "title": r["title"], "brand": r.get("brand"), "price": r.get("chosen_price"),
                     "price_source": r.get("price_source") or "unknown", "rating": p.get("rating"),
                     "age_range": age_range(p), "safety_warnings": p.get("safety_warnings"),
                     "doc_id": r["doc_id"], "live_url": r.get("live_url"), "citation_markers": markers})
    return rows, citations


def needs_warning_note(state: AgentState, picks: list[tuple[dict, dict]]) -> bool:
    age = (state.get("constraints") or {}).get("child_age_years")
    return bool(picks) and ((age is not None and age < 3) or any(p.get("safety_warnings") for _, p in picks))


# ---------------------------------------------------------------- text

def template_answer(picks, rows, left_out) -> tuple[str, str]:
    """Deterministic answer (fake provider, no products, or LLM failure)."""
    if not picks:
        answer = "I couldn't find a product in our catalog that matches all of your requirements."
        if left_out:
            answer += " " + "; ".join(left_out) + "."
        answer += " Want me to try a different budget or type of toy?"
        return answer, answer

    lines = []
    for row, (r, p) in zip(rows, picks):
        price = (f"${row['price']:.2f} ({row['price_source']})" if row["price"] is not None else "price not listed")
        bits = [price]
        if p.get("rating") is not None:
            bits.append(f"{p['rating']} stars")
        if row["age_range"]:
            bits.append(f"ages {row['age_range']}")
        line = f"{row['rank']}. {r['title']}: " + ", ".join(bits) + " " + "".join(row["citation_markers"])
        if p.get("safety_warnings"):
            line += f". Listing warnings: {'; '.join(p['safety_warnings'])}"
        if r.get("note"):
            line += f". {r['note']}"
        lines.append(line)
    n = len(picks)
    answer = f"Here {'are' if n > 1 else 'is'} the top {n} option{'s' if n > 1 else ''}:\n" + "\n".join(lines)
    if left_out:
        answer += "\nLeft out: " + "; ".join(left_out) + "."

    top = picks[0][0]
    spoken = f"My top pick is {short_title(top['title'], 6)}"
    if top.get("chosen_price") is not None:
        spoken += f" at ${top['chosen_price']:.2f}"
    spoken += "."
    if top.get("price_conflict"):
        spoken += " Its live price differs from our catalog."
    if n > 1:
        spoken += f" I also found {n - 1} more option{'s' if n > 2 else ''}."
    spoken += " Details and sources are on screen."
    return answer, spoken


def evidence(picks, rows) -> list[dict]:
    """Only the chosen products' facts go to the LLM."""
    out = []
    for row, (r, p) in zip(rows, picks):
        out.append({
            "rank": row["rank"], "citation_markers": row["citation_markers"],
            "title": r["title"], "brand": r.get("brand"),
            "price": r.get("chosen_price"), "price_source": r.get("price_source"),
            "catalog_price": r.get("catalog_price"), "live_price": r.get("live_price"),
            "availability": r.get("availability"), "rating": p.get("rating"),
            "age_range": row["age_range"], "safety_warnings": p.get("safety_warnings"),
            "features": p.get("features_snippet"), "note": r.get("note"),
        })
    return out


def llm_answer(state: AgentState, picks, rows, left_out) -> tuple[str, str, dict]:
    critic = state.get("critic") or {}
    revising = bool(state.get("revision_count")) and not critic.get("approved", True)
    payload = {
        "request": state.get("transcript", ""),
        "intent": state.get("intent"),
        "constraints": {k: v for k, v in (state.get("constraints") or {}).items() if v not in (None, [], False)},
        "products": evidence(picks, rows),
        "left_out": left_out,
    }
    if revising:
        payload["critic_feedback"] = critic.get("feedback", "")
        payload["previous_answer"] = state.get("draft_answer", "")
    system = system_prompt_for("answerer_system", guardrails=prompt_section("guardrails"))
    draft, meta = invoke_structured("answerer", AnswerDraft, system, json.dumps(payload, ensure_ascii=False))
    return draft.answer.strip(), draft.spoken_summary.strip(), meta


FILLER_RE = re.compile(r"^.*\b(left out no|no products were left out|nothing was left out)\b.*$\n?", re.I | re.M)


def drop_filler(answer: str, left_out: list[str]) -> str:
    """Remove a 'left out nothing' line the model sometimes adds when nothing was left out."""
    return answer if left_out else FILLER_RE.sub("", answer).strip()


def keep_cited(answer: str, picks, rows, citations):
    """Keep only the products the LLM's answer actually cites, so the table matches the text.

    If the answer cites nothing, everything is kept and the Critic reports the missing markers.
    """
    used = set(MARKER_RE.findall(answer))
    keep = [i for i, row in enumerate(rows) if used & set(row["citation_markers"])]
    if not keep or len(keep) == len(rows):
        return picks, rows, citations
    picks = [picks[i] for i in keep]
    rows = [{**rows[i], "rank": n} for n, i in enumerate(keep, start=1)]
    markers = {m for row in rows for m in row["citation_markers"]}
    return picks, rows, [c for c in citations if c["marker"] in markers]


# ---------------------------------------------------------------- node

def answerer_node(state: AgentState) -> dict:
    picks, left_out, dropped = select_products(state)
    rows, citations = build_table(picks)
    warn = needs_warning_note(state, picks)
    revision = state.get("revision_count", 0)

    source, meta, errors = "template", {}, []
    answer, spoken = template_answer(picks, rows, left_out)
    if picks and get_llm_settings("answerer").provider != "fake":
        try:
            llm_text, llm_spoken, meta = llm_answer(state, picks, rows, left_out)
            if MARKER_RE.search(llm_text):
                answer, spoken, source = drop_filler(llm_text, left_out), llm_spoken, "llm"
                picks, rows, citations = keep_cited(answer, picks, rows, citations)
                warn = needs_warning_note(state, picks)
            else:  # an uncited answer is never shown; the template is fully cited
                source = "template (LLM answer had no citation markers)"
        except Exception as e:  # noqa: BLE001
            errors.append(f"answerer: LLM call failed, used template: {e}")
            meta = {"error": str(e)}

    if warn and WARNING_NOTE.lower() not in answer.lower():
        answer += "\n" + WARNING_NOTE
    spoken = clean_spoken(spoken, warn)

    summary = f"{len(rows)} products, {len(citations)} citations ({source})"
    if revision:
        summary += f", revision {revision}"
    if dropped:
        summary += f", dropped on critic's request: {', '.join(dropped)}"
    out = {"draft_answer": answer, "final_answer": answer, "comparison_table": rows, "citations": citations,
           "spoken_summary": spoken,
           **log_step("answerer", summary, doc_ids=[r["doc_id"] for r in rows], left_out=left_out,
                      dropped=dropped, source=source, **meta)}
    if errors:
        out["errors"] = errors
    return out
