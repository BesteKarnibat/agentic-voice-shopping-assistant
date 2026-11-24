# Data preprocessing and indexing

**Owner:** Akshaj · **Branch:** `feature/rag` · **Status:** draft
**Code:** [../../rag/](../../rag/) (`preprocess.py`, `build_index.py`, `search.py`, `texts.py`), settings in [../../config/retrieval.py](../../config/retrieval.py) · **Contract:** `RagSearchInput` / `RagProduct` in [../../contracts/tool_schemas.py](../../contracts/tool_schemas.py)

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
`uv run doit index`: about 65 s on a laptop, 97 MB on disk. One vector per product (no chunking).
- **Model:** `BAAI/bge-base-en-v1.5`, local, 768 dimensions, with its standard query instruction prefix. No API key; the MCP server embeds queries on any laptop. First run downloads about 420 MB (plus 88 MB for the reranker). Index and queries must use the same model and text recipe: all set in [../../config/retrieval.py](../../config/retrieval.py), and `rag_search()` refuses to run against an index built with another model.
- **Text embedded:** `title. Brand: <brand>. Category: <subcategory>. <first 3 feature bullets>. Recommended age: <age>` (recipe in [../../rag/texts.py](../../rag/texts.py)).
- **Store:** Chroma, persistent, cosine space, collection `products`. Chosen because it filters on metadata natively; FAISS would need a separate filter layer.
- **Metadata:** `sku, title, brand, category, subcategory, price, min/max age, age_known, safety_warnings, listing_text, snippet`. `listing_text` is what the listing itself says (no labels we added), used for exclusions and for the reranker. Chroma cannot hold lists or `None`, so warnings are joined text and unknowns are omitted.

## 6. Retrieval (`rag_search()`)
`from rag.search import rag_search`; takes `RagSearchInput`, returns `RagSearchOutput` (plain, JSON-serializable, unchanged contract). First call about 4 s (loads two models), then about 55 ms median and 120 ms p95 on an Apple-silicon laptop; the reranker step alone is about 70 ms on CPU only.

