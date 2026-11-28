"""Router node (#32): intent, constraints, safety, clarifying question.

Prompts: system.md + router_system.md + guardrails.md.
"""

from __future__ import annotations

import re

from agent.llm import invoke_structured
from agent.prompts import prompt_section, system_prompt_for
from agent.schemas import SAFE_CATEGORIES, UNSAFE_CATEGORIES, RouterDecision
from config.graph import CURRENT_INFO_KEYWORDS, FOLLOWUP_WORDS, SHOPPING_WORDS
from contracts.state import AgentState, log_step

DEFAULT_CLARIFICATION = "Happy to help! Who is the toy or game for, how old are they, and what's your budget?"
EMPTY_TRANSCRIPT_QUESTION = "Sorry, I didn't catch that. What kind of toy or game are you looking for?"
SHOPPING_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in SHOPPING_WORDS) + r")s?\b", re.I)


FOLLOWUP_RE = re.compile(r"\b(" + "|".join(FOLLOWUP_WORDS) + r")\b", re.I)
NEW_MESSAGE_MARK = "New message:"


def new_message(transcript: str) -> str:
    """The latest user message of a composed transcript (eval/agent.py compose_transcript), else all of it."""
    head, mark, tail = transcript.rpartition(NEW_MESSAGE_MARK)
    return tail.strip() if mark else transcript


def _normalize(decision: RouterDecision, transcript: str) -> dict:
    intent = decision.intent
    safety = dict(decision.safety)
    category = safety.get("category")
    new = new_message(transcript)
    shopping = bool(SHOPPING_RE.search(new))
    has_history = new != transcript

    # #57: child_safety / unsupported_claim are answered (age and claims handled downstream), never refused.
    if category in SAFE_CATEGORIES:
        safety["is_safe"] = True
        if intent in ("unsafe", "out_of_scope", "unclear"):
            intent = "product_search"
    # #57: urgency or tool names around a toy request; an injection with a real request left is answered.
    if shopping and category not in UNSAFE_CATEGORIES:
        if category == "prompt_injection" and (not safety.get("is_safe", True) or intent == "unsafe"):
            safety["is_safe"] = True
            intent = "product_search"
        elif intent in ("out_of_scope", "unclear"):
            intent = "product_search"

    c = {k: v for k, v in dict(decision.constraints).items() if v is not None}
    # #96: a follow-up about earlier picks, or an answer to a clarifying question ("5, under $20").
    if has_history and intent in ("out_of_scope", "unclear") and category not in UNSAFE_CATEGORIES:
        if FOLLOWUP_RE.search(new) and "You recommended:" in transcript:
            intent = "product_question"
        elif FOLLOWUP_RE.search(new) or any(k in c for k in ("budget_max", "child_age_years", "category", "brand")):
            intent = "product_search"
    c["preferences"] = list(c.get("preferences") or [])
    c["exclude_features"] = list(c.get("exclude_features") or [])
    lowered = new.lower()  # an earlier "current price" must not turn on live search for every follow-up
    c["wants_current_info"] = bool(c.get("wants_current_info")) or any(k in lowered for k in CURRENT_INFO_KEYWORDS)
    if c.get("budget_min") is not None and c.get("budget_max") is not None and c["budget_min"] > c["budget_max"]:
        c["budget_min"], c["budget_max"] = c["budget_max"], c["budget_min"]

    if not safety.get("is_safe", True):
        intent = "unsafe"
    elif intent == "unsafe":
        safety.update(is_safe=False, reason=safety.get("reason") or "Classified as unsafe by the router.")

    # A product type, brand or age is enough to search.
    if intent == "unclear" and (c.get("category") or c.get("brand") or c.get("child_age_years") is not None):
        intent = "product_search"
    question = decision.clarification_question if intent == "unclear" else None
    if intent == "unclear" and not question:
        question = DEFAULT_CLARIFICATION
    return {"intent": intent, "constraints": c, "safety": safety, "clarification_question": question}


def router_node(state: AgentState) -> dict:
    transcript = (state.get("transcript") or "").strip()
    if not transcript:
        update = {"intent": "unclear", "constraints": {"preferences": [], "exclude_features": []},
                  "safety": {"is_safe": True, "category": None, "reason": None},
                  "clarification_question": EMPTY_TRANSCRIPT_QUESTION}
        return {**update, **log_step("router", "Empty transcript → ask the user to repeat", **update)}

    system = system_prompt_for("router_system", guardrails=prompt_section("guardrails"))
    try:
        decision, meta = invoke_structured("router", RouterDecision, system, transcript,
                                           fake_input={"transcript": transcript})
    except Exception as e:  # noqa: BLE001
        update = {"intent": "unclear", "constraints": {"preferences": [], "exclude_features": []},
                  "safety": {"is_safe": True, "category": None, "reason": None},
                  "clarification_question": "Sorry, I had trouble understanding that. Could you say it another way?"}
        return {**update, "errors": [f"router: LLM call failed: {e}"],
                **log_step("router", "LLM call failed → ask to rephrase", error=str(e))}

    update = _normalize(decision, transcript)
    c = update["constraints"]
    shown = {k: v for k, v in c.items() if v not in (None, [], False)}
    summary = f"intent={update['intent']}" + (f", constraints={shown}" if shown else "")
    if update["safety"].get("category"):
        summary += f", safety={update['safety']['category']}{'' if update['safety']['is_safe'] else ' (UNSAFE)'}"
    return {**update, **log_step("router", summary, input=transcript, output=update, **meta)}
