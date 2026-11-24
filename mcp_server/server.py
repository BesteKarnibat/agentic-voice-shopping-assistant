"""MCP server (stdio) for the shopping assistant.

Tool names, descriptions and schemas come from `contracts.tool_schemas.TOOLS`, so discovery
always matches the contract. Tool names stay `rag.search` / `web.search` (decision #20).
stdout is the MCP channel: log to stderr only.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from contracts.tool_schemas import TOOLS
from mcp_server.call_log import log_call
from mcp_server.tools import HANDLERS

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[mcp-server] %(message)s")
log = logging.getLogger("mcp-server")

server = Server("shopping-tools")


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


@server.call_tool(validate_input=False)
async def call_tool(name: str, arguments: dict) -> dict:
    """Validate the arguments, run the handler, return the output model as structured content.

    Any exception becomes an MCP `isError` result, which the client logs without crashing.
    """
    start = time.perf_counter()
    result, error = None, None
    try:
        if name not in TOOLS:
            raise ValueError(f"Unknown tool: {name}")
        args = TOOLS[name]["input"].model_validate(arguments)
        out = await asyncio.to_thread(HANDLERS[name], args)
        result = out.model_dump(mode="json")
        return result
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        log_call(name, arguments, result, error, int((time.perf_counter() - start) * 1000))


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
