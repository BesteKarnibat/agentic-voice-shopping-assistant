"""Command-line runner for the agent (text in, answer + step log out).

    uv run python -m agent "Recommend a board game under $30"
    uv run python -m agent --demo            # the three sample queries
    uv run python -m agent --json "..."      # full final state as JSON
    LLM_PROVIDER=fake uv run python -m agent --demo   # offline, no API key
"""

from __future__ import annotations

import argparse
import json
import sys

from agent.run import run_agent
from config.llm import get_llm_settings

DEMO_QUERIES = [
    "Recommend a fun card game for family night.",
    "I need a family board game under $30. What's the current price, and is it in stock?",
    "My son swallowed a magnet from his building set. What should I do?",
]


def _print_state(state: dict) -> None:
    print(f"\n=== {state['transcript']!r}")
    print(f"intent={state.get('intent')}  safety={state.get('safety')}")
    print("\n--- step log")
    for e in state["step_log"]:
        print(f"  {e['timestamp'][11:23]}  {e['node']:<10} {e['summary']}")
        for call in e["details"].get("tool_calls", []):
            status = f"{call.get('n_results')} results" if call.get("ok") else f"ERROR {call.get('error')}"
            print(f"  {'':12} {'':<10}   → {call['tool']}({json.dumps(call['args'])}) {status}, {call['latency_ms']} ms")
    print("\n--- final answer\n" + state["final_answer"])
    for c in state.get("citations") or []:
        print(f"  {c['marker']} {c['source_type']}: {c['doc_id'] or c['url']}")
    print(f"\n--- spoken summary ({len(state['spoken_summary'].split())} words)\n{state['spoken_summary']}")
    if state.get("errors"):
        print("\n--- errors\n  " + "\n  ".join(state["errors"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("transcript", nargs="*", help="user request (text)")
    parser.add_argument("--demo", action="store_true", help="run the three sample queries")
    parser.add_argument("--json", action="store_true", help="print the full final state as JSON")
    args = parser.parse_args(argv)

    queries = DEMO_QUERIES if args.demo or not args.transcript else [" ".join(args.transcript)]
    print(f"LLM: {get_llm_settings('router').as_log()}", file=sys.stderr)
    for q in queries:
        state = run_agent(q)
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            _print_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
