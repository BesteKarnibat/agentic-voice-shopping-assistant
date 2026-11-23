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

from config.paths import CHROMA_DIR, PRODUCTS_PARQUET
from config.retrieval import COLLECTION_NAME, EMBEDDING_MODEL

MODEL = EMBEDDING_MODEL
COLLECTION = COLLECTION_NAME
BATCH = 256


def doc_text(r):
    parts = [r["title"]]
    if r["features"] is not None and len(r["features"]):
        parts.append(" ".join(r["features"]))
    if isinstance(r["age_range"], str):
        parts.append(f"Recommended age: {r['age_range']}")
    return ". ".join(parts)


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
    return m


def main(parquet=PRODUCTS_PARQUET, chroma_dir=CHROMA_DIR):
    df = pd.read_parquet(parquet)
    texts = [doc_text(r) for _, r in df.iterrows()]
    metas = [metadata(r) for _, r in df.iterrows()]
    t0 = time.time()
    model = SentenceTransformer(MODEL)
    emb = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    t_embed = time.time() - t0

    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        client.delete_collection(COLLECTION)  # rebuild from scratch
    except Exception:
        pass
    col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine", "embedding_model": MODEL})
    for i in range(0, len(df), BATCH):
        s = slice(i, i + BATCH)
        col.add(ids=df["doc_id"].tolist()[s], embeddings=emb[s].tolist(),
                documents=texts[s], metadatas=metas[s])
    print(f"indexed {col.count()} docs | model {MODEL} | dim {emb.shape[1]} | embed {t_embed:.0f}s | total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
