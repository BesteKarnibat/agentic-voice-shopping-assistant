# MCP server and tool schemas

**Owner:** Juan · **Branch:** `feature/mcp` · **Status:** todo
**Code:** TODO (MCP server) · **Contract:** [../../contracts/tool_schemas.py](../../contracts/tool_schemas.py), generated [../../contracts/tool_schemas.json](../../contracts/tool_schemas.json)

## 1. Overview
<!-- One server exposing rag.search and web.search. Transport, how the Retriever connects, how tools are discovered (TOOLS registry). Diagram welcome. -->
TODO

## 2. Tools

### `rag.search`
<!-- Purpose, when the Planner should use it, input/output tables copied from the Pydantic models, one example request/response. -->
TODO

### `web.search`
<!-- Same. Provider used, allowed domains, what is returned (always includes source URL). -->
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
```bash
# TODO: start the server, call each tool manually, run tests
```

## 6. Schema changes
Schemas are shared contracts. To change them, agree with the team first, then regenerate the JSON (see [../../.claude/CLAUDE.md](../../.claude/CLAUDE.md)).

## 7. Decisions, limitations, and known issues
TODO
