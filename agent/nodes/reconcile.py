"""Reconcile node (#49): match catalog to live results (SKU → brand+title → similarity), flag price conflicts.

Similarity ignores generic words and the brand, so two Hasbro board games don't match each other.
"""

from __future__ import annotations

import re

from config import graph as cfg
from contracts.state import AgentState, ReconciledProduct, log_step

_GENERIC = {
    "the", "and", "for", "with", "of", "a", "an", "to", "by", "in", "game", "games", "board", "card", "classic",
    "toy", "toys", "kit", "set", "family", "families", "kids", "children", "adults", "piece", "pieces", "price",
    "amazon", "walmart", "target", "com", "www", "ebay", "store", "buy", "online", "new", "edition",
}


def _words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _distinctive(title: str, brand: str | None) -> set[str]:
    return _words(title) - _GENERIC - _words(brand)


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
    best, method, score = None, "none", 0.0
    for w in web_results:
        m, s = _match(product, w)
        if m != "none" and (_METHOD_RANK[m], s) > (_METHOD_RANK[method], score):
            best, method, score = w, m, s

    catalog_price = product.get("price")
    live_price = best.get("price") if best else None
    availability = best.get("availability") if best else None
    conflict = bool(catalog_price and live_price
                    and abs(live_price - catalog_price) / catalog_price > cfg.PRICE_CONFLICT_THRESHOLD)

    notes = []
    if live_price is not None and (prefer_live or catalog_price is None):
        chosen, source = live_price, "web"
        why = "user asked for current info" if prefer_live else "catalog has no price"
        notes.append(f"Using live price ${live_price:.2f} from {best['source_domain']} ({why}).")
    elif catalog_price is not None:
        chosen, source = catalog_price, "catalog"
        if live_price is not None:
            notes.append("Using catalog price (user did not ask for current info).")
    else:
        chosen, source = None, "unknown"
        notes.append("No price in catalog or live results.")
    if conflict:
        pct = (live_price - catalog_price) / catalog_price * 100
        notes.append(f"Price conflict: live ${live_price:.2f} vs catalog ${catalog_price:.2f} "
                     f"({pct:+.0f}%). Catalog data is from 2020.")
    if availability == "out_of_stock":
        notes.append(f"Live result says out of stock at {best['source_domain']}.")

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
    summary = f"{len(matched)}/{len(reconciled)} catalog products matched to live results"
    if conflicts:
        summary += f"; {len(conflicts)} price conflict(s): " + ", ".join(r["doc_id"] for r in conflicts)
    return {"reconciled": reconciled,
            **log_step("reconcile", summary,
                       matches=[{k: r[k] for k in ("doc_id", "match_method", "match_score", "live_url")} for r in matched],
                       conflicts=[{k: r[k] for k in ("doc_id", "catalog_price", "live_price", "chosen_price",
                                                     "price_source", "note")} for r in conflicts])}
