"""Build and run tasks for the project (pydoit).

    uv run doit            # run the default tasks
    uv run doit list       # show all tasks
    uv run doit download   # run a single task
    uv run doit clean download   # delete a task's outputs so it runs again

doit skips a task when its targets exist and its file_dep have not changed.
Add new steps (preprocess, index, app, ...) here as tasks instead of ad-hoc scripts.
Take every input and output path from config/paths.py.
"""

import shutil
import sys

from config.paths import KAGGLE_DIR, ROOT

PYTHON = sys.executable  # the uv venv interpreter, since doit runs via `uv run doit`

DOIT_CONFIG = {
    "default_tasks": ["download"],
    "verbosity": 2,  # show the output of each task
}


def task_download():
    """Download the Amazon Product Dataset 2020 (raw CSV) from Kaggle."""
    script = ROOT / "scripts" / "download_data.py"
    return {
        "actions": [f'"{PYTHON}" "{script}"'],
        "file_dep": [script],
        # The CSV sits in nested subfolders, so check for it instead of listing a fixed target.
        "uptodate": [lambda: any(KAGGLE_DIR.rglob("*.csv"))],
        "clean": [lambda: shutil.rmtree(KAGGLE_DIR, ignore_errors=True)],
    }
