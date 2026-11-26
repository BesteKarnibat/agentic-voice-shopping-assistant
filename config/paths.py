"""Every file and folder the project reads or writes, defined once.

Import paths from here instead of building them by hand:

    from config.paths import PRODUCTS_PARQUET, INDEX_DIR

Paths are absolute and derived from the repo root, so they work from any working directory
(doit, Streamlit, the MCP server, tests). Everything under `data/` is gitignored and rebuilt
by `uv run doit`. Add a new path here, in the same PR that first uses it.
"""

from pathlib import Path

# Repo root. Works because uv installs this project in editable mode (`uv sync`).
ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

DATA_DIR = ROOT / "data"

# Raw download (scripts/download_data.py)
RAW_DIR = DATA_DIR / "raw"
KAGGLE_DIR = RAW_DIR / "kaggle"  # original files exactly as Kaggle ships them
KAGGLE_CSV = KAGGLE_DIR / "home" / "sdf" / "marketing_sample_for_amazon_com-ecommerce__20200101_20200131__10k_data.csv"

# Preprocessing output (Data & RAG)
PROCESSED_DIR = DATA_DIR / "processed"
PRODUCTS_PARQUET = PROCESSED_DIR / "products.parquet"
PRODUCTS_SAMPLE_JSON = PROCESSED_DIR / "products_sample.json"  # ~100 products for teammates and tests
REVIEWS_PARQUET = PROCESSED_DIR / "reviews.parquet"  # optional

# Vector index (Data & RAG writes it, the MCP server reads it)
INDEX_DIR = DATA_DIR / "index"
CHROMA_DIR = INDEX_DIR / "chroma"  # Chroma persistent store (collection "products")
RAG_EVAL_DIR = DATA_DIR / "eval"  # retrieval evaluation output (rag/eval)

# Runtime output
LOGS_DIR = DATA_DIR / "logs"  # tool-call logs (MCP), read for the ProofAgent failure analysis
TOOL_CALLS_LOG = LOGS_DIR / "tool_calls.jsonl"  # one JSON line per MCP tool call (request + response)
AUDIO_DIR = DATA_DIR / "audio"  # recordings and TTS output (Voice & UI)

# ProofAgent evaluation (Beste, eval/): generated harness inputs and run output
PROOFAGENT_DIR = DATA_DIR / "proofagent"
EVAL_CONTEXT_DIR = PROOFAGENT_DIR / "context"  # system_prompt.md, tools.json, agent.yaml (built from prompts/, contracts/)
EVAL_KNOWLEDGE_DIR = PROOFAGENT_DIR / "knowledge"  # catalog the agent is grounded on, for hallucination scoring
EVAL_REPORTS_DIR = PROOFAGENT_DIR / "reports"  # report JSON / Markdown per run
EVAL_TURNS_DIR = PROOFAGENT_DIR / "turns"  # one JSONL per run: every turn's message and final AgentState
