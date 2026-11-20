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
   uv run doit download
   ```

This runs [scripts/download_data.py](scripts/download_data.py), which saves the original files exactly as
Kaggle ships them (one CSV, ~10k products) under `data/raw/kaggle/`.

`data/` is gitignored. This step only downloads. Preprocessing into `products.parquet` is a separate step.
To download again from scratch, run `uv run doit clean download && uv run doit download`.
