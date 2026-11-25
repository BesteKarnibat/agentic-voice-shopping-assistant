"""Build the Chroma vector index from products.parquet (issue #22).

    uv run doit index               # preferred
    uv run python -m rag.build_index

Reads PRODUCTS_PARQUET, writes CHROMA_DIR (config/paths.py). Model and collection name: config/retrieval.py.
Index and query MUST use the same embedding model.
"""
import time

import chromadb
import pandas as pd
from sentence_transformers import SentenceTransformer

from config import retrieval
from config.paths import CHROMA_DIR, PRODUCTS_PARQUET
from rag import texts

BATCH = 256


def metadata(r):
    m = {"sku": r["sku"], "title": r["title"], "category": r["category"],
         "price_is_range": bool(r["price_is_range"])}
    # Chroma rejects None/NaN metadata: omit unknown values so filters skip them
    for k in ("brand", "subcategory", "age_range", "product_url"):
        if isinstance(r[k], str):
            m[k] = r[k]
    if pd.notna(r["price"]):
        m["price"] = float(r["price"])
    # age: store bounds only when stated; age_known lets filters keep "not stated" products
    m["age_known"] = bool(pd.notna(r["min_age_years"]))
    if m["age_known"]:
        m["min_age_years"] = float(r["min_age_years"])
    if pd.notna(r["max_age_years"]):
        m["max_age_years"] = float(r["max_age_years"])
    # Chroma metadata cannot hold lists: join warnings, rag_search splits them again
    if r["safety_warnings"] is not None and len(r["safety_warnings"]):
        m["safety_warnings"] = " | ".join(r["safety_warnings"])
    # what the listing says, kept apart from the embedded text (which may carry brand/category labels we added)
    m["listing_text"] = texts.listing_text(r)
    snip = texts.snippet(r, retrieval.SNIPPET_CHARS)
    if snip:
        m["snippet"] = snip
    return m


def main(parquet=PRODUCTS_PARQUET, chroma_dir=CHROMA_DIR):
    df = pd.read_parquet(parquet)
    rows = [r for _, r in df.iterrows()]
    embedded = [texts.embed_text(r, retrieval.EMBED_TEXT) for r in rows]
    metas = [metadata(r) for r in rows]
    t0 = time.time()
    model = SentenceTransformer(retrieval.EMBEDDING_MODEL)
    emb = model.encode([retrieval.DOC_PREFIX + t for t in embedded], batch_size=64, normalize_embeddings=True,
                       show_progress_bar=False)
    t_embed = time.time() - t0

    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        client.delete_collection(retrieval.COLLECTION_NAME)  # rebuild from scratch
    except Exception:
        pass
    col = client.create_collection(retrieval.COLLECTION_NAME, metadata={
        "hnsw:space": "cosine", "embedding_model": retrieval.EMBEDDING_MODEL, "embed_text": retrieval.EMBED_TEXT,
        "query_prefix": retrieval.QUERY_PREFIX, "doc_prefix": retrieval.DOC_PREFIX})
    ids = df["doc_id"].tolist()
    for i in range(0, len(df), BATCH):
        s = slice(i, i + BATCH)
        col.add(ids=ids[s], embeddings=emb[s].tolist(), documents=embedded[s], metadatas=metas[s])
    print(f"indexed {col.count()} docs | model {retrieval.EMBEDDING_MODEL} | text {retrieval.EMBED_TEXT} | dim {emb.shape[1]} "
          f"| embed {t_embed:.0f}s | total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
