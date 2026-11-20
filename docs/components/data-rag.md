# Data preprocessing and indexing

**Owner:** Akshaj · **Branch:** `feature/rag` · **Status:** todo
**Code:** TODO (download script, cleaning, index build, `rag_search()`) · **Contract:** `RagSearchInput` / `RagProduct` in [../../contracts/tool_schemas.py](../../contracts/tool_schemas.py)

## 1. Dataset
<!-- Source, slug, license, size, which slice and why. Which fields exist (rating, ingredients, reviews) and which are missing. -->
TODO

## 2. Download
<!-- Exact command, Kaggle credentials needed, where files land under data/. -->
TODO

## 3. Cleaning and curation
<!-- Steps in order: filters, dedup, missing values, parsing ingredients/price/rating, how doc_id is built. Rows before → after. -->

| Step | What it does | Rows before → after |
|------|--------------|---------------------|
| TODO | | |

## 4. Document schema
<!-- Final columns of the processed parquet and how each maps to RagProduct. One illustrative example. -->
TODO

## 5. Indexing
<!-- Chunking (what text is embedded), embedding model, vector store, index parameters, build time and size. -->
TODO

## 6. Retrieval (`rag_search()`)
<!-- Top-k, filters (price, rating, ingredients), scoring, what is returned, how doc_id is preserved for citations. -->
TODO

## 7. Retrieval evaluation
<!-- Queries, expected products, metrics (e.g. recall@k, MRR), results table. Link the evaluation plan [CP2]. -->
TODO

## 8. Decisions, limitations, and known issues
TODO

## 9. Rebuild from scratch
```bash
# TODO: exact commands (ideally `uv run doit` tasks)
```
