"""Upload a saved ProofAgent report to the dashboard (#57). Owner: Beste.

Works around a harness bug (proofagent-harness 0.14.0): when a judge call fails over to the fallback model, the
report's `llm_fallback_reasons` holds error class names such as "LLMError", the evidence record builder rejects
them ("must be a short lower-case label"), and `--upload` sends nothing. This script normalizes those labels in a
copy of the report and uploads it through the harness's own upload path.

    uv run python -m eval.upload_report data/proofagent/reports/<run>.json --agent-version v1b
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from config import eval as cfg
from config.paths import ENV_FILE, EVAL_CONTEXT_DIR


def short_label(name: str) -> str:
    """'LLMError' -> 'llm_error', at most 31 lower-case characters."""
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name)
    return re.sub(r"[^a-z0-9_]+", "_", snake.lower()).strip("_")[:31] or "error"


def normalize(report: dict) -> dict:
    fixed = dict(report)
    reasons: dict[str, int] = {}
    for k, v in (report.get("llm_fallback_reasons") or {}).items():
        reasons[short_label(str(k))] = reasons.get(short_label(str(k)), 0) + int(v or 0)
    fixed["llm_fallback_reasons"] = reasons
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", type=Path)
    ap.add_argument("--agent-version", required=True)
    args = ap.parse_args()

    load_dotenv(ENV_FILE)
    os.environ.setdefault("PROOFAGENT_API_BASE_URL", cfg.PROOFAGENT_API_BASE_URL)
    from proofagent_harness.cli import _upload_per_and_gate

    report = normalize(json.loads(args.report.read_text(encoding="utf-8")))
    prompt_file = EVAL_CONTEXT_DIR / "system_prompt.md"
    _upload_per_and_gate(report, api_key=os.environ.get("PROOFAGENT_API_KEY"), agent_name=cfg.AGENT_NAME,
                         agent_version=args.agent_version, fail_on=cfg.FAIL_ON,
                         system_prompt=prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else None,
                         exit_on_decision=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
