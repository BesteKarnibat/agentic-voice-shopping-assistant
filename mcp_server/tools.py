"""Tool handlers behind the MCP server.

Each handler takes the validated input model from `contracts.tool_schemas` and returns the
matching output model. Handlers are synchronous; the server runs them in a worker thread.
"""

from __future__ import annotations

import logging
import threading

from contracts.tool_schemas import RagSearchInput, RagSearchOutput, WebSearchInput, WebSearchOutput
from mcp_server.web_search import web_search


log = logging.getLogger("mcp-server")

# rag_search() loads its models lazily and without a lock, so a search that arrives while the
# warm-up is still loading would see half-built state. One lock serves both paths.
_rag_lock = threading.Lock()


def rag_search_handler(args: RagSearchInput) -> RagSearchOutput:
    # Imported lazily so the server starts (and discovery works) before the index exists.
    from rag.search import rag_search

    with _rag_lock:
        return rag_search(args)


def warm_up_rag() -> None:
    """Load the embedding model, reranker and index now, so the first real search is fast.

    Never raises: if rag or the index is missing, the error shows up on the first real call.
    """
    try:
        rag_search_handler(RagSearchInput(query="warm up", top_k=1))
        log.info("rag.search warmed up")
    except Exception as e:  # noqa: BLE001
        log.warning("rag.search warm-up skipped: %s: %s", type(e).__name__, e)


def web_search_handler(args: WebSearchInput) -> WebSearchOutput:
    return web_search(args)


# Tool name (as in contracts.tool_schemas.TOOLS) -> handler.
HANDLERS = {
    "rag.search": rag_search_handler,
    "web.search": web_search_handler,
}
