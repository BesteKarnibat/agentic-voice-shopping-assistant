"""Reconcile node (#49): match catalog to live results (SKU → brand+title → similarity), flag price conflicts.

Similarity ignores generic words and the brand, so two Hasbro board games don't match each other.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from config import graph as cfg
from contracts.state import AgentState, ReconciledProduct, log_step

_GENERIC = {
    "the", "and", "for", "with", "of", "a", "an", "to", "by", "in", "game", "games", "board", "card", "classic",
    "toy", "toys", "kit", "set", "family", "families", "kids", "children", "adults", "piece", "pieces", "price",
    "amazon", "walmart", "target", "com", "www", "ebay", "store", "buy", "online", "new", "edition",
}


def _words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def short_title(title: str, max_words: int = 8) -> str:
    """Head of a catalog title, before the marketing text ('Voila! Board Game - A Fast and Fun ...')."""
    return " ".join(re.split(r" - | – |\(|,|\|", title)[0].split()[:max_words])


def _distinctive(title: str, brand: str | None) -> set[str]:
    return _words(short_title(title)) - _GENERIC - _words(brand)


_NON_PRODUCT_RE = re.compile("|".join(cfg.NON_PRODUCT_URL_PATTERNS), re.I)
_PRODUCT_RE = re.compile("|".join(cfg.PRODUCT_URL_PATTERNS))


def is_product_page(url: str | None) -> bool:
    """A single product's page, not a search, category, store or review page (#49)."""
    parts = urlsplit(url or "")
    tail = parts.path + ("?" + parts.query if parts.query else "")
    return bool(parts.netloc) and not _NON_PRODUCT_RE.search(tail) and bool(_PRODUCT_RE.search(tail))


def _store(web: dict) -> str:
    return web.get("source_domain") or urlsplit(web.get("url") or "").netloc.removeprefix("www.") or "the store"


def _is_marketplace(web: dict) -> bool:
    domain = web.get("source_domain") or ""
    return any(domain == d or domain.endswith("." + d) for d in cfg.MARKETPLACE_DOMAINS)


def _match(product: dict, web: dict) -> tuple[str, float]:
    sku = (product.get("sku") or "").lower()
    haystack = " ".join([web.get("url", ""), web.get("title", ""), web.get("snippet", "")]).lower()
    if sku and len(sku) >= 6 and sku in haystack:
        return "sku", 1.0
    cat_words = _distinctive(product["title"], product.get("brand"))
    if not cat_words:
        return "none", 0.0
    web_words = _words(web.get("title")) | _words(web.get("url"))
    score = round(len(cat_words & web_words) / len(cat_words), 3)
    brand = (product.get("brand") or "").lower()
    if brand and brand in haystack and score >= cfg.BRAND_TITLE_THRESHOLD:
        return "brand_title", score
    if score >= cfg.TITLE_MATCH_THRESHOLD:
        return "similarity", score
    return "none", score


_METHOD_RANK = {"sku": 3, "brand_title": 2, "similarity": 1, "none": 0}


def reconcile_product(product: dict, web_results: list[dict], prefer_live: bool) -> ReconciledProduct:
    # Rank: match method, score, then retailers over marketplaces (resale listings), then listings with a price.
    best, method, score, best_key = None, "none", 0.0, None
    for w in web_results:
        if not is_product_page(w.get("url")):
            continue
        m, s = _match(product, w)
        if m == "none":
            continue
        key = (_METHOD_RANK[m], s, not _is_marketplace(w), w.get("price") is not None)
        if best_key is None or key > best_key:
            best, method, score, best_key = w, m, s, key

    catalog_price = product.get("price")
    live_price = best.get("price") if best else None
    availability = best.get("availability") if best else None
    conflict = bool(catalog_price and live_price
                    and abs(live_price - catalog_price) / catalog_price > cfg.PRICE_CONFLICT_THRESHOLD)
    lo, hi = cfg.PLAUSIBLE_PRICE_RATIO
    implausible = bool(catalog_price and live_price and not lo <= live_price / catalog_price <= hi)

    # Labels the Answerer repeats: "catalog price (2020)" and "current price at <store>".
    store = _store(best) if best else None
    cat_label = f"${catalog_price:.2f} catalog price (2020)" if catalog_price is not None else None
    live_label = f"${live_price:.2f} current price at {store}" if live_price is not None else None
    notes = []
    if implausible:
        chosen, source = catalog_price, "catalog"
        notes.append(f"Price: {cat_label}. The {live_label} looks like a different listing "
                     f"(used, bundle or accessory), so it is not used.")
    elif live_price is not None and (prefer_live or catalog_price is None):
        chosen, source = live_price, "web"
        notes.append(f"Price: {live_label}" + (" (the catalog has no price)." if catalog_price is None else "."))
    elif catalog_price is not None:
        chosen, source = catalog_price, "catalog"
        if live_price is not None:
            notes.append(f"Price: {cat_label}; the user did not ask for current prices ({live_label}).")
        elif best is not None and prefer_live:
            notes.append(f"Price: {cat_label}. The listing at {store} shows no current price.")
        else:
            notes.append(f"Price: {cat_label}.")
    else:
        chosen, source = None, "unknown"
        notes.append("No price in the catalog or the live results.")
    if conflict:
        pct = (live_price - catalog_price) / catalog_price * 100
        notes.append(f"Price conflict: {live_label} vs {cat_label} ({pct:+.0f}%).")
    if availability == "out_of_stock":
        notes.append(f"Live result says out of stock at {store}.")

    return {
        "doc_id": product["doc_id"],
        "title": product["title"],
        "brand": product.get("brand"),
        "catalog_price": catalog_price,
        "live_price": live_price,
        "live_url": best.get("url") if best else None,
        "availability": availability,
        "match_method": method,
        "match_score": score,
        "price_conflict": conflict,
        "chosen_price": chosen,
        "price_source": source,
        "note": " ".join(notes) or None,
    }


def reconcile_node(state: AgentState) -> dict:
    rag = state.get("rag_results") or []
    web = state.get("web_results") or []
    prefer_live = bool((state.get("constraints") or {}).get("wants_current_info")) or state.get("intent") == "price_check"
    reconciled = [reconcile_product(p, web, prefer_live) for p in rag]
    matched = [r for r in reconciled if r["match_method"] != "none"]
    conflicts = [r for r in reconciled if r["price_conflict"]]
    not_product = [w["url"] for w in web if not is_product_page(w.get("url"))]
    summary = f"{len(matched)}/{len(reconciled)} catalog products matched to live results"
    if not_product:
        summary += f"; ignored {len(not_product)} non-product page(s)"
    if conflicts:
        summary += f"; {len(conflicts)} price conflict(s): " + ", ".join(r["doc_id"] for r in conflicts)
    return {"reconciled": reconciled,
            **log_step("reconcile", summary, ignored_non_product_urls=not_product,
                       matches=[{k: r[k] for k in ("doc_id", "match_method", "match_score", "live_url")} for r in matched],
                       conflicts=[{k: r[k] for k in ("doc_id", "catalog_price", "live_price", "chosen_price",
                                                     "price_source", "note")} for r in conflicts])}
