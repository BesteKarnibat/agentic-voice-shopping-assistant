"""`proof run` with a Claude effort level for the jury. Called by eval/run.py instead of proofagent_harness.cli.

The harness builds the jury from a model name only, and its --reasoning-effort reaches OpenAI reasoning models
only. Here the harness's LLM class is replaced by a subclass that adds `output_config.effort` (config/eval.py
JURY_EFFORT) to the jury's calls when the jury is a Claude model. The attacker and the backup judge are unchanged.
"""

from __future__ import annotations

import sys

from proofagent_harness import harness as _harness
from proofagent_harness.cli import app

from config import eval as cfg


def _arg(name: str) -> str | None:
    argv = sys.argv
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def jury_kwargs(model: str | None, effort: str) -> dict:
    """Extra call kwargs for the jury: Claude effort, or nothing for other providers."""
    if model and model.startswith("anthropic/") and effort:
        return {"output_config": {"effort": effort}}
    return {}


def install(jury_model: str | None, effort: str) -> None:
    extra = jury_kwargs(jury_model, effort)
    if not extra:
        return

    class JuryLLM(_harness.LLM):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.model == jury_model:
                for k, v in extra.items():
                    self.extra_kwargs.setdefault(k, v)

    _harness.LLM = JuryLLM  # Harness builds the attacker, jury, and fallback through this name


if __name__ == "__main__":
    install(_arg("--jury-llm"), cfg.JURY_EFFORT)
    app()
