"""Retriever node (#44): run the plan through MCP. No LLM; policy in prompts/retriever_tools.md."""

from __future__ import annotations

import asyncio
import time

from pydantic import ValidationError

from agent.mcp_client import ToolError, get_mcp_client
from agent.nodes.reconcile import short_title
from config import graph as cfg
from contracts.state import AgentState, log_step
from contracts.tool_schemas import RagSearchInput, RagSearchOutput, WebSearchInput, WebSearchOutput


def _lookup_query(product: dict) -> str:
    """'<brand> <short title> price'. Catalog titles are long marketing strings, so keep the head."""
    brand = product.get("brand") or ""
    title = short_title(product["title"])
    prefix = "" if not brand or title.lower().startswith(brand.lower()) else brand + " "
    return f"{prefix}{title} price"


async def retriever_node(state: AgentState) -> dict:
    plan = state.get("plan") or {}
    calls: list[dict] = []
    errors: list[str] = []
    rag_results: list[dict] = []
    web_results: list[dict] = []
    fallback_reason = None

    try:
        client = await get_mcp_client()
    except Exception as e:  # noqa: BLE001
        msg = f"retriever: MCP server unavailable: {e}"
        return {"rag_results": [], "web_results": [], "errors": [msg],
                **log_step("retriever", "MCP server unavailable, no results", error=str(e))}

    async def call(tool: str, args_model, out_model):
        args = args_model.model_dump(exclude_none=True)
        t0 = time.perf_counter()
        record = {"tool": tool, "args": args}
        try:
            out = out_model.model_validate(await client.call(tool, args))
            record.update(ok=True, n_results=len(out.results))
            return out
        except (ToolError, ValidationError) as e:
            record.update(ok=False, error=str(e)[:300])
            errors.append(f"retriever: {tool} failed: {str(e)[:200]}")
            return None
        finally:
            record["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            calls.append(record)

    # Catalog first.
    if plan.get("use_rag", True):
        try:
            rag_in = RagSearchInput(query=plan.get("rag_query") or state.get("transcript", "toy"),
                                    top_k=plan.get("top_k", cfg.DEFAULT_TOP_K), **plan.get("rag_filters", {}))
        except ValidationError as e:
            errors.append(f"retriever: invalid rag.search arguments: {e}")
            rag_in = None
        if rag_in is not None:
            out = await call(cfg.RAG_TOOL, rag_in, RagSearchOutput)
            if out is not None:
                rag_results = [p.model_dump() for p in out.results]

    # One live lookup per top catalog product, so results can be reconciled.
    web_queries: list[str] = []
    if plan.get("use_web"):
        if rag_results:
            web_queries = [_lookup_query(p) for p in rag_results[: cfg.WEB_LOOKUPS_PER_RUN]]
        else:
            web_queries = [plan.get("web_query") or plan.get("rag_query", "")]
    elif plan.get("use_rag", True) and not rag_results:
        # Catalog empty: fall back to the web.
        fallback_reason = "rag.search returned no products; falling back to web.search"
        web_queries = [plan.get("web_query") or plan.get("rag_query", "")]

    web_queries = [q for q in dict.fromkeys(web_queries) if q.strip()]
    outs = await asyncio.gather(*[
        call(cfg.WEB_TOOL, WebSearchInput(query=q, max_results=cfg.WEB_MAX_RESULTS), WebSearchOutput)
        for q in web_queries
    ])
    seen_urls: set[str] = set()
    for out in outs:
        for r in (out.results if out else []):
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                web_results.append(r.model_dump(mode="json"))

    summary = f"rag.search → {len(rag_results)} products"
    if web_queries:
        summary += f"; web.search x{len(web_queries)} → {len(web_results)} live results"
    if fallback_reason:
        summary += " (fallback: catalog empty)"
    if errors:
        summary += f"; {len(errors)} tool error(s)"
    update = {"rag_results": rag_results, "web_results": web_results,
              **log_step("retriever", summary, tool_calls=calls, fallback_reason=fallback_reason,
                         doc_ids=[p["doc_id"] for p in rag_results], urls=[w["url"] for w in web_results])}
    if errors:
        update["errors"] = errors
    return update
