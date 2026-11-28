"""Agent config (non-secret). Owner: Devanshu. Env vars of the same name override."""

from __future__ import annotations

import os
import sys


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


# MCP server (stdio): Juan's server. Offline/mock: MCP_SERVER_ARGS="-m mocks.mcp_server".
MCP_SERVER_COMMAND: str = os.getenv("MCP_SERVER_COMMAND", sys.executable)
MCP_SERVER_ARGS: str = os.getenv("MCP_SERVER_ARGS", "-m mcp_server")
MCP_TOOL_TIMEOUT_S: float = _env_float("MCP_TOOL_TIMEOUT_S", 30.0)
MCP_FIRST_CALL_TIMEOUT_S: float = _env_float("MCP_FIRST_CALL_TIMEOUT_S", 120.0)
# The server loads its models before the handshake: ~12 s warm, ~70 s on a fresh venv.
MCP_STARTUP_TIMEOUT_S: float = _env_float("MCP_STARTUP_TIMEOUT_S", 180.0)

RAG_TOOL = "rag.search"
WEB_TOOL = "web.search"

# Planner / Retriever
DEFAULT_TOP_K: int = _env_int("GRAPH_TOP_K", 5)
WEB_MAX_RESULTS: int = _env_int("GRAPH_WEB_MAX_RESULTS", 5)
WEB_LOOKUPS_PER_RUN: int = _env_int("GRAPH_WEB_LOOKUPS", 3)

# Backup trigger for web.search if the Router misses it.
CURRENT_INFO_KEYWORDS: tuple[str, ...] = (
    "current", "currently", "latest", "right now", "today", "in stock", "available now",
    "availability", "price now", "current price", "still available", "on sale", "deal",
)

# Backup for the Router (#57): a request with one of these words is shopping, even if it is wrapped in urgency
# or tool names. Matched as whole words; plurals included.
SHOPPING_WORDS: tuple[str, ...] = (
    "toy", "game", "puzzle", "lego", "doll", "drone", "blocks", "building set", "playset", "plush",
    "stuffed animal", "action figure", "science kit", "chemistry set", "craft kit", "stem kit", "nerf",
    "board game", "card game", "rc car", "train set", "kite", "jigsaw",
)
# Router backstop for follow-ups (#96): a new message with one of these refers to earlier picks. Regex fragments.
FOLLOWUP_WORDS: tuple[str, ...] = (
    "cheapest", "cheaper", "most expensive", "which one", "which of", "these", "those", "them", "that one",
    "this one", r"the (first|second|third|last|other) one", "first one", "second one", "third one", "why",
    "compare", "difference", "better", "in stock", "how much", "more about", "tell me more", "picks?",
)

# Reconciliation
PRICE_CONFLICT_THRESHOLD: float = _env_float("PRICE_CONFLICT_THRESHOLD", 0.10)
TITLE_MATCH_THRESHOLD: float = _env_float("TITLE_MATCH_THRESHOLD", 0.6)
BRAND_TITLE_THRESHOLD: float = _env_float("BRAND_TITLE_THRESHOLD", 0.4)
# A live price outside this ratio of the catalog price is probably another listing; keep the catalog price.
PLAUSIBLE_PRICE_RATIO: tuple[float, float] = (0.4, 2.5)
# Resale marketplaces lose ties against retailers.
MARKETPLACE_DOMAINS: tuple[str, ...] = ("ebay.com",)
# Only product pages are matched to catalog products (#49): a search, category or store page has no single
# product's price. Patterns are regexes on the URL's path + query, checked after the domain. Tuned on
# data/logs/tool_calls.jsonl.
NON_PRODUCT_URL_PATTERNS: tuple[str, ...] = (
    r"/browse/", r"/search\b", r"[/?&](s|k|q)[=?/]", r"^/s$", r"/c/", r"^/b[/?]", r"/stores?/",
    r"/category/", r"/categories/", r"/collections?/(?!.*/products/)", r"/brand/", r"/shop/", r"/deals?\b",
    r"/reviews?/", r"/wirecutter/", r"/blog/",
)
PRODUCT_URL_PATTERNS: tuple[str, ...] = (
    r"/ip/",                                   # walmart
    r"/dp/[A-Z0-9]{10}", r"/gp/(aw/d|product)/[A-Z0-9]{10}", r"/clp/[A-Z0-9]{10}",  # amazon
    r"/p/.+/A-\d+", r"/itm/\d+",               # target, ebay
    r"/w/[^/]+/\d+",                           # barnes & noble
    r"/products?/", r"/prd-\d+", r"/pd/",      # kohls, shopify stores, others
    r"/\d{6,}(/|$|\?)",                        # any long numeric product id
)

# Answer
TOP_N_ANSWER: int = 3
SPOKEN_SUMMARY_MAX_WORDS: int = 40

# run_agent
RUN_TIMEOUT_S: float = _env_float("RUN_TIMEOUT_S", 240.0)  # must exceed MCP_STARTUP_TIMEOUT_S
