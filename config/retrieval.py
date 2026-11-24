"""Non-secret settings for the Data & RAG component (index build and `rag_search()`).

    from config.retrieval import EMBEDDING_MODEL, HYBRID_LAMBDA

The index and every query must use the same EMBEDDING_MODEL, QUERY_PREFIX/DOC_PREFIX and EMBED_TEXT. Changing any of
them means rebuilding the index (`uv run doit clean index index`). Secrets (API keys) never go here, see `.env.example`.

The values below were chosen by trials on random product samples and confirmed on a separate sample plus 28
hand-written queries; see docs/components/data-rag.md section 8 for the numbers and the alternatives that lost.
"""

# Embedding model: local sentence-transformers, no API key. The MCP server embeds queries, so it must run on every
# teammate's laptop (about 440 MB, downloaded once). bge models want a fixed instruction in front of queries.
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DOC_PREFIX = ""
# Which recipe in rag/texts.py builds the embedded text of a product.
EMBED_TEXT = "brand_cat_first3"

COLLECTION_NAME = "products"

# score before reranking = cosine(query, product) + HYBRID_LAMBDA * title_overlap. 0 means pure vector search.
# Small on purpose: this model finds descriptive queries well, and a larger weight hurt them in the trials.
HYBRID_LAMBDA = 0.05
LEXICAL_POOL = 30      # extra BM25 (title + brand) candidates added to the vector candidates
VECTOR_POOL = 50       # vector candidates fetched before rescoring (at least top_k * 10)
SNIPPET_CHARS = 220

# Cross-encoder that re-orders the best candidates. Set RERANKER_MODEL = None to turn it off (about 100 ms faster per
# search and one less model to download, at the cost of about 0.1 feature-query MRR). With it on, `score` is the
# reranker's relevance probability in 0..1 (higher is better), not a cosine.
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANK_TOP_N = 20
RERANK_MAX_LENGTH = 128  # tokens per passage: half the cost of 256 with the same quality in the trials
