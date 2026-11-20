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

# Preprocessing output (Data & RAG)
PROCESSED_DIR = DATA_DIR / "processed"
PRODUCTS_PARQUET = PROCESSED_DIR / "products.parquet"
REVIEWS_PARQUET = PROCESSED_DIR / "reviews.parquet"  # optional

# Vector index (Data & RAG writes it, the MCP server reads it)
INDEX_DIR = DATA_DIR / "index"

# Runtime output
LOGS_DIR = DATA_DIR / "logs"  # tool-call logs (MCP), read for the ProofAgent failure analysis
AUDIO_DIR = DATA_DIR / "audio"  # recordings and TTS output (Voice & UI)
