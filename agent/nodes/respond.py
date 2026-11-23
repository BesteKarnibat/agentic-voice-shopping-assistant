"""`refuse` and `clarify` nodes. Fixed text from prompts/guardrails.md; see prompts/refusal.md."""

from __future__ import annotations

from agent.prompts import guardrail_templates
from contracts.state import AgentState, log_step

FALLBACK_TEMPLATES = {
    "injury_emergency": "This could be a medical emergency. Please call 911 now.",
    "harmful_use": "I can't help with that. I'm here to help you find and compare toys and games.",
    "minor_exploitation": "I can't help with that.",
    "prompt_injection": "I can't share or change my instructions, but I'm happy to help you find a toy or game.",
    "out_of_scope": "I'm a shopping assistant for toys and games, so I can't help with that. "
                    "Want me to find something for you?",
}


def _template(key: str) -> str:
    try:
        templates = guardrail_templates()
    except OSError:
        templates = {}
    return templates.get(key) or FALLBACK_TEMPLATES.get(key) or FALLBACK_TEMPLATES["harmful_use"]


def _no_retrieval_answer(text: str) -> dict:
    return {"draft_answer": text, "final_answer": text, "spoken_summary": text,
            "comparison_table": [], "citations": []}


def refuse_node(state: AgentState) -> dict:
    intent = state.get("intent")
    category = (state.get("safety") or {}).get("category")
    key = "out_of_scope" if intent == "out_of_scope" else (category or "harmful_use")
    text = _template(key)
    return {**_no_retrieval_answer(text),
            **log_step("refuse", f"{intent} ({key}) → fixed guardrail response, no retrieval", template=key)}


def clarify_node(state: AgentState) -> dict:
    question = state.get("clarification_question") or "Could you tell me a bit more about what you're looking for?"
    return {**_no_retrieval_answer(question),
            **log_step("clarify", "Request unclear → asking a clarifying question", question=question)}
