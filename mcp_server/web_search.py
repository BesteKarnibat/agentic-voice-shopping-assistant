"""web.search: Serper client and normalization into WebSearchOutput.

Uses Serper's /search endpoint, whose results carry real, citable store URLs. The USD price and
availability are parsed from the snippet when it states them; otherwise they stay None / "unknown".
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from config import web as cfg
from config.paths import ENV_FILE
from contracts.tool_schemas import WebResult, WebSearchInput, WebSearchOutput

_PRICE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")
_OUT_RE = re.compile(r"out of stock|sold out|unavailable|currently unavailable", re.I)
_IN_RE = re.compile(r"in stock|available now|add to cart", re.I)


def parse_price(text: str) -> float | None:
    """First USD amount in the text, e.g. 'Price: $9.99' -> 9.99. Other currencies are ignored."""
    m = _PRICE_RE.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def parse_availability(text: str) -> str:
    if _OUT_RE.search(text):
        return "out_of_stock"
    if _IN_RE.search(text):
        return "in_stock"
    return "unknown"


def source_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def normalize(args: WebSearchInput, payload: dict) -> WebSearchOutput:
    results = []
    for item in payload.get("organic", [])[: args.max_results]:
        url, title = item.get("link"), item.get("title")
        if not url or not title:
            continue  # a result without a URL cannot be cited
        snippet = item.get("snippet", "")
        results.append(
            WebResult(
                title=title,
                url=url,
                snippet=snippet,
                source_domain=source_domain(url),
                price=parse_price(snippet),
                availability=parse_availability(snippet),
            )
        )
    return WebSearchOutput(
        query=args.query,
        provider=cfg.PROVIDER_NAME,
        cached=False,
        retrieved_at=datetime.now(timezone.utc),
        results=results,
    )


def web_search(args: WebSearchInput) -> WebSearchOutput:
    load_dotenv(ENV_FILE)
    key = os.getenv("SERPER_API_KEY")
    if not key:
        raise RuntimeError("SERPER_API_KEY is not set (add it to .env)")
    resp = httpx.post(
        cfg.SERPER_URL,
        headers={"X-API-KEY": key},
        json={"q": args.query, "num": args.max_results, "gl": "us"},
        timeout=cfg.SERPER_TIMEOUT_S,
    )
    resp.raise_for_status()
    return normalize(args, resp.json())
