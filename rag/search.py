"""rag_search(): hybrid retrieval (vector similarity + metadata filters) over the Chroma index. Issue #23.

    from rag.search import rag_search
    out = rag_search(RagSearchInput(query="wooden puzzle", max_price=20))

Signature follows contracts/tool_schemas.py. Sync, returns plain pydantic models.
Behaviour for the Juan <-> Akshaj agreement (#6):
  * no matches -> empty `results` (never an exception)
  * filters the data cannot support (rating) are NOT applied and are reported
    in `filters_applied` so the caller never mistakes "ignored" for "satisfied"
Hybrid scoring: score = cosine(query, doc) + HYBRID_LAMBDA * title_overlap, where title_overlap is the share of
the query's content words found in the product's title/brand. Candidates come from the vector top-N plus a BM25
(title/brand) top-N, so an exact product name is found even when the embedding ranks it low. HYBRID_LAMBDA=0
gives pure vector search.
Config: config/retrieval.py (EMBEDDING_MODEL must match the model used by rag.build_index, HYBRID_LAMBDA) and
config/paths.py (CHROMA_DIR).
"""
from __future__ import annotations

import difflib
import math
import re
import time
from collections import Counter

import chromadb
import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from config import retrieval
from config.paths import CHROMA_DIR
from rag import texts
from contracts.tool_schemas import RagProduct, RagSearchInput, RagSearchOutput

CHROMA_PATH = str(CHROMA_DIR)

STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "of", "to", "in", "on", "at", "by", "from", "my", "your",
    "is", "are", "that", "this", "it", "its", "i", "me", "we", "you", "some", "any", "one", "up", "as",
    "kid", "child", "toy", "need", "want", "looking", "find", "get", "something", "good", "best", "nice",
}

_state: dict = {}


def _key(text: str) -> str:
    """Lookup key tolerant of speech/typing variants: 'Fisher Price' == 'Fisher-Price', 'and' == '&'."""
    t = text.lower().replace(" and ", " & ")
    return "".join(ch for ch in t if ch.isalnum() or ch == "&")


def _tokens(text: str) -> list[str]:
    """Lowercase alphanumeric content words, with trivial plural folding (puzzles -> puzzle)."""
    out = []
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        if t not in STOPWORDS:
            out.append(t)
    return out


