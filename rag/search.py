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

import math
import re
import time
from collections import Counter

import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer

from config import retrieval
from config.paths import CHROMA_DIR
from contracts.tool_schemas import RagProduct, RagSearchInput, RagSearchOutput

CHROMA_PATH = str(CHROMA_DIR)
MODEL_NAME = retrieval.EMBEDDING_MODEL
COLLECTION = retrieval.COLLECTION_NAME
SNIPPET_CHARS = retrieval.SNIPPET_CHARS
LEXICAL_POOL = retrieval.LEXICAL_POOL

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
    """Load the model, collection and lowercase lookups once per process."""
    if _state:
        return _state
    col = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(COLLECTION)
    got = col.get(include=["metadatas"])
    metas = got["metadatas"]
    _state["lex"] = _build_lexical(got["ids"], metas)
    _state["col"] = col
    _state["model"] = SentenceTransformer(MODEL_NAME)
    _state["brands"] = {_key(m["brand"]): m["brand"] for m in metas if m.get("brand")}
    _state["categories"] = {m["category"].lower(): m["category"] for m in metas if m.get("category")}
    _state["subcategories"] = {m["subcategory"].lower(): m["subcategory"] for m in metas if m.get("subcategory")}
    return _state


def _snippet(document: str, title: str) -> str | None:
    """Document text is 'title. features. Recommended age: x'; drop the title, trim."""
    rest = document[len(title):].lstrip(". ").strip() if document.startswith(title) else document
    if not rest:
        return None
    return rest if len(rest) <= SNIPPET_CHARS else rest[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "..."


def _build_where(inp: RagSearchInput, st: dict) -> tuple[dict | None, dict, bool]:
    """Return (chroma where, filters_applied report, impossible). impossible=True means no product can match."""
    clauses: list[dict] = []
    applied: dict = {}
    impossible = False

    if inp.category:
        key = inp.category.lower()
        if key in st["categories"]:
            clauses.append({"category": st["categories"][key]})
            applied["category"] = st["categories"][key]
        elif key in st["subcategories"]:  # lets 'Puzzles' work as a category
            clauses.append({"subcategory": st["subcategories"][key]})
            applied["subcategory"] = st["subcategories"][key]
        else:
            applied["category"] = f"{inp.category} (no such category)"
            impossible = True

    if inp.brand:
        canon = st["brands"].get(_key(inp.brand))
        if canon:
            clauses.append({"brand": canon})
            applied["brand"] = canon
        else:
            applied["brand"] = f"{inp.brand} (no such brand)"
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

    if impossible:
        return RagSearchOutput(query=inp.query, filters_applied=applied, results=[],
                               took_ms=int((time.perf_counter() - t0) * 1000))

    lam = retrieval.HYBRID_LAMBDA  # read at call time so evaluation can sweep it
    emb = st["model"].encode([inp.query], normalize_embeddings=True)
    # exclude_features is a text match Chroma cannot express: over-fetch, then drop, then trim to top_k
    n_fetch = min(st["col"].count(), max(inp.top_k * 10, 50)) if (inp.exclude_features or lam > 0) else inp.top_k
    res = st["col"].query(query_embeddings=emb.tolist(), n_results=n_fetch, where=where,
                          include=["metadatas", "documents", "distances"])
    # candidates: (doc_id, meta, doc, score)
    cands = [(i, m, d, 1.0 - dist) for i, m, d, dist in
             zip(res["ids"][0], res["metadatas"][0], res["documents"][0], res["distances"][0])]

    if lam > 0:
        q_tokens = _tokens(inp.query)
        lex = st["lex"]
        allowed = set(st["col"].get(where=where, include=[])["ids"]) if where else None
        have = {c[0] for c in cands}
        scored = [(_bm25(lex, q_tokens, k), i) for k, i in enumerate(lex["ids"])
                  if (allowed is None or i in allowed) and i not in have]
        extra = [i for sc, i in sorted(scored, reverse=True)[:LEXICAL_POOL] if sc > 0]
        if extra:
            got = st["col"].get(ids=extra, include=["metadatas", "documents", "embeddings"])
            for i, m, d, e in zip(got["ids"], got["metadatas"], got["documents"], got["embeddings"]):
                cands.append((i, m, d, float(np.dot(emb[0], np.asarray(e)))))
        rescored = []
        for i, m, d, cos in cands:
            title_tokens = set(_tokens(f"{m['title']} {m.get('brand', '')}"))
            overlap = len(set(q_tokens) & title_tokens) / len(set(q_tokens)) if q_tokens else 0.0
            rescored.append((i, m, d, cos + lam * overlap))
        cands = sorted(rescored, key=lambda c: -c[3])

    excluded = [f.lower() for f in inp.exclude_features]
    products = []
    for doc_id, meta, doc, score in cands:
        warnings = meta["safety_warnings"].split(" | ") if meta.get("safety_warnings") else None
        if excluded:
            haystack = (doc + " " + " ".join(warnings or [])).lower()
            if any(term in haystack for term in excluded):
                continue
        products.append(RagProduct(
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
            features_snippet=_snippet(doc, meta["title"]),
            score=round(score, 4),
        ))
        if len(products) == inp.top_k:
            break
    return RagSearchOutput(query=inp.query, filters_applied=applied, results=products,
                           took_ms=int((time.perf_counter() - t0) * 1000))
