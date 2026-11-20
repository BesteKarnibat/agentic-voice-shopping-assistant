# agentic-voice-shopping-assistant
Voice-to-voice AI shopping assistant that recommends products using multi-agent LangGraph, RAG over an Amazon catalog, and MCP web search, with grounded, cited answers. 

## Setup

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv` on macOS).

```bash
git clone <repo-url> && cd agentic-voice-shopping-assistant
uv sync                  # creates .venv with the exact versions from uv.lock
cp .env.example .env     # then fill in your own secrets
```

- Add a dependency with `uv add <package>` (never `pip install`). Commit both `pyproject.toml` and `uv.lock`.
- Run anything inside the project environment with `uv run <command>`.
- `uv sync` also installs this repo's own packages (`contracts`, `config`) in editable mode, so they import
  from any working directory (doit, `streamlit run`, the MCP server, `scripts/`).

## Paths

Every file and folder the project reads or writes is defined once in [config/paths.py](config/paths.py).
Import from there instead of writing paths by hand:

```python
from config.paths import PRODUCTS_PARQUET, INDEX_DIR
```

| Constant | Path | Written by |
|----------|------|------------|
| `KAGGLE_DIR` | `data/raw/kaggle/` | download (`uv run doit download_kaggle_dataset`) |
| `KAGGLE_CSV` | `data/raw/kaggle/home/sdf/marketing_sample_…_10k_data.csv` | download; read by preprocessing |
| `PRODUCTS_PARQUET` | `data/processed/products.parquet` | preprocessing (Data & RAG) |
| `REVIEWS_PARQUET` | `data/processed/reviews.parquet` | preprocessing, optional (Data & RAG) |
| `INDEX_DIR` | `data/index/` | index build (Data & RAG); read by the MCP server |
| `LOGS_DIR` | `data/logs/` | tool-call logs (MCP) |
| `AUDIO_DIR` | `data/audio/` | recordings and TTS output (Voice & UI) |

Everything under `data/` is gitignored. If you need a new path, add it to `config/paths.py` in the same PR that first uses it.

## Build tasks (pydoit)

Every build and run step is a task in [dodo.py](dodo.py). doit skips a task when its outputs already exist and its inputs haven't changed.

```bash
uv run doit list         # show available tasks
uv run doit              # run the default tasks
uv run doit <task>       # run one task
uv run doit clean <task> # delete a task's outputs so it runs again
```

## Download the data

The private catalog is the [Amazon Product Dataset 2020](https://www.kaggle.com/datasets/promptcloud/amazon-product-dataset-2020) on Kaggle. Each person downloads it with their own Kaggle account. No data is committed to git.

1. Create a Kaggle API token: [kaggle.com](https://www.kaggle.com) → your profile → **Settings** → **API** → **Generate New Token**.
2. Put it in `.env`:
   ```bash
   KAGGLE_API_TOKEN=your-token
   ```
3. Run the download task:
   ```bash
   uv run doit download_kaggle_dataset
   ```

This runs [scripts/download_data.py](scripts/download_data.py), which saves the original files exactly as
Kaggle ships them (one CSV, ~10k products) under `data/raw/kaggle/`.

`data/` is gitignored. This step only downloads. Preprocessing into `products.parquet` is a separate step.
To download again from scratch, run `uv run doit clean download_kaggle_dataset && uv run doit download_kaggle_dataset`.
