"""Build and run tasks for the project (pydoit).

    uv run doit            # run the default tasks
    uv run doit list       # show all tasks
    uv run doit download_kaggle_dataset         # run a single task
    uv run doit clean download_kaggle_dataset   # delete a task's outputs so it runs again
    uv run doit preprocess                      # raw CSV -> products.parquet (Toys & Games slice)
    uv run doit index                           # products.parquet -> Chroma vector index
    uv run doit rag_test rag_smoke_test rag_eval rag_sample_eval   # tests, checks, retrieval scores
    uv run doit eval_dry_run                    # ProofAgent wiring check (mock catalog, no upload)
    uv run doit eval                            # full ProofAgent evaluation, uploads the scorecard
    uv run doit eval_faults                     # incorrect tool results via fault injection

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

STREAMLIT_APP = ROOT / "app" / "streamlit_app.py"  # Alekhya's UI

# Default chain (Devanshu): download → preprocess → index → app (agent_demo until the UI is merged).
DOIT_CONFIG = {
    "default_tasks": ["download_kaggle_dataset", "preprocess", "index",
                      "app" if STREAMLIT_APP.exists() else "agent_demo"],
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


def task_app():
    """Launch the Streamlit voice UI: uv run doit app [-p 8501]. Stop with Ctrl+C."""
    return {
        "actions": [f'"{PYTHON}" -m streamlit run "{STREAMLIT_APP}" --server.port %(port)s'],
        "params": [{"name": "port", "short": "p", "default": "8501", "help": "port for the UI"}],
        "file_dep": [STREAMLIT_APP] if STREAMLIT_APP.exists() else [],
        "uptodate": [False],
        "verbosity": 2,
    }


# ProofAgent evaluation (Beste, #55). Settings in config/eval.py; see docs/components/evaluation.md.

def task_eval_validate():
    """Check the ProofAgent scenario files in eval/traps/ against the trap schema."""
    return {
        "actions": [f'"{PYTHON}" -m proofagent_harness.cli traps validate "{ROOT / "eval" / "traps"}" --strict'],
        "uptodate": [False],
    }


def task_eval_faults():
    """Incorrect-tool-result cases (#54): faulty MCP output, real agent, checks in code. Mock catalog."""
    return {
        "actions": [f'"{PYTHON}" -m eval.faults'],
        "uptodate": [False],
    }


def task_eval_dry_run():
    """ProofAgent wiring check: mock catalog, 2 scenarios, 3 turns, no upload (needs the LLM keys)."""
    return {
        "actions": [f'"{PYTHON}" -m eval.run --dry-run'],
        "uptodate": [False],
    }


def task_eval():
    """Full ProofAgent evaluation on the real index; uploads to the dashboard (EVAL_AGENT_VERSION=v1 ...)."""
    return {
        "actions": [f'"{PYTHON}" -m eval.run'],
        "file_dep": [CHROMA_DIR / "chroma.sqlite3"],
        "uptodate": [False],
    }
