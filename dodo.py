"""Build and run tasks for the project (pydoit).

    uv run doit            # run the default tasks
    uv run doit list       # show all tasks
    uv run doit download_kaggle_dataset         # run a single task
    uv run doit clean download_kaggle_dataset   # delete a task's outputs so it runs again
    uv run doit preprocess                      # raw CSV -> products.parquet (Toys & Games slice)
    uv run doit index                           # products.parquet -> Chroma vector index
    uv run doit rag_test rag_smoke_test rag_eval rag_sample_eval   # tests, checks, retrieval scores

doit skips a task when its targets exist and its file_dep have not changed.
Add new steps (preprocess, index, app, ...) here as tasks instead of ad-hoc scripts.
Take every input and output path from config/paths.py.
"""

import shutil
import sys

from config.paths import (
    CHROMA_DIR,
    KAGGLE_CSV,
    KAGGLE_DIR,
    PRODUCTS_PARQUET,
    PRODUCTS_SAMPLE_JSON,
    ROOT,
)

PYTHON = sys.executable  # the uv venv interpreter, since doit runs via `uv run doit`

# Default chain (Devanshu): download → preprocess → index → app. Ends with the agent demo until
# the app task lands.
DOIT_CONFIG = {
    "default_tasks": ["download_kaggle_dataset", "preprocess", "index", "agent_demo"],
    "verbosity": 2,  # show the output of each task
}


def task_download_kaggle_dataset():
    """Download the Amazon Product Dataset 2020 (raw CSV) from Kaggle."""
    script = ROOT / "scripts" / "download_data.py"
    return {
        "actions": [f'"{PYTHON}" "{script}"'],
        "file_dep": [script],  # input: re-run when the script changes
        "targets": [KAGGLE_CSV],  # output: skip while the CSV exists
        # Remove the whole download folder, not only the CSV.
        "clean": [lambda: shutil.rmtree(KAGGLE_DIR, ignore_errors=True)],
    }


def task_preprocess():
    """Clean the Toys & Games slice into products.parquet (plus a ~100-product sample)."""
    script = ROOT / "rag" / "preprocess.py"
    return {
        "actions": [f'"{PYTHON}" -m rag.preprocess'],
        "file_dep": [KAGGLE_CSV, script],  # depends on download_kaggle_dataset through its target
        "targets": [PRODUCTS_PARQUET, PRODUCTS_SAMPLE_JSON],
        "clean": True,
    }


def task_index():
    """Embed the products and build the Chroma vector index."""
    return {
        "actions": [f'"{PYTHON}" -m rag.build_index'],
        "file_dep": [PRODUCTS_PARQUET, ROOT / "rag" / "build_index.py", ROOT / "config" / "retrieval.py"],
        "targets": [CHROMA_DIR / "chroma.sqlite3"],
        "clean": [lambda: shutil.rmtree(CHROMA_DIR, ignore_errors=True)],
    }


def task_rag_test():
    """Run every rag test: parsers, data quality, index, search and filters, contract compatibility.
    Tests that need the index skip with a hint if `preprocess` and `index` have not run yet."""
    return {"actions": [f'"{PYTHON}" -m unittest discover -s rag -t . -p "test_*.py"']}


def task_rag_smoke_test():
    """Run rag_search() on a few queries and fail if a filter is broken."""
    return {"actions": [f'"{PYTHON}" -m rag.smoke_test'], "file_dep": [CHROMA_DIR / "chroma.sqlite3"]}


def task_rag_sample_eval():
    """Retrieval recall on 600 random products with generated queries (about 3 min). Output: data/eval/random_sample_eval.md."""
    return {"actions": [f'"{PYTHON}" -m rag.eval.random_sample_eval'], "file_dep": [CHROMA_DIR / "chroma.sqlite3"]}


def task_rag_eval():
    """Score retrieval (recall@k, MRR, filter checks). Output: data/eval/EVAL_REPORT.md."""
    return {"actions": [f'"{PYTHON}" -m rag.eval.run_eval'], "file_dep": [CHROMA_DIR / "chroma.sqlite3"]}


# ---------------------------------------------------------------------------
# LangGraph agent (Devanshu)
# ---------------------------------------------------------------------------


def task_test_graph():
    """Run the agent test suite offline (fake LLM + mock MCP server, no API key needed)."""
    return {
        "actions": [f'"{PYTHON}" -m pytest -q'],
        "uptodate": [False],  # always run
    }


def task_agent_demo():
    """Run run_agent() on three sample queries (LLM_PROVIDER=fake for offline)."""
    return {
        "actions": [f'"{PYTHON}" -m agent --demo'],
        "uptodate": [False],
    }


def task_agent_ask():
    """Ask the agent one question: uv run doit agent_ask -q "board game under $30"."""
    return {
        "actions": [f'"{PYTHON}" -m agent %(q)s'],
        "params": [{"name": "q", "short": "q", "default": "Recommend a card game for family night.",
                    "help": "user request text"}],
        "uptodate": [False],
    }
