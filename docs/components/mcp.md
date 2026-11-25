# MCP server and tool schemas

**Owner:** Juan · **Branch:** `feature/mcp` · **Status:** draft
**Code:** TODO (MCP server) · **Contract:** [../../contracts/tool_schemas.py](../../contracts/tool_schemas.py), generated [../../contracts/tool_schemas.json](../../contracts/tool_schemas.json)

## 1. Overview
<!-- One server exposing rag.search and web.search. Transport, how the Retriever connects, how tools are discovered (TOOLS registry). Diagram welcome. -->
TODO

## 2. Tools

Each tool is built around one purpose:

### `rag.search`
**Purpose:** Use it for product facts (what a product is, what it contains, how it is rated, and its catalog price), because the private catalog is our primary, citable source, and every fact is cited by its `doc_id`.

<!-- When the Planner should use it, input/output tables copied from the Pydantic models, one example request/response. -->
TODO

### `web.search`
**Purpose:** Use it only to check what the live web reports right now (current price or availability), or to fill a gap the catalog cannot answer; it returns only what the search API provides and never visits store pages, so every live fact is cited by its URL.

<!-- Provider used, allowed domains, what is returned (always includes source URL). -->
TODO

## 3. `web.search` controls
| Control | Value / config key | Notes |
|---------|--------------------|-------|
| Rate limit | TODO | |
| TTL cache | TODO (60–300 s) | |
| Domain allowlist | TODO | |
| Source URL preserved | yes | |
| Request/response logging | TODO (where) | |

## 4. Error handling
<!-- Timeouts, provider failure, empty results, rate limit hit: what the tool returns and how the graph should react. -->
TODO

## 5. Running and testing
The server speaks MCP over **stdio**, so you normally do not start it by hand: the client launches it as a
subprocess. The Retriever does this through [../../agent/mcp_client.py](../../agent/mcp_client.py), using
`MCP_SERVER_COMMAND` / `MCP_SERVER_ARGS` from [../../config/graph.py](../../config/graph.py) (default `-m mcp_server`).

### Prerequisites
- `uv sync`, and the Chroma index built (`uv run doit preprocess index`). The server is designed to start and
  list its tools without the index (the warm-up never raises); `rag.search` calls then fail with an error.
- `SERPER_API_KEY` in `.env` for `web.search`.

### Start the server
```bash
uv run python -m mcp_server
```
It loads the embedding model and reranker **before** the handshake (about 12 s warm, about 70 s on a fresh venv),
then waits for a client on stdin. Logs go to stderr (`[mcp-server] ...`); stdout is the MCP channel.
Every tool call is appended to `data/logs/tool_calls.jsonl` (timestamp, tool, request, response or error, duration).

### Smoke test: the whole chain through MCP
The agent runner starts the real server, discovers both tools and calls them; the step log prints each call
with its arguments, result count and latency.

```bash
uv run python -m agent --demo                      # three sample queries (needs an LLM key from .env)
LLM_PROVIDER=fake uv run python -m agent --demo    # same, offline LLM (no API key; web.search still uses Serper)
uv run python -m agent "family board game under \$30, what is the current price?"
```

A healthy run shows `→ rag.search(...) N results` and, for price or stock questions, `→ web.search(...)` lines
in the `retriever` step. Check `data/logs/tool_calls.jsonl` for the raw requests and responses.

### Call a tool by hand
```python
import asyncio, json, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command="uv", args=["run", "python", "-m", "mcp_server"], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print([t.name for t in (await session.list_tools()).tools])   # ['rag.search', 'web.search']
            r = await session.call_tool("rag.search", {"query": "wooden puzzle for a 6 year old", "top_k": 3})
            print(json.dumps(r.structuredContent, indent=2))
            w = await session.call_tool("web.search", {"query": "Calliope Tsuro price", "max_results": 3})
            print(json.dumps(w.structuredContent, indent=2))

asyncio.run(main())
```
Run it from the repo root with `uv run python <file>`. The server loads `SERPER_API_KEY` from `.env` itself.

### Tests
- `uv run pytest tests/test_components.py -k mcp`: checks that discovery matches the contract. It runs against the
  mock server (`mocks/mcp_server.py`, 12 fake products), so it needs no index or key.
- `uv run doit rag_smoke_test`: tests `rag_search()` directly (not through MCP).
- To point the agent at the mock instead of the real server: `MCP_SERVER_ARGS="-m mocks.mcp_server"`.

## 6. Schema changes
Schemas are shared contracts. To change them, agree with the team first, then regenerate the JSON (see [../../.claude/CLAUDE.md](../../.claude/CLAUDE.md)).

## 7. Decisions, limitations, and known issues
TODO
