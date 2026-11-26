"""ProofAgent evaluation settings (non-secret). Owner: Beste. Issue: #55.

Env vars of the same name override the defaults. Secrets (PROOFAGENT_API_KEY, the LLM keys) live in .env.

    EVAL_TURNS=10 EVAL_AGENT_VERSION=v1 uv run doit eval
"""

from __future__ import annotations

import os

# ProofAgent workspace (dashboard) for --upload
PROOFAGENT_API_BASE_URL: str = os.getenv("PROOFAGENT_API_BASE_URL", "https://app.proofagent.ai")
AGENT_NAME: str = os.getenv("EVAL_AGENT_NAME", "toy-shopping-assistant")
# Bump between runs we compare: v1 = first run (Sat Nov 28), v2 = after the fix loop.
AGENT_VERSION: str = os.getenv("EVAL_AGENT_VERSION", "v0")
PROFILE: str = os.getenv("EVAL_PROFILE", "default_multi_turn")
FAIL_ON: str = os.getenv("EVAL_FAIL_ON", "block")

# Harness models (LiteLLM ids). The jury uses a different provider from the agent (config/llm.py, OpenAI by
# default) so the agent is not graded by its own model family; the attacker matches neither the jury.
ATTACKER_LLM: str = os.getenv("EVAL_ATTACKER_LLM", "gpt-4o-mini")
JURY_LLM: str = os.getenv("EVAL_JURY_LLM", "anthropic/claude-haiku-5-5")
# Used when the jury provider has no key in .env (e.g. no ANTHROPIC_API_KEY); same provider as the agent, so noted
# as a limitation in the report.
JURY_FALLBACK_LLM: str = os.getenv("EVAL_JURY_FALLBACK_LLM", "gpt-4.1-mini")

TURNS: int = int(os.getenv("EVAL_TURNS", "25"))
SEED: int = int(os.getenv("EVAL_SEED", "42"))

# Our scenarios (eval/traps/), pinned so every run includes them; the rest of the turns come from the
# harness library (prompt injection, data exfiltration, ...).
SCENARIOS: tuple[str, ...] = (
    "toy_discovery_constraints", "toy_comparison", "toy_voice_transcripts", "toy_grounded_claims",
    "toy_missing_or_impossible", "toy_tool_selection", "toy_incorrect_tool_results", "toy_prompt_injection",
    "toy_child_safety", "toy_age_grade_pressure",
)
DRY_RUN_SCENARIOS: tuple[str, ...] = ("toy_discovery_constraints", "toy_child_safety")
DRY_RUN_TURNS: int = 3

# Multi-turn memory in the adapter. run_agent() handles one turn, so the adapter adds the last N user turns
# (and the products recommended for them) to the transcript. 0 = no memory. Interim until the graph keeps
# conversation memory per session_id (open question with Devanshu on PR #85).
HISTORY_TURNS: int = int(os.getenv("EVAL_HISTORY_TURNS", "2"))

# Which catalog the agent and the knowledge corpus use: "real" (Chroma index + products.parquet) or "mock"
# (mocks/fake_catalog.py, offline). Must match, or the jury flags correct answers as hallucinations.
CATALOG: str = os.getenv("EVAL_CATALOG", "real")
