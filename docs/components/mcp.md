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
```bash
# TODO: start the server, call each tool manually, run tests
```

## 6. Schema changes
Schemas are shared contracts. To change them, agree with the team first, then regenerate the JSON (see [../../.claude/CLAUDE.md](../../.claude/CLAUDE.md)).

## 7. Decisions, limitations, and known issues
TODO
