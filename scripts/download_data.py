"""Download the Amazon Product Dataset 2020 from Kaggle.

Credentials come from `.env` (never committed):
    KAGGLE_API_TOKEN=...   # kaggle.com -> Settings -> API -> Generate New Token

Output (under data/, which is gitignored):
    data/raw/kaggle/...    original files exactly as Kaggle ships them (one CSV)

This step only downloads. Reading the CSV, type casting, filtering, and writing `products.parquet`
belong to the preprocessing step (Data & RAG).

Usage:
    uv run doit download                       # preferred
    uv run python scripts/download_data.py     # same thing, without doit
    uv run python scripts/download_data.py --force
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import kagglehub
from dotenv import load_dotenv

from config.paths import ENV_FILE, KAGGLE_DIR, ROOT

# Non-secret configuration. Override from the command line if needed.
DATASET_SLUG = "promptcloud/amazon-product-dataset-2020"

log = logging.getLogger("download_data")


def check_credentials() -> None:
    """Fail early with a clear message if the Kaggle token is not configured."""
    if not os.getenv("KAGGLE_API_TOKEN"):
        sys.exit(
            "KAGGLE_API_TOKEN is not set. Copy .env.example to .env and add your token "
            "(kaggle.com -> Settings -> API -> Generate New Token)."
        )


def download(slug: str, dest: Path, force: bool) -> Path:
    """Download and unzip the dataset into `dest`. Skips the download if it is already there."""
    dest.mkdir(parents=True, exist_ok=True)
    log.info("Downloading %s into %s", slug, dest)
    path = kagglehub.dataset_download(slug, output_dir=str(dest), force_download=force)
    return Path(path)


def find_csv(folder: Path) -> Path:
    """Return the single CSV in the download. Kaggle nests it in subfolders, so search recursively."""
    csvs = sorted(folder.rglob("*.csv"))
    if len(csvs) != 1:
        raise RuntimeError(f"Expected exactly one CSV under {folder}, found {len(csvs)}: {csvs}")
    return csvs[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--slug", default=DATASET_SLUG, help="Kaggle dataset handle (owner/name)")
    parser.add_argument("--force", action="store_true", help="Download again even if the files exist")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv(ENV_FILE)
    check_credentials()

    folder = download(args.slug, KAGGLE_DIR, args.force)
    csv_path = find_csv(folder)
    log.info("Downloaded %s", csv_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
