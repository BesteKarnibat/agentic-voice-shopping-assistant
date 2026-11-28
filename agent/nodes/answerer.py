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
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from agent.llm import invoke_structured
from agent.nodes.reconcile import short_title
from agent.prompts import prompt_section, system_prompt_for
from config.graph import SPOKEN_SUMMARY_MAX_WORDS, TOP_N_ANSWER
from config.llm import get_llm_settings
from contracts.state import AgentState, Citation, ComparisonRow, log_step

WARNING_NOTE = "Check the age grade and warnings on the package."
SPOKEN_WARNING = "Please check the package warnings."
AGE_NOT_LISTED = "age range not listed"
AGE_NOTE = "Some of these listings don't state an age range."
SMALL_PARTS_WORDS = ("small part", "choking")
# Price labels, the same wording as the Reconcile notes: "catalog price (2020)" and "current price at <store>".
CATALOG_LABEL = "catalog price (2020)"
PRICE_NOTE = "These are 2020 catalog prices. Want me to check current ones?"
PRICE_NOTE_NO_LIVE = "I couldn't find a current price for the ones marked catalog price (2020)."
SPOKEN_PRICE_NOTE = "Prices are from our 2020 catalog."
MARKER_RE = re.compile(r"\[\d+\]")


class AnswerDraft(BaseModel):
    """LLM output for the Answerer."""

    answer: str = Field(..., description="On-screen answer with the given [n] citation markers after each fact.")
    # Optional: models sometimes omit it (v1b T22). The code then builds it, instead of discarding the answer.
    spoken_summary: str = Field("", description="At most 35 words, no citation markers, for text-to-speech.")


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


def price_label(row: ComparisonRow) -> str:
    """'$12.15 catalog price (2020)', '$14.97 current price at walmart.com', or 'price not listed'."""
    if row.get("price") is None:
        return "price not listed"
    if row.get("price_source") == "web":
        store = urlsplit(row.get("live_url") or "").netloc.removeprefix("www.") or "the store"
        return f"${row['price']:.2f} current price at {store}"
    return f"${row['price']:.2f} {CATALOG_LABEL}"


def price_note(state: AgentState, rows: list[ComparisonRow]) -> str | None:
    """Closing line when any shown price comes from the 2020 catalog."""
    if not any(r.get("price") is not None and r.get("price_source") == "catalog" for r in rows):
        return None
    asked_live = bool((state.get("constraints") or {}).get("wants_current_info"))
    return PRICE_NOTE_NO_LIVE if asked_live else PRICE_NOTE


def clean_spoken(text: str, needs_warning: bool, catalog_prices: bool = False) -> str:
    text = " ".join(MARKER_RE.sub("", text).split())
    if catalog_prices and "$" in text and "2020" not in text:
        budget = SPOKEN_SUMMARY_MAX_WORDS - len(SPOKEN_PRICE_NOTE.split()) - \
            (len(SPOKEN_WARNING.split()) if needs_warning and "warning" not in text.lower() else 0)
        text = limit_words(text, budget) + " " + SPOKEN_PRICE_NOTE
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

    # With a child's age given, a product with no age grade is never preferred over one that fits:
    # under 3 it is left out (small-parts risk), otherwise it is shown after the others, marked as not listed.
    picks, no_age, left_out, dropped, unknown_names = [], [], [], [], []
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
        elif age is not None and age < 3 and min_age is None:
            unknown_names.append(name)
        elif age is not None and age < 3 and _mentions(warnings, SMALL_PARTS_WORDS):
            left_out.append(f"{name} has a small-parts warning")
        elif excluded and (feat := next((e for e in excluded
                                         if _mentions(warnings + " " + (p.get("features_snippet") or ""), [e])), None)):
            left_out.append(f"{name} lists {feat}")
        elif min_rating is not None and p.get("rating") is not None and p["rating"] < min_rating:
            left_out.append(f"{name} is rated {p['rating']:g}, below {min_rating:g}")
        else:
            (no_age if age is not None and min_age is None else picks).append((r, p))
    if len(unknown_names) == 1:
        left_out.append(f"{unknown_names[0]} doesn't list an age range")
    elif unknown_names:
        left_out.append(f"{len(unknown_names)} matches don't list an age range, so I can't confirm they suit a child under 3")
    in_stock_first = lambda rp: rp[0].get("availability") == "out_of_stock"  # noqa: E731  stable: keeps relevance order
    picks = sorted(picks, key=in_stock_first) + sorted(no_age, key=in_stock_first)
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
    return bool(picks) and ((age is not None and age < 3) or any(p.get("safety_warnings") for _, p in picks)
                            or (age is not None and any(p.get("min_age_years") is None for _, p in picks)))


def needs_age_note(state: AgentState, picks: list[tuple[dict, dict]]) -> bool:
    """A child's age was given and a shown product has no age grade."""
    age = (state.get("constraints") or {}).get("child_age_years")
    return age is not None and any(p.get("min_age_years") is None for _, p in picks)


# ---------------------------------------------------------------- text

