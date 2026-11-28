"""Structured-output schemas for the Router and Planner LLM calls.

Built from the contract types in contracts/state.py, not new contracts.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from contracts.state import Constraints, Intent, SafetyCheck

# guardrails.md: only these categories are unsafe on their own; child_safety and unsupported_claim are answered.
UNSAFE_CATEGORIES = frozenset({"injury_emergency", "harmful_use", "minor_exploitation"})
SAFE_CATEGORIES = frozenset({"child_safety", "unsupported_claim"})


class RouterDecision(BaseModel):
    """Router output → AgentState.intent / constraints / safety / clarification_question."""

    intent: Intent = Field(..., description="'unclear' only if there is no product type, brand, or age at all.")
    constraints: Constraints = Field(..., description="Only what the user said; null/empty when not stated.")
    safety: SafetyCheck = Field(default_factory=lambda: {"is_safe": True, "category": None, "reason": None})
    clarification_question: Optional[str] = Field(None, description="Null unless intent is 'unclear'.")

    @field_validator("safety", mode="before")
    @classmethod
    def _fill_optional_safety_keys(cls, v):
        # Models often omit keys, but SafetyCheck requires them. A missing is_safe follows the category (#57).
        if v is None:
            v = {}
        if isinstance(v, dict):
            v = {"category": None, "reason": None, **v}
            if v.get("is_safe") is None:
                v["is_safe"] = v["category"] not in UNSAFE_CATEGORIES
        return v

    @field_validator("constraints", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return v or {}


class PlannerDraft(BaseModel):
    """LLM part of Plan; the planner node adds use_rag, rag_filters and top_k."""

    rag_query: str = Field(..., description="Short semantic search text for the private catalog.")
    use_web: bool = Field(..., description="True only for current/latest price, availability, or missing catalog data.")
    web_query: Optional[str] = None
    comparison_criteria: list[str] = Field(default_factory=list)
    reasoning: str
