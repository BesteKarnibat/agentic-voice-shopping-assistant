"""web.search: Serper client and normalization into WebSearchOutput.

Uses Serper's /search endpoint, whose results carry real, citable store URLs. The USD price and
availability are parsed from the snippet when it states them; otherwise they stay None / "unknown".
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
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


def is_allowed(domain: str) -> bool:
    """True if the domain is on the allow-list or is a subdomain of an allowed domain."""
    return any(domain == d or domain.endswith("." + d) for d in cfg.ALLOWED_DOMAINS)


class RateLimitError(RuntimeError):
    pass


class RateLimiter:
    """Sliding window: at most `calls` acquisitions per `window_s` seconds."""

    def __init__(self, calls: int, window_s: float, clock=time.monotonic):
        self.calls, self.window_s, self.clock = calls, window_s, clock
        self._times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self.clock()
            while self._times and now - self._times[0] >= self.window_s:
                self._times.popleft()
            if len(self._times) >= self.calls:
                wait = self.window_s - (now - self._times[0])
                raise RateLimitError(f"web.search rate limit reached; retry in {wait:.0f}s")
            self._times.append(now)


class TTLCache:
    def __init__(self, ttl_s: float, clock=time.monotonic):
        self.ttl_s, self.clock = ttl_s, clock
        self._data: dict[tuple, tuple[float, WebSearchOutput]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple) -> WebSearchOutput | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if self.clock() - stored_at >= self.ttl_s:
                del self._data[key]
                return None
            return value

    def put(self, key: tuple, value: WebSearchOutput) -> None:
        with self._lock:
            self._data[key] = (self.clock(), value)


_cache = TTLCache(cfg.CACHE_TTL_S)
_limiter = RateLimiter(cfg.RATE_LIMIT_CALLS, cfg.RATE_LIMIT_WINDOW_S)


def normalize(args: WebSearchInput, payload: dict) -> WebSearchOutput:
    results = []
    for item in payload.get("organic", []):
        url, title = item.get("link"), item.get("title")
        if not url or not title:
            continue  # a result without a URL cannot be cited
        if not is_allowed(source_domain(url)):
            continue  # domain restriction
        if len(results) == args.max_results:
            break
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
    key = (" ".join(args.query.lower().split()), args.max_results)
    hit = _cache.get(key)
    if hit is not None:
        return hit.model_copy(update={"cached": True})

    load_dotenv(ENV_FILE)
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        raise RuntimeError("SERPER_API_KEY is not set (add it to .env)")
    _limiter.acquire()
    resp = httpx.post(
        cfg.SERPER_URL,
        headers={"X-API-KEY": api_key},
        json={"q": args.query, "num": cfg.SERPER_NUM_RESULTS, "gl": "us"},
        timeout=cfg.SERPER_TIMEOUT_S,
    )
    resp.raise_for_status()
    out = normalize(args, resp.json())
    _cache.put(key, out)
    return out
