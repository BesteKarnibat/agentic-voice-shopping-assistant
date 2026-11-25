"""Test setup: fully offline. Fake LLM + mock MCP server on the fake catalog."""

import os

os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ["MOCK_RAG_FORCE_FAKE"] = "1"
os.environ["MCP_SERVER_ARGS"] = "-m mocks.mcp_server"  # tests assert on the fake catalog

import pytest  # noqa: E402

from agent import run_agent  # noqa: E402

_cache: dict[str, dict] = {}


@pytest.fixture(scope="session")
def run():
    """run(transcript) → final state, cached per transcript."""
    def _run(transcript: str) -> dict:
        if transcript not in _cache:
            _cache[transcript] = run_agent(transcript)
        return _cache[transcript]
    return _run


def nodes(state: dict) -> list[str]:
    return [e["node"] for e in state["step_log"]]
