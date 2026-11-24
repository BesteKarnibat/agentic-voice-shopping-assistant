"""Tool handlers behind the MCP server.

Each handler takes the validated input model from `contracts.tool_schemas` and returns the
matching output model. Handlers are synchronous; the server runs them in a worker thread.
"""

from __future__ import annotations

from contracts.tool_schemas import RagSearchInput, RagSearchOutput, WebSearchInput, WebSearchOutput


def rag_search_handler(args: RagSearchInput) -> RagSearchOutput:
    # Imported lazily so the server starts (and discovery works) before the index exists.
    from rag.search import rag_search

    return rag_search(args)


def web_search_handler(args: WebSearchInput) -> WebSearchOutput:
    raise NotImplementedError("web.search is not implemented yet (issue #14)")


# Tool name (as in contracts.tool_schemas.TOOLS) -> handler.
HANDLERS = {
    "rag.search": rag_search_handler,
    "web.search": web_search_handler,
}
