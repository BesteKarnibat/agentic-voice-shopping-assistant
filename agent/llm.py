"""Model-agnostic LLM access (#16). Provider/model come from config/llm.py.

LLM_PROVIDER=fake uses the offline responders in agent/fake_llm.py.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from dotenv import load_dotenv
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

from config.llm import LLMSettings, get_llm_settings
from config.paths import ENV_FILE

load_dotenv(ENV_FILE)

T = TypeVar("T", bound=BaseModel)
STRUCTURED_RETRIES = 1


@lru_cache(maxsize=32)
def _build(settings: LLMSettings):
    from langchain.chat_models import init_chat_model

    return init_chat_model(
        settings.model,
        model_provider=settings.provider,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )


def get_chat_model(node: str):
    """LangChain chat model for `node` (not available with the fake provider)."""
    settings = get_llm_settings(node)
    if settings.provider == "fake":
        raise RuntimeError("LLM_PROVIDER=fake has no chat model; use invoke_structured().")
    return _build(settings)


def invoke_structured(node: str, schema: type[T], system: str, user: str,
                      fake_input: dict | None = None) -> tuple[T, dict]:
    """Structured output via tool calling. Returns (result, metadata for the step log).

    `fake_input` is only used by the fake provider.
    """
    settings = get_llm_settings(node)
    meta = {"llm": settings.as_log()}
    if settings.provider == "fake":
        from agent.fake_llm import fake_structured

        return fake_structured(node, schema, **(fake_input or {})), meta

    model = _build(settings).with_structured_output(schema, method="function_calling")
    messages = [("system", system), ("user", user)]
    last_error: Exception | None = None
    for attempt in range(1 + STRUCTURED_RETRIES):
        try:
            result = model.invoke(messages)
            if isinstance(result, dict):
                result = schema.model_validate(result)
            if result is None:
                raise ValueError("model returned no tool call")
            meta["attempts"] = attempt + 1
            return result, meta
        except (ValidationError, OutputParserException, ValueError) as e:
            last_error = e
    raise last_error  # type: ignore[misc]
