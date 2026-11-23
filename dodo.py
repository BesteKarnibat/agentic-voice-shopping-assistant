"""Build and run tasks for the project (pydoit).

    uv run doit            # run the default tasks
    uv run doit list       # show all tasks
    uv run doit download_kaggle_dataset         # run a single task
    uv run doit clean download_kaggle_dataset   # delete a task's outputs so it runs again

doit skips a task when its targets exist and its file_dep have not changed.
Add new steps (preprocess, index, app, ...) here as tasks instead of ad-hoc scripts.
Take every input and output path from config/paths.py.
"""

import shutil
import sys

from config.paths import KAGGLE_CSV, KAGGLE_DIR, ROOT

PYTHON = sys.executable  # the uv venv interpreter, since doit runs via `uv run doit`

# Default chain (Devanshu): download → preprocess → index → app. Ends with the agent demo until
# the index and app tasks land.
DOIT_CONFIG = {
    "default_tasks": ["download_kaggle_dataset", "agent_demo"],
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
