"""Build and run tasks for the project (pydoit).

    uv run doit            # run the default tasks
    uv run doit list       # show all tasks
    uv run doit download   # run a single task
    uv run doit clean download   # delete a task's outputs so it runs again

doit skips a task when its targets exist and its file_dep have not changed.
Add new steps (preprocess, index, app, ...) here as tasks instead of ad-hoc scripts.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = sys.executable  # the uv venv interpreter, since doit runs via `uv run doit`

DOIT_CONFIG = {
    "default_tasks": ["download"],
    "verbosity": 2,  # show the output of each task
}


def task_download():
    """Download the Amazon Product Dataset 2020 from Kaggle and save it as parquet."""
    script = ROOT / "scripts" / "download_data.py"
    return {
        "actions": [f'"{PYTHON}" "{script}"'],
        "file_dep": [script],
        "targets": [ROOT / "data" / "raw" / "amazon_products_2020.parquet"],
        "clean": True,
    }
