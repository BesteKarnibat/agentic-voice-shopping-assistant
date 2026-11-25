"""Critic node (#47). Owner: Beste. See prompts/critic_system.md.

Two layers feed one CriticVerdict:
1. Code checks (always): citations, phantom sources, prices and ratings in the text, budget, age, excluded
   features, small parts for under-3s, the warnings note.
2. LLM review (real providers, when there are products): unsupported claims and the guardrails output check.

Any issue rejects the draft; `revision_count` goes up by one and `feedback` goes back to the Answerer. The graph
stops after MAX_CRITIC_REVISIONS rewrites (agent/graph.py).

Issues about a specific product name its doc_id in parentheses, so the Answerer can drop that product.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from agent.llm import invoke_structured
from agent.nodes.answerer import SMALL_PARTS_WORDS, WARNING_NOTE, evidence, needs_warning_note
from agent.prompts import prompt_section, system_prompt_for
from config.llm import get_llm_settings
from contracts.state import AgentState, CriticVerdict, log_step

PRICE_RE = re.compile(r"\$\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)")
RATING_RE = re.compile(r"(\d(?:\.\d)?)\s*(?:-|\s)?(?:out of 5\s*)?stars?\b", re.I)
MARKER_RE = re.compile(r"\[(\d+)\]")


# LLM issues about these are dropped: code checks them exactly, and small models misjudge them.
CODE_CHECKED = re.compile(r"\b(age|ages|years? old|year-old|month|budget|price|priced|cost|\$|rating|rated|stars?|"
                          r"citation|cite|marker|warnings?)\b", re.I)


class ReviewIssue(BaseModel):
    kind: Literal["unsupported_claim", "safety_issue"]
    quote: str = Field(..., description="The exact words from the answer or spoken summary that are wrong.")
    problem: str = Field(..., description="One sentence: which product ([n]) and what the evidence says instead.")


class CriticReview(BaseModel):
    """LLM output for the Critic."""

    issues: list[ReviewIssue] = Field(default_factory=list, description="Empty if the draft is fine.")


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9$.%+ ]", " ", text.lower()).split())


def filter_review(review: CriticReview, answer: str, spoken: str) -> tuple[list[str], list[str], list[dict]]:
    """Keep LLM issues that quote the draft and are not about code-checked facts."""
    text = _norm(answer + " " + spoken)
    unsupported, safety, dropped = [], [], []
    for issue in review.issues:
        quote = _norm(issue.quote)
        if not quote or quote not in text:
            dropped.append({**issue.model_dump(), "why": "quote not found in the draft"})
        elif CODE_CHECKED.search(issue.problem):
            dropped.append({**issue.model_dump(), "why": "code-checked fact"})
        else:
            msg = f'"{issue.quote.strip()}": {issue.problem.strip()}'
            (unsupported if issue.kind == "unsupported_claim" else safety).append(msg)
    return unsupported, safety, dropped


def _money(x: float | None) -> float | None:
    return None if x is None else round(float(x), 2)


def code_checks(state: AgentState) -> dict[str, list[str]]:
    c = state.get("constraints") or {}
    budget, age = c.get("budget_max"), c.get("child_age_years")
    excluded = [e.lower() for e in c.get("exclude_features") or []]
    rows = state.get("comparison_table") or []
    citations = state.get("citations") or []
    answer = state.get("final_answer") or state.get("draft_answer") or ""
    rag_by_id = {p["doc_id"]: p for p in state.get("rag_results") or []}
    reconciled = state.get("reconciled") or []
    web_urls = ({w.get("url") for w in state.get("web_results") or []}
                | {r.get("live_url") for r in reconciled if r.get("live_url")})

    unsupported, missing, violations, safety = [], [], [], []

    # Citations point at retrieved evidence.
    for cit in citations:
        if cit["source_type"] == "private" and cit.get("doc_id") not in rag_by_id:
            unsupported.append(f"Citation {cit['marker']} points at {cit.get('doc_id')}, which was not retrieved.")
        if cit["source_type"] == "web" and cit.get("url") not in web_urls:
            unsupported.append(f"Citation {cit['marker']} points at a URL that no web result returned.")
    valid = {cit["marker"] for cit in citations}
    used = {f"[{n}]" for n in MARKER_RE.findall(answer)}
    for m in sorted(used - valid):
        unsupported.append(f"Marker {m} in the answer has no source.")
    if rows and not used:
        missing.append("The answer text has no citation markers; cite each product fact with its markers.")

    # Every price and rating in the text matches the evidence.
    prices = {_money(v) for r in reconciled for v in (r.get("catalog_price"), r.get("live_price"),
                                                      r.get("chosen_price")) if v is not None}
    prices |= {_money(v) for v in (c.get("budget_min"), c.get("budget_max")) if v is not None}
    for raw in PRICE_RE.findall(answer):
        if _money(float(raw.replace(",", ""))) not in prices:
            unsupported.append(f"Price ${raw} in the answer does not match any source.")
    ratings = {round(float(p["rating"]), 1) for p in rag_by_id.values() if p.get("rating") is not None}
    for raw in RATING_RE.findall(answer):
        if round(float(raw), 1) not in ratings:
            unsupported.append(f"Rating {raw} stars in the answer does not match any source.")

    # Constraints and child safety, per recommended product.
    for row in rows:
        tag = f"[{row['rank']}] ({row['doc_id']})"
        p = rag_by_id.get(row["doc_id"], {})
        warnings = " ".join(p.get("safety_warnings") or []).lower()
        if not row.get("citation_markers"):
            missing.append(f"Product {tag} has no citation.")
        if budget is not None and row.get("price") is not None and row["price"] > budget:
            violations.append(f"Product {tag} is ${row['price']:.2f}, budget is ${budget:g}.")
        if age is not None and p.get("min_age_years") is not None and p["min_age_years"] > age:
            safety.append(f"Product {tag} is for ages {p['min_age_years']:g}+, but the child is {age:g}.")
        if age is not None and age < 3 and any(w in warnings for w in SMALL_PARTS_WORDS):
            safety.append(f"Product {tag} has a small-parts warning, but the child is under 3.")
        text = warnings + " " + (p.get("features_snippet") or "").lower()
        for e in excluded:
            if e in text:
                violations.append(f"Product {tag} lists '{e}', which the user wants to avoid.")

    if needs_warning_note(state, [(None, rag_by_id.get(r["doc_id"], {})) for r in rows]) \
            and WARNING_NOTE.lower() not in answer.lower():
        safety.append(f"The answer is missing the note: '{WARNING_NOTE}'")

    return {"unsupported_claims": unsupported, "missing_citations": missing,
            "constraint_violations": violations, "safety_issues": safety}


def llm_review(state: AgentState) -> tuple[CriticReview, dict]:
    rag_by_id = {p["doc_id"]: p for p in state.get("rag_results") or []}
    rec_by_id = {r["doc_id"]: r for r in state.get("reconciled") or []}
    rows = state.get("comparison_table") or []
    picks = [(rec_by_id.get(r["doc_id"], {"doc_id": r["doc_id"], "title": r["title"]}),
              rag_by_id.get(r["doc_id"], {})) for r in rows]
    payload = {
        "request": state.get("transcript", ""),
        "constraints": {k: v for k, v in (state.get("constraints") or {}).items() if v not in (None, [], False)},
        "evidence": evidence(picks, rows),
        "answer": state.get("final_answer", ""),
        "spoken_summary": state.get("spoken_summary", ""),
    }
    system = system_prompt_for("critic_system", guardrails=prompt_section("guardrails"))
    return invoke_structured("critic", CriticReview, system, json.dumps(payload, ensure_ascii=False))


def critic_node(state: AgentState) -> dict:
    issues = code_checks(state)
    meta, errors, reviewed, dropped = {}, [], False, []
    if state.get("comparison_table") and get_llm_settings("critic").provider != "fake":
        try:
            review, meta = llm_review(state)
            unsupported, safety, dropped = filter_review(review, state.get("final_answer") or "",
                                                         state.get("spoken_summary") or "")
            issues["unsupported_claims"] += unsupported
            issues["safety_issues"] += safety
            reviewed = True
        except Exception as e:  # noqa: BLE001
            errors.append(f"critic: LLM review failed, used code checks only: {e}")
            meta = {"error": str(e)}

    all_issues = [i for group in issues.values() for i in group]
    approved = not all_issues
    verdict: CriticVerdict = {"approved": approved, **issues,
                              "feedback": "" if approved else "Fix these issues: " + " ".join(all_issues)}
    revision = state.get("revision_count", 0) + (0 if approved else 1)
    summary = ("approved" if approved else f"rejected: {len(all_issues)} issue(s)") \
        + (" (code checks + LLM review)" if reviewed else " (code checks)")
    out = {"critic": verdict, "revision_count": revision,
           **log_step("critic", summary, verdict=verdict, llm_review=reviewed,
                      llm_issues_dropped=dropped, **meta)}
    if errors:
        out["errors"] = errors
    return out