def template_answer(picks, rows, left_out, child_age=None) -> tuple[str, str]:
    """Deterministic answer (fake provider, no products, or LLM failure)."""
    if not picks:
        first = "I couldn't find a product in our catalog that matches all of your requirements."
        if child_age is not None:
            question = f" Want me to look for toys made for a {child_age:g}-year-old instead?"
        else:
            question = " Want me to try a different budget or type of toy?"
        answer = first + (" " + "; ".join(left_out) + "." if left_out else "") + question
        return answer, first + " Details are on screen." + question

    lines = []
    for row, (r, p) in zip(rows, picks):
        bits = [price_label(row)]
        if p.get("rating") is not None:
            bits.append(f"{p['rating']} stars")
        if row["age_range"]:
            bits.append(f"ages {row['age_range']}")
        elif child_age is not None:
            bits.append(AGE_NOT_LISTED)
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
        spoken += " in our 2020 catalog" if top.get("price_source") == "catalog" else ""
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
            "price": r.get("chosen_price"), "price_source": r.get("price_source"), "price_label": price_label(row),
            "catalog_price": r.get("catalog_price"), "live_price": r.get("live_price"),
            "availability": r.get("availability"), "rating": p.get("rating"),
            "age_range": row["age_range"] or "not listed", "safety_warnings": p.get("safety_warnings"),
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


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_TRAILING_MARKERS = re.compile(r"(?:\s*\[\d+\]){2,}\s*$")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _title_key(title: str) -> list[str]:
    """First three words of the title's head, e.g. ['monopoly', 'fortnite', 'edition']."""
    return _words(short_title(title, 6))[:3]


def _names(words: list[str], key: list[str], mismatches: int) -> bool:
    """True if `key` appears as consecutive words, allowing up to `mismatches` differing words."""
    n = len(key)
    return any(sum(w != k for w, k in zip(words[j:j + n], key)) <= mismatches for j in range(len(words) - n + 1))


def place_markers(answer: str, rows: list[ComparisonRow]) -> tuple[str, int]:
    """Put each product's markers after the first sentence that names it; drop a marker cluster left at the end.

    The LLM sometimes writes correct facts but cites them all at the end ("...[1][2][3][4][5]") or not at all,
    which breaks per-fact citation. Returns (answer, number of products whose markers were placed by code).
    """
    trailing = _TRAILING_MARKERS.search(answer)
    body_before = answer[: trailing.start()] if trailing else answer
    pieces = _SENTENCE_END.split(answer)
    seps = _SENTENCE_END.findall(answer)
    placed = 0
    for row in rows:
        key = _title_key(row["title"])
        if not key or any(m in body_before for m in row["citation_markers"]):
            continue  # already cited in the text (outside an end-of-answer cluster)
        # Exact title words first; then, on lines with no marker yet, allow one differing word
        # (the LLM fixes catalog typos, e.g. "Small Wold Toys" -> "Small World Toys").
        hit = next((i for i, piece in enumerate(pieces) if _names(_words(piece), key, 0)), None)
        if hit is None and len(key) == 3:
            hit = next((i for i, piece in enumerate(pieces)
                        if not MARKER_RE.search(piece) and _names(_words(piece), key, 1)), None)
        if hit is not None and not any(m in pieces[hit] for m in row["citation_markers"]):
            pieces[hit] = pieces[hit].rstrip() + " " + "".join(row["citation_markers"])
            placed += 1
    text = "".join(p + (seps[i] if i < len(seps) else "") for i, p in enumerate(pieces))
    trailing = _TRAILING_MARKERS.search(text)
    if placed and trailing:
        body = text[: trailing.start()]
        if all(m in body for m in MARKER_RE.findall(trailing.group())):  # every marker is now cited in place
            text = body.rstrip()
    return text, placed


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
    child_age = (state.get("constraints") or {}).get("child_age_years")
    answer, spoken = template_answer(picks, rows, left_out, child_age)
    if picks and get_llm_settings("answerer").provider != "fake":
        try:
            llm_text, llm_spoken, meta = llm_answer(state, picks, rows, left_out)
            llm_text, placed = place_markers(llm_text, rows)
            if MARKER_RE.search(llm_text):
                answer, source = drop_filler(llm_text, left_out), "llm"
                spoken = llm_spoken.strip() or spoken  # template spoken summary if the model left it out
                if placed:
                    source += f" (code placed markers for {placed} product{'s' if placed > 1 else ''})"
                if not llm_spoken.strip():
                    source += " (spoken summary from template)"
                picks, rows, citations = keep_cited(answer, picks, rows, citations)
                warn = needs_warning_note(state, picks)
            else:  # an uncited answer is never shown; the template is fully cited
                source = "template (LLM answer had no citation markers)"
        except Exception as e:  # noqa: BLE001
            errors.append(f"answerer: LLM call failed, used template: {e}")
            meta = {"error": str(e)}

    if needs_age_note(state, picks) and "age range" not in answer.lower():
        answer += "\n" + AGE_NOTE
    if warn and WARNING_NOTE.lower() not in answer.lower():
        answer += "\n" + WARNING_NOTE
    note = price_note(state, rows)
    if note and note.lower() not in answer.lower():
        answer += "\n" + note
    spoken = clean_spoken(spoken, warn, catalog_prices=any(r.get("price_source") == "catalog" for r in rows))

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