1. **Candidates:** vector top-50 (with the filters below) plus 30 BM25 matches on title and brand.
2. **Score:** `cosine + 0.05 * title_overlap` (share of the query's content words found in the title or brand).
3. **Exclusions:** products whose listing text or warnings mention an `exclude_features` phrase are dropped (matching ignores plural and singular, so "batteries" also catches "battery").
4. **Rerank:** a cross-encoder (`ms-marco-MiniLM-L-6-v2`) re-orders the best 20 and the top `top_k` are returned. `score` is then the reranker's relevance probability (0 to 1). Set `RERANKER_MODEL = None` to switch it off.

| Filter | Behaviour |
|---|---|
| `category` | free text from the Router is mapped to a catalog subcategory ("board games", "lego", "costumes"); if nothing matches, the filter is **not applied** and `filters_applied` says so (the search is never emptied by wording) |
| `brand` | tolerant of speech and spelling ("fisher price", "Melissa and Doug", "Fisher Price Little People"); an unknown brand returns an empty list with the reason |
| `min_price`, `max_price` | products with no price never match |
| `child_age_years` | drops products whose minimum age is above the child's; products with **no stated age are kept** |
| `exclude_features` | see step 3 |
| `min_rating` | **not applied** (no data); reported as "not applied: catalog has no rating data" |

No match returns an empty list, never an exception; a blank query or `min_price` above `max_price` also returns empty with the reason. Every result keeps its `doc_id`, and its `features_snippet` is a prefix of the listing text.

**Not-found signal:** the best `score` separates real requests from ones the catalog cannot serve. On 15 out-of-catalog queries (PS5, laptop charger, dog food, ...) the top score was at most 0.18 (median 0.001); on 38 real hand-written and short queries it was at least 0.99. **A best score below 0.2 means nothing relevant exists**; the Answerer should say so instead of recommending something. Only valid with the reranker on.

## 7. Retrieval evaluation
Commands: `uv run doit rag_test rag_smoke_test rag_eval rag_sample_eval`.
- **Tests (94):** parsers, data quality, index contents, search behaviour (including 300 random filter combinations checked against the parquet), the not-found signal, and compatibility with the shared contracts and `AgentState`.
- **Query sets:** [eval_queries.json](../../rag/eval/eval_queries.json) (34: 16 known-item, 8 constraint, 10 edge cases), [heldout_queries.json](../../rag/eval/heldout_queries.json) (12 known-item), and a 600-product random sample with generated queries ([random_sample_eval.py](../../rag/eval/random_sample_eval.py), seed 42). Hits are exact `doc_id` matches, so near-duplicate listings count as misses.

| Measure | Before (MiniLM, hybrid 0.3, no reranker) | **Final** |
|---|---|---|
| 34-query set: recall@1 / MRR | 0.88 / 0.93 | **0.88 / 0.94**; 34/34 checks, filters never violated |
| 12 held-out queries: recall@1 | 1.00 | **1.00** |
| 600 products, features only: recall@1 / MRR | 0.47 / 0.54 | **0.69 / 0.73** |
| 600 products, features only: recall@10 | 0.68 | **0.79** |
| 600 products, brand + subcategory: recall@10 | 0.52 | **0.78** |
| 600 products, title-based queries: recall@1 | 0.96 / 0.98 | 0.97 / 0.98 |
| Not-in-catalog detection | weak (cosine) | **0.2 cut-off: 15/15 flagged, 0 of 38 real queries flagged** |

What each component adds on the 600 products (feature-only recall@1): vector search alone 0.56, plus title match 0.55, plus reranker **0.69**. The title-match bonus now adds almost nothing for descriptive queries and only helps exact names (title without brand: 0.957 → 0.970); it is kept because it is cheap.

## 8. Decisions, limitations, and known issues
**How the configuration was chosen.** Trials ran on a *tune* sample (500 random products, queries generated from their fields); the winners were confirmed on a *separate* 600-product sample and 28 hand-written paraphrase queries that were never used to choose. The rules were fixed before the confirm sample and the hand-written queries were looked at (the model rule after seeing the first model comparison on tune): adopt a change only if it gains at least 0.02 on tune and 0.01 on the confirm sample, hand-written MRR does not drop by more than 0.01, and search stays under 250 ms. Selection metric: mean of feature-only MRR and brand+subcategory precision@5.

| Tried | Result | Decision |
|---|---|---|
| 7 embedding models | bge-base 0.515, bge-small 0.500, MiniLM 0.489, multi-qa 0.478, mpnet 0.467, gte-small 0.466, e5-small 0.463 | **bge-base** |
| Embedded text | brand and category in the text: brand queries +0.10 precision but feature MRR -0.03; first 3 bullets beat all bullets; title only is clearly worse | **brand + category + first 3 bullets** |
| Title-match weight | 0.3 suited MiniLM; for bge-base feature MRR falls steadily as the weight rises (0.66 at 0, 0.60 at 0.3) | **0.05** |
| Reciprocal-rank fusion instead of a weighted sum | worse at every weight | additive |
| Cross-encoder reranker | feature MRR 0.65 → 0.74 on tune; 20 candidates at 128 tokens cost 70 ms on CPU, 256 tokens cost more than double with the same quality | **adopted** |
| What the reranker reads | without brand and category it hurt brand queries (precision 0.56 → 0.48); with them 0.61 | brand + category + all features |
| One vector per feature bullet | 5.5x the vectors and a rewrite of filters; ties on the fair test | not adopted |

**Limitations**
- **No ratings** in the dataset: the agent cannot rank by stars. Could come from `web.search`.
- **Safety data is thin:** warnings exist for 1.4% of products and age for 74%. The Answerer must never call a toy safe because nothing was found.
- **Brand is best-effort** for about 75% of products (first title word) and can truncate unlisted multi-word brands.
- **Generated queries share words with the listing.** The 600-product gains for feature queries are probably optimistic, because a reranker reads those shared words directly. The fair evidence is the 28 hand-written queries (recall@1 0.93, MRR 0.97, essentially unchanged from before) and the not-found signal, which does not depend on query wording. One missed hand-written query costs 3.6 points.
- **Numbers move slightly between index rebuilds** (up to 0.004 here): Chroma's approximate nearest-neighbour index is not bit-identical from build to build. The figures above are rounded to two decimals and hold.
- **Cost of the reranker:** one more model (88 MB) and about 70 ms per search on CPU; `RERANKER_MODEL = None` removes both and the not-found signal with it.
- **Prices are kept as scraped:** 4 products under $1 (one at $0.01, likely a source glitch) and 30 over $500 (mostly swing sets; one $5,332 lab instrument filed under Toys & Games).
- Package size and price per unit (#40) are not built: PR #78 removed those fields.

## 9. Rebuild from scratch
```bash
uv run doit download_kaggle_dataset   # raw CSV (needs KAGGLE_API_TOKEN)
uv run doit preprocess                # products.parquet
uv run doit index                     # Chroma index
uv run doit rag_test rag_smoke_test rag_eval rag_sample_eval   # tests, checks, retrieval scores
```
Changing the model, prefix or text recipe in `config/retrieval.py` needs `uv run doit clean index index`.
