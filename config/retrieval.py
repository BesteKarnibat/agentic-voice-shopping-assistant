"""Non-secret settings for the Data & RAG component (index build and `rag_search()`).

    from config.retrieval import EMBEDDING_MODEL, HYBRID_LAMBDA

The index and every query must use the same EMBEDDING_MODEL. Changing it means rebuilding the index
(`uv run doit clean index index`). Secrets (API keys) never go here, see `.env.example`.
"""

# Local sentence-transformers model: no API key, runs on every teammate's laptop (the MCP server embeds queries).
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

COLLECTION_NAME = "products"

# score = cosine(query, product) + HYBRID_LAMBDA * title_overlap. 0 means pure vector search.
# 0.3 was the highest weight that kept out-of-catalog queries scoring low (see docs/components/data-rag.md).
HYBRID_LAMBDA = 0.3
# Extra BM25 (title + brand) candidates added to the vector candidates before rescoring.
LEXICAL_POOL = 30
SNIPPET_CHARS = 220
