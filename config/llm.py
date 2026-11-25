"""LLM provider/model settings (non-secret). Owner: Devanshu. Issue: #16.

Defaults below; override per run with env vars (not .env, which is secrets only):
LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS_<NODE>, LLM_MODEL_<NODE>.

    LLM_PROVIDER=anthropic uv run python -m agent "board game under $30"
    LLM_PROVIDER=fake uv run pytest
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_PROVIDER = "openai"
DEFAULT_TEMPERATURE = 0.2

PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-5-5",
    "fake": "fake-rule-based",
}

NODE_MAX_TOKENS: dict[str, int] = {
    "router": 800,
    "planner": 800,
    "answerer": 1200,
    "critic": 800,
    "spoken_summary": 220,
}
FALLBACK_MAX_TOKENS = 800


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    temperature: float
    max_tokens: int

    def as_log(self) -> dict:
        return {"provider": self.provider, "model": self.model,
                "temperature": self.temperature, "max_tokens": self.max_tokens}


def get_llm_settings(node: str) -> LLMSettings:
    """Settings for one node, read from env at call time."""
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    model = (
        os.getenv(f"LLM_MODEL_{node.upper()}")
        or os.getenv("LLM_MODEL")
        or PROVIDER_DEFAULT_MODELS.get(provider)
    )
    if not model:
        raise ValueError(f"No model configured for provider '{provider}'. Set LLM_MODEL.")
    temperature = float(os.getenv("LLM_TEMPERATURE", DEFAULT_TEMPERATURE))
    max_tokens = int(os.getenv(f"LLM_MAX_TOKENS_{node.upper()}",
                               NODE_MAX_TOKENS.get(node, FALLBACK_MAX_TOKENS)))
    return LLMSettings(provider, model, temperature, max_tokens)
