"""
Shared LangGraph state. Every node reads from and writes to this one object.

Owner: Devanshu (LangGraph lead). Change only after telling the team.

Rules:
  * Store plain dicts (e.g. RagProduct(...).model_dump()), not Pydantic objects,
    so the state is JSON-serializable for logs, the UI, and ProofAgent.
  * Every node appends at least one entry to step_log using log_step().
  * A node returns only the keys it changed.
"""
from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, TypedDict

MAX_CRITIC_REVISIONS = 2  # Answerer gets at most 2 rewrites before we stop.

Intent = Literal[
    "product_search",      # "recommend a cleaner under $15"
    "product_comparison",  # "compare X and Y"
    "product_question",    # "does X contain bleach?"
    "price_check",         # "what's the current price of X?"
    "unclear",             # needs a clarifying question
    "unsafe",              # refuse or redirect
    "out_of_scope",        # not about products
]


# ---------------- Router output ----------------

class Constraints(TypedDict, total=False):
    category: Optional[str]
    budget_min: Optional[float]
    budget_max: Optional[float]
    brand: Optional[str]
    surface: Optional[str]          # what it's used on, e.g. "stainless steel"
    preferences: list[str]          # e.g. ["eco-friendly", "fragrance-free"]
    exclude_ingredients: list[str]  # e.g. ["bleach", "ammonia"]
    min_rating: Optional[float]
    wants_current_info: bool        # user said "current", "latest", "in stock"...


class SafetyCheck(TypedDict):
    is_safe: bool
    category: Optional[str]  # e.g. "chemical_mixing", "ingestion", "prompt_injection"
    reason: Optional[str]


# ---------------- Planner output ----------------

class Plan(TypedDict):
    use_rag: bool
    use_web: bool
    rag_query: str
    rag_filters: dict              # becomes RagSearchInput fields
    web_query: Optional[str]
    comparison_criteria: list[str] # e.g. ["price", "rating", "ingredients"]
    top_k: int
    reasoning: str                 # shown in the UI step log


# ---------------- Retriever output ----------------

class ReconciledProduct(TypedDict):
    """A catalog product, optionally matched to a live web result."""
    doc_id: str
    title: str
    brand: Optional[str]
    catalog_price: Optional[float]
    live_price: Optional[float]
    live_url: Optional[str]
    availability: Optional[str]
    match_method: Literal["sku", "brand_title", "similarity", "none"]
    match_score: float
    price_conflict: bool           # catalog and live price differ by > threshold
    chosen_price: Optional[float]
    price_source: Literal["catalog", "web", "unknown"]
    note: Optional[str]            # e.g. "Live price is 20% higher than catalog"


# ---------------- Answerer / Critic output ----------------

class Citation(TypedDict):
    marker: str                    # "[1]"
    source_type: Literal["private", "web"]
    doc_id: Optional[str]          # set for private sources
    url: Optional[str]             # set for web sources
    title: str


class ComparisonRow(TypedDict):
    rank: int
    title: str
    brand: Optional[str]
    price: Optional[float]
    price_source: str
    rating: Optional[float]
    ingredients: Optional[list[str]]
    doc_id: str
    live_url: Optional[str]
    citation_markers: list[str]


class CriticVerdict(TypedDict):
    approved: bool
    unsupported_claims: list[str]
    missing_citations: list[str]
    constraint_violations: list[str]  # e.g. "Product [2] is $18, budget is $15"
    safety_issues: list[str]
    feedback: str                     # passed back to the Answerer on rejection


# ---------------- Logging ----------------

class StepLogEntry(TypedDict):
    timestamp: str
    node: str        # "router", "planner", "retriever", "answerer", "critic", "tts"...
    summary: str     # one human-readable line for the UI
    details: dict    # tool args, result counts, latency, etc.


# ---------------- The state ----------------

class AgentState(TypedDict, total=False):
    # Input (Alekhya: ASR)
    session_id: str
    audio_path: Optional[str]
    transcript: str
    asr_segments: list[dict]                 # [{"start": 0.0, "end": 1.2, "text": "..."}]

    # Router (Devanshu)
    intent: Intent
    constraints: Constraints
    safety: SafetyCheck
    clarification_question: Optional[str]

    # Planner (Devanshu)
    plan: Plan

    # Retriever (Devanshu, using Akshaj's and Juan's tools)
    rag_results: list[dict]                  # RagProduct.model_dump()
    web_results: list[dict]                  # WebResult.model_dump()
    reconciled: list[ReconciledProduct]

    # Answerer / Critic (Beste)
    draft_answer: str
    critic: CriticVerdict
    revision_count: int
    final_answer: str                        # full on-screen answer with [n] markers
    comparison_table: list[ComparisonRow]
    citations: list[Citation]
    spoken_summary: str                      # <= ~40 words, no markers, for TTS

    # Output (Alekhya: TTS)
    tts_audio_path: Optional[str]

    # Logging: these lists APPEND across nodes instead of overwriting
    step_log: Annotated[list[StepLogEntry], operator.add]
    errors: Annotated[list[str], operator.add]


def log_step(node: str, summary: str, **details) -> dict:
    """Return a partial state update that appends one step-log entry.

    Usage inside a node:
        return {"plan": plan, **log_step("planner", "Using RAG + web", plan=plan)}
    """
    entry: StepLogEntry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": node,
        "summary": summary,
        "details": details,
    }
    return {"step_log": [entry]}
