"""Run the ProofAgent evaluation (#55). Owner: Beste. Usually called through doit:

    uv run doit eval_dry_run     # mock catalog, 2 scenarios, 3 turns, no upload: checks the wiring
    uv run doit eval             # real catalog, all scenarios, uploads to the ProofAgent dashboard

    uv run python -m eval.run [--dry-run] [--no-upload] [--turns N]

Settings: config/eval.py (env vars override). Secrets from .env: PROOFAGENT_API_KEY for --upload, and the LLM keys
for the agent, the attacker, and the jury.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from config import eval as cfg
from config.paths import ENV_FILE, EVAL_CONTEXT_DIR, EVAL_KNOWLEDGE_DIR, EVAL_REPORTS_DIR, ROOT


def jury_llm(env: dict) -> str:
    """The configured jury, or the fallback when its provider has no API key."""
    if cfg.JURY_LLM.startswith("anthropic/") and not env.get("ANTHROPIC_API_KEY"):
        print(f"WARNING: no ANTHROPIC_API_KEY; jury falls back to {cfg.JURY_FALLBACK_LLM} (same provider as the agent).")
        return cfg.JURY_FALLBACK_LLM
    return cfg.JURY_LLM


def build_command(dry_run: bool, upload: bool, turns: int | None, jury: str) -> list[str]:
    scenarios = cfg.DRY_RUN_SCENARIOS if dry_run else cfg.SCENARIOS
    stamp = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{cfg.AGENT_VERSION}{'-dry' if dry_run else ''}"
    EVAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "eval.proof_cli", "run", str(ROOT / "eval" / "agent.py"),
        "--context-dir", str(EVAL_CONTEXT_DIR),
        "--domain-knowledge-dir", str(EVAL_KNOWLEDGE_DIR),
        "--extra-traps", str(ROOT / "eval" / "traps"),
        "--pin-traps", ",".join(scenarios),
        "--turns", str(turns or (cfg.DRY_RUN_TURNS if dry_run else cfg.TURNS)),
        "--seed", str(cfg.SEED),
        "--attacker-llm", cfg.ATTACKER_LLM, "--llm", cfg.ATTACKER_LLM, "--jury-llm", jury,
        "--fallback-llm", cfg.FALLBACK_LLM,
        "--agent", cfg.AGENT_NAME, "--agent-version", cfg.AGENT_VERSION,
        "--json", str(EVAL_REPORTS_DIR / f"{stamp}.json"),
        "--markdown", str(EVAL_REPORTS_DIR / f"{stamp}.md"),
        "--fresh",
    ]
    if upload:
        cmd += ["--upload", "--profile", cfg.PROFILE, "--fail-on", cfg.FAIL_ON]
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="mock catalog, 2 scenarios, 3 turns, no upload")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--turns", type=int)
    args = ap.parse_args()

    load_dotenv(ENV_FILE)
    env = dict(os.environ, PROOFAGENT_API_BASE_URL=cfg.PROOFAGENT_API_BASE_URL)
    if args.dry_run:
        env.update(EVAL_CATALOG="mock")
    if env.get("EVAL_CATALOG", cfg.CATALOG) == "mock":
        env.update(MCP_SERVER_ARGS="-m mocks.mcp_server", MOCK_RAG_FORCE_FAKE="1")
    upload = not (args.dry_run or args.no_upload)
    if upload and not env.get("PROOFAGENT_API_KEY"):
        sys.exit("PROOFAGENT_API_KEY is not set in .env (needed for --upload). Use --no-upload to run locally.")

    # Rebuild the context so it matches the current prompts and catalog.
    subprocess.run([sys.executable, "-m", "eval.build_context"], check=True, env=env, cwd=ROOT)
    cmd = build_command(args.dry_run, upload, args.turns, jury_llm(env))
    print("Running:", " ".join(cmd[2:]))
    return subprocess.run(cmd, env=env, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
