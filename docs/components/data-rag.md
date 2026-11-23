# Data preprocessing and indexing

**Owner:** Akshaj · **Branch:** `feature/rag` · **Status:** draft
**Code:** [../../rag/](../../rag/) (`preprocess.py`, `build_index.py`, `search.py`), settings in [../../config/retrieval.py](../../config/retrieval.py) · **Contract:** `RagSearchInput` / `RagProduct` in [../../contracts/tool_schemas.py](../../contracts/tool_schemas.py)

## 1. Dataset
Amazon Product Dataset 2020 (PromptCloud, Kaggle `promptcloud/amazon-product-dataset-2020`), the 10,002-row marketing sample. **Slice: Toys & Games, 6,662 products, 20 subcategories.**

Why not Household Cleaning (the assignment's example): cleaning products barely exist in this file (all of "Health & Household" has 23 rows), while Toys & Games is 67% of it with 97% of products having a price and features. Toys also bring a better safety constraint: the child's age.

| Field | In the raw file | Result |
|---|---|---|
| Star rating, reviews | none | `rating` always `None`; `reviews.parquet` not built; `min_rating` cannot filter |
| Ingredients | 100% empty | dropped from the contract (PR #78) |
| `Brand Name`, `Asin`, `Sku` | 100% empty | recovered from other fields (section 3) |
| Age range | in the specification text for 72% | parsed |
| Safety warnings | in the listing text for ~1% | keyword-extracted |

## 2. Download
`uv run doit download_kaggle_dataset` (needs `KAGGLE_API_TOKEN` in `.env`). The CSV lands at `KAGGLE_CSV` in `config/paths.py`, under the gitignored `data/`.

## 3. Cleaning and curation
`uv run doit preprocess` writes `data/processed/products.parquet` and a 100-product `products_sample.json`.

| Column | Rule | Unknown |
|---|---|---|
| `doc_id` | `Uniq Id`, unique and stable across rebuilds (used for citations) | n/a |
| `sku` | ASIN parsed from `/dp/<ASIN>` in `Product Url` | `None` |
| `brand` | 1) `Manufacturer:` field (300 rows), 2) curated list of ~70 multi-word brands matched on the title prefix (1,104), 3) first title word (4,986), 4) `None` when the first word is a description such as "Remote" or "Wooden" (272). `brand_source` records the rule | `None` (4.1%) |
| `price` | first dollar amount; for a range the lowest (`price_is_range`, 25 rows) | `None` (1.3%) |
| `features` | `About Product` split into a list, boilerplate line removed | `None` (2.6%) |
| `min_age_years`, `max_age_years` | structured age field, converted to years (4,772 rows), else text such as "Ages 5+" (173). Corrupt ranges like "14-1 years" keep only the minimum | `None` (min 26%, max 59%) |
| `safety_warnings` | keywords in title, features and technical details: choking hazard, small parts, button battery, magnets, suffocation, sharp edges, "not for children under N" | `None` (98.6%) |

Rows: 10,002 raw, 6,662 after the Toys & Games filter, no rows dropped after that. **Unknown is always `None`, never 0, `[]` or "unknown".** "No warning" means "not stated", never "safe".

## 4. Document schema
Columns of `products.parquet`: `doc_id, sku, title, brand, brand_source, category, subcategory, price, price_is_range, rating, features, ingredients, age_range, min_age_years, max_age_years, age_source, safety_warnings, product_url`. They map one to one onto `RagProduct` (`features` becomes `features_snippet`; `rating` and `ingredients` stay `None`, and `ingredients` is not in the contract).

## 5. Indexing
`uv run doit index`: about 22 s on CPU, 44 MB.
- **Text embedded:** `title. features. Recommended age: <age>`. No chunking: one vector per product.
- **Model:** `sentence-transformers/all-MiniLM-L6-v2`, local, 384 dimensions. Chosen over a hosted embedding API so no key is needed and the MCP server can embed queries on any laptop. Index and queries must use the same model (`config/retrieval.py`).
- **Store:** Chroma, persistent, cosine space, collection `products`. Chosen because it filters on metadata natively. FAISS would need a separate filter layer.
- **Metadata:** `sku, title, brand, category, subcategory, price, min/max age, age_known, safety_warnings` (joined text, Chroma cannot hold lists). Unknown values are omitted.