def _stem(word: str) -> str:
    """Light stemmer for phrase matching: batteries -> battery, parts -> part, glass stays."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _phrase(text: str) -> str:
    """Normalized, space-padded text so ' small part ' can be searched as a whole phrase."""
    return " " + " ".join(_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())) + " "


# Router categories are free text. These map common wording onto the real subcategory names.
CATEGORY_SYNONYMS = {
    "costume": "Dress Up & Pretend Play", "dress": "Dress Up & Pretend Play", "pretend": "Dress Up & Pretend Play",
    "lego": "Building Toys", "block": "Building Toys", "brick": "Building Toys", "construction": "Building Toys",
    "car": "Play Vehicles", "truck": "Play Vehicles", "vehicle": "Play Vehicles", "train": "Play Vehicles",
    "plush": "Stuffed Animals & Plush Toys", "teddy": "Stuffed Animals & Plush Toys",
    "board": "Games & Accessories", "card": "Games & Accessories", "game": "Games & Accessories",
    "figure": "Toy Figures & Playsets", "action": "Toy Figures & Playsets",
    "baby": "Baby & Toddler Toys", "toddler": "Baby & Toddler Toys", "infant": "Baby & Toddler Toys",
    "educational": "Learning & Education", "stem": "Learning & Education", "science": "Learning & Education",
    "craft": "Arts & Crafts", "art": "Arts & Crafts", "drawing": "Arts & Crafts",
    "scooter": "Tricycles, Scooters & Wagons", "tricycle": "Tricycles, Scooters & Wagons",
    "outdoor": "Sports & Outdoor Play", "sport": "Sports & Outdoor Play",
}


def _resolve_category(text: str, st: dict) -> tuple[str, str] | None:
    """Map a free-text category to ("category"|"subcategory", catalog name), or None if nothing fits.
    Order: exact name, then word overlap with a subcategory name, then the synonym table."""
    low = text.lower().strip()
    if low in st["categories"]:
        return "category", st["categories"][low]
    if low in st["subcategories"]:
        return "subcategory", st["subcategories"][low]
    raw = {_stem(w) for w in re.findall(r"[a-z0-9]+", low)}
    if raw and raw <= {"toy", "and", "the", "a"}:  # "toys": the whole catalog is Toys & Games
        return "category", next(iter(st["categories"].values()))
    words = raw - {"and", "the", "a", "toy"}
    if not words:
        return None
    best, best_score, tie = None, 0.0, False
    for sub in st["subcategories"].values():
        sub_words = {_stem(w) for w in re.findall(r"[a-z0-9]+", sub.lower())}
        score = len(words & sub_words) / len(words)
        if score > best_score:
            best, best_score, tie = sub, score, False
        elif score == best_score and score > 0:
            tie = True
    if best and best_score >= 0.5 and not tie:
        return "subcategory", best
    for w in words:
        if w in CATEGORY_SYNONYMS:
            return "subcategory", CATEGORY_SYNONYMS[w]
    return None


def _resolve_brand(text: str, st: dict) -> str | None:
    """Exact (speech-tolerant) match, else the longest known brand that the text starts with
    ("Fisher Price Little People" -> Fisher-Price), else a close spelling. None if unknown."""
    key = _key(text)
    if key in st["brands"]:
        return st["brands"][key]
    starts = [k for k in st["brands"] if len(k) >= 5 and key.startswith(k)]
    if starts:
        return st["brands"][max(starts, key=len)]
    close = difflib.get_close_matches(key, list(st["brands"]), n=1, cutoff=0.88)
    return st["brands"][close[0]] if close else None


def _build_lexical(ids: list[str], metas: list[dict]) -> dict:
    """BM25 statistics over title + brand."""
    docs = [Counter(_tokens(f"{m['title']} {m.get('brand', '')}")) for m in metas]
    df: Counter = Counter()
    for d in docs:
        df.update(d.keys())
    n = len(docs)
    return {"ids": ids, "docs": docs, "df": df, "n": n,
            "avgdl": sum(sum(d.values()) for d in docs) / max(n, 1),
            "pos": {i: k for k, i in enumerate(ids)}}


def _bm25(lex: dict, q_tokens: list[str], idx: int, k1: float = 1.5, b: float = 0.75) -> float:
    d = lex["docs"][idx]
    dl = sum(d.values())
    score = 0.0
    for t in set(q_tokens):
        f = d.get(t, 0)
        if not f:
            continue
        idf = math.log(1 + (lex["n"] - lex["df"][t] + 0.5) / (lex["df"][t] + 0.5))
        score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / lex["avgdl"]))
    return score


def _load():
    """Load the model, optional reranker, collection and lookups once per process."""
    if _state:
        return _state
    col = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(retrieval.COLLECTION_NAME)
    built_with = col.metadata or {}
    if built_with.get("embedding_model") not in (None, retrieval.EMBEDDING_MODEL):
        raise RuntimeError(f"index was built with {built_with.get('embedding_model')} but config/retrieval.py says "
                           f"{retrieval.EMBEDDING_MODEL}: rebuild with `uv run doit clean index index`")
    got = col.get(include=["metadatas"])
    metas = got["metadatas"]
    _state["lex"] = _build_lexical(got["ids"], metas)
    _state["col"] = col
    _state["model"] = SentenceTransformer(retrieval.EMBEDDING_MODEL)
    _state["reranker"] = CrossEncoder(retrieval.RERANKER_MODEL, max_length=retrieval.RERANK_MAX_LENGTH) if retrieval.RERANKER_MODEL else None
    _state["brands"] = {_key(m["brand"]): m["brand"] for m in metas if m.get("brand")}
    _state["categories"] = {m["category"].lower(): m["category"] for m in metas if m.get("category")}
    _state["subcategories"] = {m["subcategory"].lower(): m["subcategory"] for m in metas if m.get("subcategory")}
    return _state


def _passage(meta: dict) -> str:
    """The text a reranker reads for one product (see rag/texts.py)."""
    return texts.passage_from_metadata(meta)


def _build_where(inp: RagSearchInput, st: dict) -> tuple[dict | None, dict, bool]:
    """Return (chroma where, filters_applied report, impossible). impossible=True means no product can match."""
    clauses: list[dict] = []
    applied: dict = {}
    impossible = False

    if inp.category:
        hit = _resolve_category(inp.category, st)
        if hit:
            clauses.append({hit[0]: hit[1]})
            applied[hit[0]] = hit[1] if hit[1].lower() == inp.category.lower() else f"{hit[1]} (from '{inp.category}')"
        else:  # the Router's wording is free text: do not return nothing, search without it and say so
            applied["category"] = f"'{inp.category}' matches no catalog category: filter not applied"

    if inp.brand:
        canon = _resolve_brand(inp.brand, st)
        if canon:
            clauses.append({"brand": canon})
            applied["brand"] = canon if _key(canon) == _key(inp.brand) else f"{canon} (from '{inp.brand}')"
        else:
            applied["brand"] = f"{inp.brand} (no such brand)"
            impossible = True

    if inp.min_price is not None and inp.max_price is not None and inp.min_price > inp.max_price:
        applied["price"] = "min_price is above max_price: no product can match"
        impossible = True
    if inp.min_price is not None:
        clauses.append({"price": {"$gte": inp.min_price}})
        applied["min_price"] = inp.min_price
    if inp.max_price is not None:
        clauses.append({"price": {"$lte": inp.max_price}})
        applied["max_price"] = inp.max_price

    # Children's age: drop products whose minimum age is above the child's age.
    # Products with no stated age are KEPT (age_known=False): None means "not stated", not "unsafe".
    if inp.child_age_years is not None:
        clauses.append({"$or": [{"min_age_years": {"$lte": inp.child_age_years}}, {"age_known": False}]})
        applied["child_age_years"] = inp.child_age_years
    if inp.exclude_features:
        applied["exclude_features"] = list(inp.exclude_features)  # applied after retrieval, see rag_search

    # The dataset has no ratings: report instead of silently dropping everything.
    if inp.min_rating is not None:
        applied["min_rating"] = "not applied: catalog has no rating data"

    where = None if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}
    return where, applied, impossible


def rag_search(inp: RagSearchInput) -> RagSearchOutput:
    t0 = time.perf_counter()
    st = _load()
    where, applied, impossible = _build_where(inp, st)
    if not inp.query.strip():  # the contract only checks length, so "   " gets through
        applied["query"] = "blank query: nothing to search for"
        impossible = True

    if impossible:
        return RagSearchOutput(query=inp.query, filters_applied=applied, results=[],
                               took_ms=int((time.perf_counter() - t0) * 1000))

    lam = retrieval.HYBRID_LAMBDA  # read at call time so evaluation can sweep it
    reranker = st["reranker"]
    emb = st["model"].encode([retrieval.QUERY_PREFIX + inp.query], normalize_embeddings=True)
    # a pool is needed whenever candidates are rescored, filtered by text, or reranked
    pooled = bool(inp.exclude_features or lam > 0 or reranker)
    n_fetch = min(st["col"].count(), max(inp.top_k * 10, retrieval.VECTOR_POOL)) if pooled else inp.top_k
    res = st["col"].query(query_embeddings=emb.tolist(), n_results=n_fetch, where=where,
                          include=["metadatas", "distances"])
    cands = [(i, m, 1.0 - dist) for i, m, dist in zip(res["ids"][0], res["metadatas"][0], res["distances"][0])]

    if lam > 0:
        q_tokens = _tokens(inp.query)
        lex = st["lex"]
        allowed = set(st["col"].get(where=where, include=[])["ids"]) if where else None
        have = {c[0] for c in cands}
        scored = [(_bm25(lex, q_tokens, k), i) for k, i in enumerate(lex["ids"])
                  if (allowed is None or i in allowed) and i not in have]
        extra = [i for sc, i in sorted(scored, reverse=True)[:retrieval.LEXICAL_POOL] if sc > 0]
        if extra:
            got = st["col"].get(ids=extra, include=["metadatas", "embeddings"])
            for i, m, e in zip(got["ids"], got["metadatas"], got["embeddings"]):
                cands.append((i, m, float(np.dot(emb[0], np.asarray(e)))))
        rescored = []
        for i, m, cos in cands:
            title_tokens = set(_tokens(f"{m['title']} {m.get('brand', '')}"))
            overlap = len(set(q_tokens) & title_tokens) / len(set(q_tokens)) if q_tokens else 0.0
            rescored.append((i, m, cos + lam * overlap))
        cands = sorted(rescored, key=lambda c: -c[2])

    # text exclusion on what the listing says (not on labels we added), before reranking so top_k stays full
    excluded = [_phrase(f) for f in inp.exclude_features if f.strip()]
    kept = []
    for doc_id, meta, score in cands:
        warnings = meta["safety_warnings"].split(" | ") if meta.get("safety_warnings") else None
        if excluded:
            haystack = _phrase(meta.get("listing_text", meta["title"]) + " " + " ".join(warnings or []))
            if any(term in haystack for term in excluded):
                continue
        kept.append((doc_id, meta, score, warnings))

    if reranker and kept:
        pool = kept[:max(retrieval.RERANK_TOP_N, inp.top_k)]
        ce = reranker.predict([(inp.query, _passage(m)) for _, m, _, _ in pool], batch_size=32, show_progress_bar=False)
        order = sorted(range(len(pool)), key=lambda j: -ce[j])[:inp.top_k]
        ranked = [(pool[j][0], pool[j][1], 1.0 / (1.0 + math.exp(-float(ce[j]))), pool[j][3]) for j in order]
    else:
        ranked = kept[:inp.top_k]

    products = [RagProduct(
        doc_id=doc_id,
        sku=meta.get("sku"),
        title=meta["title"],
        brand=meta.get("brand"),
        category=meta.get("category"),
        price=meta.get("price"),
        rating=None,
        min_age_years=meta.get("min_age_years"),
        max_age_years=meta.get("max_age_years"),
        safety_warnings=warnings,
        features_snippet=meta.get("snippet"),
        score=round(score, 4),
    ) for doc_id, meta, score, warnings in ranked]
    return RagSearchOutput(query=inp.query, filters_applied=applied, results=products,
                           took_ms=int((time.perf_counter() - t0) * 1000))
