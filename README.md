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

Task names are the function names in `dodo.py` without the `task_` prefix (`task_download_kaggle_dataset` → `download_kaggle_dataset`).
`uv run doit` with no arguments runs only the tasks listed in `DOIT_CONFIG["default_tasks"]`.

### Add a new task

1. Put the logic in a script under `scripts/` (or in your package) that can also run on its own.
2. Add a `task_<name>()` function to [dodo.py](dodo.py) that returns a dict. Use the download task as the model:

   ```python
   from config.paths import PRODUCTS_PARQUET, KAGGLE_CSV, ROOT

   def task_preprocess():
       """Clean the raw CSV into products.parquet."""   # the docstring is what `doit list` shows
       script = ROOT / "scripts" / "preprocess.py"
       return {
           "actions": [f'"{PYTHON}" "{script}"'],
           "file_dep": [script, KAGGLE_CSV],  # inputs: re-run when any of them changes
           "targets": [PRODUCTS_PARQUET],     # outputs: skipped while they exist and inputs are unchanged
           "clean": True,                     # `doit clean preprocess` deletes the targets
       }
   ```

3. Take every input and output path from [config/paths.py](config/paths.py). Don't write paths by hand.
4. Run the interpreter as `PYTHON` (the uv venv) so the task uses the locked dependencies.
5. Chain tasks with `file_dep`: a task that reads another task's target lists it in `file_dep`, and doit runs them in order.
6. Add the task to `DOIT_CONFIG["default_tasks"]` only if a fresh clone needs it to run by default. Check with `uv run doit list`.
7. Add any new secret to `.env.example` and the new path to the table in [Paths](#paths).

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

## Tools

The tools the project uses, with the owner who added each one. Prefer tools that uv manages (`uv add <package>`).
Each owner adds their own rows in the same PR that introduces the tool. Don't list a tool before it is decided.

| Tool | Purpose | Owner | Managed by |
|------|---------|-------|------------|
| [uv](https://docs.astral.sh/uv/) | Python 3.12 and dependency management (`pyproject.toml`, `uv.lock`) | Everyone | `brew install uv` |
| [pydoit](https://pydoit.org) | Build and run tasks in [dodo.py](dodo.py) | Juan (example), Devanshu (orchestration) | `uv add doit` |
| [kagglehub](https://github.com/Kaggle/kagglehub) | Download the Amazon Product Dataset 2020 | Juan | `uv add kagglehub` |
| [Serper](https://serper.dev) | Search API behind `web.search` (proposed, to confirm with test queries; see [decision](docs/decisions/web_search_api.md)) | Juan | API key in `.env` (`SERPER_API_KEY`) |

Still to add by their owners: MCP server library and transport (Juan), vector store and embeddings (Akshaj),
LangGraph and the LLM client (Devanshu), ASR, TTS and Streamlit (Alekhya), ProofAgent (Beste).
