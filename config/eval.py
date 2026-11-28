"""ProofAgent evaluation settings (non-secret). Owner: Beste. Issue: #55.

Env vars of the same name override the defaults. Secrets (PROOFAGENT_API_KEY, the LLM keys) live in .env.

    EVAL_TURNS=10 EVAL_AGENT_VERSION=v1 uv run doit eval
"""

from __future__ import annotations

import os

# ProofAgent workspace (dashboard) for --upload
PROOFAGENT_API_BASE_URL: str = os.getenv("PROOFAGENT_API_BASE_URL", "https://app.proofagent.ai")
AGENT_NAME: str = os.getenv("EVAL_AGENT_NAME", "toy-shopping-assistant")
# Bump between runs we compare: v1c = baseline before the fix loop, v2 = after it.
AGENT_VERSION: str = os.getenv("EVAL_AGENT_VERSION", "v0")
PROFILE: str = os.getenv("EVAL_PROFILE", "default_multi_turn")
FAIL_ON: str = os.getenv("EVAL_FAIL_ON", "block")

# Harness models (LiteLLM ids). The jury uses a different provider from the agent (config/llm.py, OpenAI by
# default) so the agent is not graded by its own model family; the attacker matches neither the jury.
ATTACKER_LLM: str = os.getenv("EVAL_ATTACKER_LLM", "gpt-4o-mini")
JURY_LLM: str = os.getenv("EVAL_JURY_LLM", "anthropic/claude-haiku-5-5")
# Claude effort for the jury (low | medium | high | xhigh | max; "" = model default, which is medium on Haiku 5.5).
# Sent as output_config.effort by eval/proof_cli.py; the harness's own --reasoning-effort only reaches OpenAI models.
JURY_EFFORT: str = os.getenv("EVAL_JURY_EFFORT", "high")
# Rescues judge calls that fail (rate limit, bad JSON). Different family from the jury.
FALLBACK_LLM: str = os.getenv("EVAL_FALLBACK_LLM", "gpt-4.1-mini")
# Products written to the judges' reference file. The judges also see each turn's retrieved products, so a
# sample is enough; the full catalog (3.6M characters) was trimmed anyway and blew the rate limit in v1.
KNOWLEDGE_MAX_PRODUCTS: int = int(os.getenv("EVAL_KNOWLEDGE_MAX_PRODUCTS", "100"))
# Used when the jury provider has no key in .env (e.g. no ANTHROPIC_API_KEY); same provider as the agent, so noted
# as a limitation in the report.
JURY_FALLBACK_LLM: str = os.getenv("EVAL_JURY_FALLBACK_LLM", "gpt-4.1-mini")

# 30 so all 14 pinned scenario files fit next to the harness's own personal-data traps (~25-30% of turns).
TURNS: int = int(os.getenv("EVAL_TURNS", "30"))
SEED: int = int(os.getenv("EVAL_SEED", "42"))

# Our scenarios (eval/traps/), pinned so every run includes them; the rest of the turns come from the
# harness library (prompt injection, data exfiltration, ...).
SCENARIOS: tuple[str, ...] = (
    "toy_discovery_constraints", "toy_comparison", "toy_voice_transcripts", "toy_grounded_claims",
    "toy_missing_or_impossible", "toy_tool_selection", "toy_prompt_injection", "toy_child_safety",
    "toy_age_grade_pressure",
    # adversarial / edge cases (#54)
    "toy_claim_pressure", "toy_budget_pressure", "toy_ambiguous_followups", "toy_live_data_pressure",
    "toy_unsafe_escalation",
)
# Incorrect tool results run separately with fault injection (eval/faults.py), not through ProofAgent.
DRY_RUN_SCENARIOS: tuple[str, ...] = ("toy_discovery_constraints", "toy_child_safety")
DRY_RUN_TURNS: int = 3

# Multi-turn memory in the adapter. run_agent() handles one turn, so the adapter adds the last N user turns
# (and the products recommended for them) to the transcript. 0 = no memory. Interim until the graph keeps
# conversation memory per session_id (open question with Devanshu on PR #85).
HISTORY_TURNS: int = int(os.getenv("EVAL_HISTORY_TURNS", "2"))

# Which catalog the agent and the knowledge corpus use: "real" (Chroma index + products.parquet) or "mock"
# (mocks/fake_catalog.py, offline). Must match, or the jury flags correct answers as hallucinations.
CATALOG: str = os.getenv("EVAL_CATALOG", "real")
