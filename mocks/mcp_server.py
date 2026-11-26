"""Mock MCP server (stdio) with rag.search and web.search. Owner: Devanshu. Used by the offline tests
(MCP_SERVER_ARGS="-m mocks.mcp_server"); the real server is mcp_server/.

Tools and schemas come from contracts.tool_schemas.TOOLS. rag.search uses the real rag_search()
once the index exists (MOCK_RAG_FORCE_FAKE=1 forces the fake catalog); web.search is always fake.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from config.paths import INDEX_DIR
from contracts.tool_schemas import (
    TOOLS,
    RagProduct,
    RagSearchInput,
    RagSearchOutput,
    WebResult,
    WebSearchInput,
    WebSearchOutput,
)
from mocks.fake_catalog import fake_rag_search, fake_web_search

# stdout is the MCP channel: log to stderr only.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="[mock-mcp] %(message)s")
log = logging.getLogger("mock-mcp")

server = Server("shopping-tools-mock")


def _real_rag_search():
    """Akshaj's rag_search(), or None if it isn't available yet."""
    if os.getenv("MOCK_RAG_FORCE_FAKE") == "1":
        return None
    if not (INDEX_DIR.exists() and any(INDEX_DIR.iterdir())):
        return None
    try:
        from rag.search import rag_search
    except ImportError:
        return None
    return rag_search


def run_rag_search(args: RagSearchInput) -> RagSearchOutput:
    real = _real_rag_search()
    if real is not None:
        return real(args)
    t0 = time.perf_counter()
    filters = args.model_dump(exclude={"query", "top_k"}, exclude_none=True)
    if not filters.get("exclude_features"):
        filters.pop("exclude_features", None)
    hits = fake_rag_search(args.query, args.top_k, **args.model_dump(exclude={"query", "top_k"}))
    return RagSearchOutput(
        query=args.query,
        filters_applied=filters,
        results=[RagProduct(**h) for h in hits],
        took_ms=int((time.perf_counter() - t0) * 1000),
    )


def run_web_search(args: WebSearchInput) -> WebSearchOutput:
    return WebSearchOutput(
        query=args.query,
        provider="mock",
        cached=False,
        retrieved_at=datetime.now(timezone.utc),
        results=[WebResult(**r) for r in fake_web_search(args.query, args.max_results)],
    )


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=spec["description"],
            inputSchema=spec["input"].model_json_schema(),
            outputSchema=spec["output"].model_json_schema(),
        )
        for name, spec in TOOLS.items()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> dict:
    log.info("call %s %s", name, arguments)
    if name == "rag.search":
        out = run_rag_search(RagSearchInput.model_validate(arguments))
    elif name == "web.search":
        out = run_web_search(WebSearchInput.model_validate(arguments))
    else:
        raise ValueError(f"Unknown tool: {name}")
    return out.model_dump(mode="json")


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
