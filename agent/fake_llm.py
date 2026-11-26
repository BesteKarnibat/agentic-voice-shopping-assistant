"""Keyword-based stand-in for the Router and Planner LLMs (LLM_PROVIDER=fake). Tests only."""

from __future__ import annotations

import re

from pydantic import BaseModel

from agent.schemas import PlannerDraft, RouterDecision
from config.graph import CURRENT_INFO_KEYWORDS

_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
             "twenty five": 25, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "hundred": 100}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(_WORD_NUM, key=len, reverse=True)) + r")"

_SHOPPING_WORDS = ("toy", "game", "puzzle", "lego", "gift", "present", "board", "card", "doll", "kit",
                   "block", "brick", "blaster", "nerf", "stacking", "monopoly", "uno", "catan", "set",
                   "recommend", "buy", "price", "stock", "teether", "tiles", "circuits")
_BRANDS = ("LEGO", "Hasbro", "Mattel", "Ravensburger", "Melissa & Doug", "Fisher-Price", "Elenco",
           "Magna-Tiles", "Days of Wonder", "Catan Studio")
_CATEGORIES = ("board game", "card game", "jigsaw puzzle", "puzzle", "building set", "stacking toy",
               "science kit", "magnetic tiles")
_PREFS = ("educational", "stem", "cooperative", "outdoor", "family", "party", "strategy", "creative")
_EXCLUDES = ("small parts", "batteries", "magnets")


def _num(s: str) -> float:
    return float(s) if re.match(r"\d", s) else float(_WORD_NUM[s])


def fake_router(transcript: str) -> RouterDecision:
    t = " " + transcript.lower().strip() + " "
    safe = {"is_safe": True, "category": None, "reason": None}

    def decision(intent, constraints=None, safety=None, question=None):
        return RouterDecision(intent=intent, constraints=constraints or {"preferences": [], "exclude_features": []},
                              safety=safety or safe, clarification_question=question)

    # safety
    if re.search(r"swallow|inhaled|choking on|poison|ingested", t):
        return decision("unsafe", safety={"is_safe": False, "category": "injury_emergency",
                                          "reason": "User reports a possible swallowed or inhaled toy part."})
    if re.search(r"hurt (someone|people|him|her|them)|hurt more|orange tip|shoot harder|more powerful|make .* dangerous", t):
        return decision("unsafe", safety={"is_safe": False, "category": "harmful_use",
                                          "reason": "User asks how to make a toy cause harm."})
    injection = bool(re.search(r"ignore (all |your |previous |prior )*(instructions|rules)|system prompt|api key", t))
    has_shopping = any(w in t for w in _SHOPPING_WORDS)
    if injection and not re.search(r"(find|recommend|buy|need|want).*(toy|game|puzzle|lego|set)", t):
        return decision("unsafe", safety={"is_safe": False, "category": "prompt_injection",
                                          "reason": "Request tries to override instructions."})
    if not has_shopping and not re.search(r"year[- ]old|month[- ]old", t):
        return decision("out_of_scope")

    # constraints
    c: dict = {"preferences": [], "exclude_features": []}
    if m := re.search(r"(?:under|less than|below|max(?:imum)?|up to|no more than)\s*\$?\s*" + _NUM, t):
        c["budget_max"] = _num(m.group(1))
    if m := re.search(_NUM + r"[- ]?(?:years?|yrs?)[- ]?old", t):
        c["child_age_years"] = _num(m.group(1))
    elif m := re.search(_NUM + r"[- ]?months?[- ]?old", t):
        c["child_age_years"] = round(_num(m.group(1)) / 12, 2)
    if m := re.search(_NUM + r"\s*(?:players|people|of us|kids)", t):
        c["num_players"] = int(_num(m.group(1)))
    for b in _BRANDS:
        if b.lower() in t:
            c["brand"] = b
            break
    for cat in _CATEGORIES:
        if cat in t or cat + "s" in t:
            c["category"] = cat
            break
    c["preferences"] = [p if p != "stem" else "STEM" for p in _PREFS if re.search(rf"\b{p}\b", t)]
    c["exclude_features"] = [e for e in _EXCLUDES if re.search(rf"(no|without|avoid)\s+(any\s+)?{e}", t)]
    c["wants_current_info"] = any(k in t for k in CURRENT_INFO_KEYWORDS)

    safety = dict(safe)
    if injection:
        safety.update(category="prompt_injection", reason="Contains an instruction override; answering the shopping part only.")
    elif c.get("child_age_years") is not None and c["child_age_years"] < 3 or c["exclude_features"]:
        safety.update(category="child_safety", reason="Young child or excluded hazards: respect age grade and warnings.")

    # intent
    vague = re.search(r"\b(a gift|a present|something)\b", t) and not (
        c.get("category") or c.get("child_age_years") is not None or c.get("brand"))
    if vague or len(transcript.split()) < 3 and not c.get("brand"):
        return decision("unclear", c, safety,
                        "Happy to help! Who is it for, how old are they, and do you have a budget in mind?")
    if re.search(r"\bcompare\b| vs\.? | versus ", t):
        intent = "product_comparison"
    elif (re.search(r"(how much|price of|is .* in stock|cost of)", t)
          and not re.search(r"recommend|suggest|find|need|want", t) and not c.get("budget_max")):
        intent = "price_check"
    else:
        intent = "product_search"
    return decision(intent, c, safety)


def fake_planner(transcript: str, intent: str, constraints: dict) -> PlannerDraft:
    words = re.sub(r"\$?\d+(\.\d+)?|\b(under|less than|below|dollars?|bucks|year[- ]olds?|months?[- ]olds?|"
                   r"current(ly)?|price|latest|in stock|available|right now|today|please|recommend|"
                   r"find|me|my|for|a|an|the|what'?s|is|it|of|with|and|i|need|want|no|small parts|"
                   r"how much|does|do|have|any|some|son|daughter|kid)\b|[?.,!']",
                   " ", transcript.lower())
    rag_query = " ".join(words.split()) or (constraints.get("category") or "toy")
    use_web = bool(constraints.get("wants_current_info")) or intent == "price_check"
    criteria = ["price", "rating"]
    if constraints.get("child_age_years") is not None:
        criteria += ["age_range", "safety_warnings"]
    if constraints.get("num_players"):
        criteria.append("num_players")
    if use_web:
        criteria.append("availability")
    return PlannerDraft(
        rag_query=rag_query,
        use_web=use_web,
        web_query=f"{rag_query} price" if use_web else None,
        comparison_criteria=criteria,
        reasoning=("Catalog for product facts plus web search because the user asked for current price/availability."
                   if use_web else "Catalog only: the request needs product facts, not live information."),
    )


def fake_structured(node: str, schema: type[BaseModel], **kwargs) -> BaseModel:
    if node == "router":
        return fake_router(kwargs["transcript"])
    if node == "planner":
        return fake_planner(kwargs["transcript"], kwargs["intent"], kwargs["constraints"])
    raise NotImplementedError(f"No fake responder for node '{node}' (schema {schema.__name__}).")
