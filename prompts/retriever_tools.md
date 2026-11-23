# Retriever tool-use policy

**Owner:** Devanshu · **Issue:** #44, #49, #60 · **Nodes:** `retriever` ([agent/nodes/retriever.py](../agent/nodes/retriever.py)),
`reconcile` ([agent/nodes/reconcile.py](../agent/nodes/reconcile.py))
**Tools:** `rag.search`, `web.search` (MCP, stdio) · **Writes:** `rag_results`, `web_results`, `reconciled`, `errors`

**No LLM prompt is sent by these nodes.** The Retriever executes the Planner's `plan` deterministically through the
MCP client, so the tool calls are reproducible and every call is logged. This file discloses that policy (the
assignment asks for "tool-call instructions"); the LLM-side tool decisions are in [planner_system.md](planner_system.md).

Why deterministic: the Planner has already chosen the tools and arguments with an LLM. Letting a second LLM re-decide
the calls would add latency, cost, and a new failure point without new information. It also avoids the dotted tool
name issue (#20): `rag.search` / `web.search` are called by their MCP names and never exposed as LLM function names.

## Policy

1. **Catalog first.** If `plan.use_rag`, call `rag.search` with `RagSearchInput(query=plan.rag_query, top_k=plan.top_k, **plan.rag_filters)`.
2. **Live lookups per product.** If `plan.use_web`, call `web.search` once for each of the top
   `GRAPH_WEB_LOOKUPS` (3) catalog results with query `"<brand> <title> price"`, so live results can be matched to
   catalog products. If the catalog returned nothing, call it once with `plan.web_query`.
3. **Fallback when catalog data is missing.** If `rag.search` returns 0 products and the plan did not use the web,
   call `web.search` once with `plan.web_query` (or `plan.rag_query`) and log the reason.
4. **Failures never crash the graph.** A tool error or timeout is appended to `errors` and logged; the graph
   continues with whatever results it has.
5. **Logging.** Each call goes into the step log: tool, arguments, result count, latency, error.

## Reconciliation (node `reconcile`)

For each catalog product, find the best live result:

| Order | `match_method` | Rule |
|-------|----------------|------|
| 1 | `sku` | The catalog SKU/ASIN appears in the web result's URL, title, or snippet. |
| 2 | `brand_title` | Brand appears in the web title/snippet and ≥ `BRAND_TITLE_THRESHOLD` (0.4) of catalog-title words are in the web title. |
| 3 | `similarity` | ≥ `TITLE_MATCH_THRESHOLD` (0.6) of catalog-title words are in the web title. |
| — | `none` | No live match. |

- **Conflict:** `price_conflict = true` when both prices exist and differ by more than `PRICE_CONFLICT_THRESHOLD` (10%).
- **Chosen price:** the live price when the user asked for current info (or the catalog has no price); otherwise the
  catalog price. `price_source` and `note` record which source was used and why. Out-of-stock results are noted.
- Thresholds live in [config/graph.py](../config/graph.py).