## 6. Retrieval (`rag_search()`)
`from rag.search import rag_search`; takes `RagSearchInput`, returns `RagSearchOutput` (plain, JSON-serializable). First call about 2 s (model load), then 20-50 ms.

| Filter | Behaviour |
|---|---|
| `category` | exact; a subcategory name such as "Puzzles" also works |
| `brand` | tolerant of speech: "fisher price" matches "Fisher-Price", "and" matches "&" |
| `min_price`, `max_price` | products with no price never match |
| `child_age_years` | drops products whose minimum age is above the child's; products with **no stated age are kept** |
| `exclude_features` | text match on features and warnings, applied after retrieval |
| `min_rating` | **not applied** (no data); reported in `filters_applied` as "not applied: catalog has no rating data" instead of silently dropping everything |

**Scoring:** `cosine(query, product) + 0.3 * title_overlap` (share of the query's content words found in the title or brand). Candidates are the vector top-50 plus a BM25 top-30 on title and brand. No match returns an empty list, never an exception. `score` is for ordering only and can slightly exceed 1.0. Every result keeps its `doc_id` for citations.

## 7. Retrieval evaluation
`uv run doit rag_smoke_test rag_eval`: 30 queries in [../../rag/eval/eval_queries.json](../../rag/eval/eval_queries.json): 16 known-item (one expected `doc_id` each), 8 constraint (every result must obey every filter, checked against the parquet), 6 edge cases (unknown brand, impossible budget, unsupported rating filter, product not in the catalog, ambiguous request, strict age filter). Report goes to `data/eval/EVAL_REPORT.md`.

| Metric | v0 vector only | v1 hybrid (shipped) |
|---|---|---|
| Recall@1 | 0.75 | 0.88 |
| Recall@5 / @10 | 0.94 / 0.94 | 1.00 / 1.00 |
| MRR | 0.83 | 0.93 |
| Constraint satisfaction | 1.00 | 1.00 |
| Checks passed | 29/30 | 30/30 |
| Latency p50 / p95 | ~20 / ~33 ms | ~25 / ~45 ms |

**Failure found (v0):** "300 piece jigsaw puzzle with a pet park scene for kids" did not return the Ravensburger Pet Park puzzle in the top 10, because other 300-piece puzzles outranked it (long marketing text dilutes the title in the embedding). The title/brand signal moved it to rank 3.

## 8. Decisions, limitations, and known issues
- **Weight 0.3:** swept 0 to 0.6. 0.4 and above give slightly better MRR (0.97) but blur the "not in catalog" signal: "PlayStation 5 console" then scores 0.46, close to real matches. 0.3 is the highest weight that keeps it below 0.45.
- **A similarity score alone cannot say "not found":** short real queries also top out near 0.5. The Answerer should check that a result actually names the requested product.
- **No ratings:** the agent cannot rank by stars or cite a rating from private data. Could come from `web.search`.
- **Warnings exist for 1.4% of products, age for 74%.** The Answerer must never call a toy safe because nothing was found.
- **Brand is best-effort** for ~75% of products (first title word) and can truncate unlisted multi-word brands.
- **Small evaluation:** the weight was tuned on the same 30 queries it is reported on, and one missed known-item query costs 6 points. Treat the numbers as indicative.
- Package size and price per unit (#40) are not built: PR #78 removed those fields.

## 9. Rebuild from scratch
```bash
uv run doit download_kaggle_dataset   # raw CSV
uv run doit preprocess                # products.parquet
uv run doit index                     # Chroma index
uv run doit rag_smoke_test rag_eval   # checks
```
Needs `chromadb`, `sentence-transformers`, `pandas` and `pyarrow` in the project dependencies.
