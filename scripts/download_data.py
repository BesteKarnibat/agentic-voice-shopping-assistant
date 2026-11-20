"""Download the Amazon Product Dataset 2020 from Kaggle and save it as parquet.

Credentials come from `.env` (never committed):
    KAGGLE_API_TOKEN=...   # kaggle.com -> Settings -> API -> Generate New Token

Output (all under data/, which is gitignored):
    data/raw/kaggle/...                    original files exactly as Kaggle ships them
    data/raw/amazon_products_2020.parquet  same rows, columns renamed to snake_case, all values as strings

This step does no cleaning. Type casting, filtering, and the `products.parquet` schema belong
to the preprocessing step (Data & RAG).

Usage:
    uv run doit download                       # preferred
    uv run python scripts/download_data.py     # same thing, without doit
    uv run python scripts/download_data.py --force
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import kagglehub
import polars as pl
from dotenv import load_dotenv

# Non-secret configuration. Override from the command line if needed.
REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_SLUG = "promptcloud/amazon-product-dataset-2020"
RAW_DIR = REPO_ROOT / "data" / "raw"
KAGGLE_DIR = RAW_DIR / "kaggle"
OUTPUT_PARQUET = RAW_DIR / "amazon_products_2020.parquet"

log = logging.getLogger("download_data")


def to_snake_case(name: str) -> str:
    """'Uniq Id' -> 'uniq_id', 'Upc Ean Code' -> 'upc_ean_code'."""
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


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


def csv_to_parquet(csv_path: Path, parquet_path: Path) -> pl.DataFrame:
    """Read every column as a string (no type guessing) and write it as parquet."""
    df = pl.read_csv(csv_path, infer_schema=False)
    df = df.rename({c: to_snake_case(c) for c in df.columns})
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(parquet_path)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--slug", default=DATASET_SLUG, help="Kaggle dataset handle (owner/name)")
    parser.add_argument("--output", type=Path, default=OUTPUT_PARQUET, help="Parquet file to write")
    parser.add_argument("--force", action="store_true", help="Download again even if the files exist")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv(REPO_ROOT / ".env")
    check_credentials()

    folder = download(args.slug, KAGGLE_DIR, args.force)
    csv_path = find_csv(folder)
    df = csv_to_parquet(csv_path, args.output)
    log.info("Wrote %s (%d rows x %d columns)", args.output.relative_to(REPO_ROOT), df.height, df.width)


if __name__ == "__main__":
    main()
