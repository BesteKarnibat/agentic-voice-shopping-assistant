"""MCP stdio client for the Retriever (#20, #44).

One server process is kept open and reused across runs (restarted if it dies).
Server command: MCP_SERVER_COMMAND / MCP_SERVER_ARGS in config/graph.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import graph as cfg
from config.paths import ROOT


class ToolError(RuntimeError):
    """A tool call failed (server error, timeout, or invalid result)."""


class MCPToolClient:
    def __init__(self, command: str, args: list[str]):
        self.params = StdioServerParameters(
            command=command, args=args, cwd=str(ROOT),
            env=dict(os.environ),
        )
        self.tool_names: list[str] = []
        self._session: ClientSession | None = None
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._startup_error: BaseException | None = None
        self._lock = asyncio.Lock()
        self._warm = False

    @property
    def alive(self) -> bool:
        return self._session is not None and self._task is not None and not self._task.done()

    async def _hold(self) -> None:
        # The session must be entered and exited in one task, so this task owns it.
        try:
            async with stdio_client(self.params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self.tool_names = [t.name for t in listed.tools]
                    self._session = session
                    self._ready.set()
                    await self._stop.wait()
        except BaseException as e:  # noqa: BLE001
            self._startup_error = e
            raise
        finally:
            self._session = None
            self._ready.set()

    async def start(self) -> None:
        async with self._lock:
            if self.alive:
                return
            self._ready, self._stop, self._startup_error = asyncio.Event(), asyncio.Event(), None
            self._warm = False
            self._task = asyncio.create_task(self._hold(), name="mcp-session")
            try:
                await asyncio.wait_for(self._ready.wait(), cfg.MCP_STARTUP_TIMEOUT_S)
            except asyncio.TimeoutError as e:
                await self.aclose()
                raise ToolError(f"MCP server did not start within {cfg.MCP_STARTUP_TIMEOUT_S}s") from e
            if not self.alive:
                raise ToolError(f"MCP server failed to start: {self._startup_error!r}")

    async def call(self, name: str, arguments: dict) -> dict:
        """Call a tool and return its result as a dict. Raises ToolError."""
        if not self.alive:
            await self.start()
        if self.tool_names and name not in self.tool_names:
            raise ToolError(f"Tool '{name}' not advertised by the MCP server (has {self.tool_names})")
        timeout = cfg.MCP_TOOL_TIMEOUT_S if self._warm else cfg.MCP_FIRST_CALL_TIMEOUT_S
        try:
            result = await self._session.call_tool(
                name, arguments, read_timeout_seconds=timedelta(seconds=timeout))
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"{name} failed: {e}") from e
        self._warm = True
        text = " ".join(getattr(c, "text", "") for c in result.content)
        if result.isError:
            raise ToolError(f"{name} returned an error: {text[:300]}")
        if result.structuredContent is not None:
            return dict(result.structuredContent)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ToolError(f"{name} returned non-JSON content: {text[:200]}") from e

    async def aclose(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, 10)
            except BaseException:  # noqa: BLE001
                self._task.cancel()
        self._session = None


# One client per (event loop, server command).
_clients: dict[tuple[int, str, tuple[str, ...]], MCPToolClient] = {}


async def get_mcp_client() -> MCPToolClient:
    args = tuple(shlex.split(cfg_args(), posix=os.name != "nt"))
    key = (id(asyncio.get_running_loop()), cfg_command(), args)
    client = _clients.get(key)
    if client is None:
        client = _clients[key] = MCPToolClient(cfg_command(), list(args))
    if not client.alive:
        await client.start()
    return client


def cfg_command() -> str:
    return os.getenv("MCP_SERVER_COMMAND", cfg.MCP_SERVER_COMMAND)


def cfg_args() -> str:
    return os.getenv("MCP_SERVER_ARGS", cfg.MCP_SERVER_ARGS)


async def close_all_clients() -> None:
    loop_id = id(asyncio.get_running_loop())
    for key in [k for k in _clients if k[0] == loop_id]:
        await _clients.pop(key).aclose()
