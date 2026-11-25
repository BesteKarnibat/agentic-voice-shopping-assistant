# CLAUDE.md

Team final project (UChicago, Generative AI): a voice-to-voice shopping assistant.
Spoken request → Whisper ASR → LangGraph multi-agent workflow → RAG over an Amazon product
catalog + live web search, both through one MCP server → grounded answer with citations → TTS.
Evaluated end-to-end with the ProofAgent harness.

## Read first

- [docs_assignment/deliverables.md](../docs_assignment/deliverables.md): requirements checklist, schedule, infrastructure decisions, grading weights, open questions.
- [docs_assignment/task-planning.md](../docs_assignment/task-planning.md): who owns what, the critical path, handoffs, and branches.
- [docs_assignment/assignment.md](../docs_assignment/assignment.md): the original assignment. If it disagrees with anything else, it wins.
- [contracts/](../contracts/): the shared interfaces between team members. Read these before writing any node or tool.

**Official deadline: Wed Dec 2, 2026.** Repo ready Mon Nov 30, team test Tue Dec 1. Feature freeze is Sat Nov 28. Prefer the simple, working option over the
ambitious one, and keep optional scope (reranker, streaming) out unless asked.

## Current state

On `main`: the contracts, the docs skeletons, and `prompts/README.md`. PR #3 adds the uv project
(`pyproject.toml`, `uv.lock`), `dodo.py`, and the Kaggle download script. No graph, MCP server, index,
or UI yet. Don't assume a module exists until you have checked.

Work is tracked as GitHub issues (#4–#75), one milestone per schedule date, with "blocked by"
relationships between them. Technical decisions are sub-issues of #2. Check an issue's dependencies
before starting it.

## Ownership and git workflow

| Area | Owner | Branch |
|------|-------|--------|
| Data & RAG (download, cleaning, index, `rag_search()`) | Akshaj | `feature/rag` |
| MCP server (`rag.search`, `web.search`) | Juan | `feature/mcp` |
| LangGraph (graph, Router, Planner, Retriever, integration) | Devanshu | `feature/graph` |
| Voice & UI (Whisper, TTS, Streamlit) | Alekhya | `feature/ui` |
| Answerer/Critic, guardrails, ProofAgent eval | Beste | `feature/eval` |

- Never commit directly to `main`. Everything goes through a PR that Devanshu reviews.
- Work on the branch of the area you're changing. Don't edit another owner's area without saying so.
- Don't open PRs or issues unless the user asks.

## Tooling

- Python 3.12, managed with **uv**: `uv add <pkg>` to add a dependency, `uv run <cmd>` to run anything.
  Don't use `pip install` and don't hand-edit `uv.lock`. If `uv.lock` has a merge conflict, run `uv lock` to regenerate it.
- Goal: a fresh clone with `.env` filled in launches the app with one command. Run orchestration is Devanshu's call
  as integrator. **pydoit** (`dodo.py`, `uv run doit`) is the suggested option. If a `dodo.py` exists, add new build
  or run steps to it as tasks instead of writing ad-hoc scripts.
- Data comes from Kaggle through a download script that uses the user's own API key. Raw data, processed parquet,
  and indexes live under `data/` (gitignored).

## Contracts are shared: don't change them without asking

- `contracts/state.py`: `AgentState`, the single LangGraph state every node reads and writes. Owned by Devanshu.
- `contracts/tool_schemas.py`: Pydantic input/output models for `rag.search` and `web.search`, plus the `TOOLS`
  registry used for MCP discovery. Owned by Juan.
- `contracts/tool_schemas.json`: generated from `tool_schemas.py`. Never edit it by hand.

If a task needs a contract change, stop and tell the user. Other teammates code against these files.
After an agreed change to `tool_schemas.py`, regenerate the JSON from the repo root:

```bash
python -c "from contracts.tool_schemas import export_json_schemas; export_json_schemas('contracts/tool_schemas.json')"
```

(`python -m contracts.tool_schemas` writes to `./tool_schemas.json` in the current directory, not into `contracts/`.)

## Rules for LangGraph nodes (from `state.py`)

- Store plain dicts in state (`RagProduct(...).model_dump()`), never Pydantic objects. The state has to stay
  JSON-serializable for logs, the UI, and ProofAgent.
- A node returns only the keys it changed.
- Every node appends at least one `step_log` entry via `log_step(node, summary, **details)`.
- `step_log` and `errors` append across nodes (`operator.add`). Return a list with the new items, not the full list.
- The Answerer gets at most `MAX_CRITIC_REVISIONS` (2) rewrites from the Critic.

## Non-negotiables from the assignment

- **Model-agnostic:** choose the LLM provider and model through env vars or config. Never hard-code one provider.
- **Grounded and cited:** every factual product claim cites a private `doc_id` or a live `url`. No citation, no claim.
- **Planner:** prefer `rag.search` for product facts. Also use `web.search` only for "current / latest / in stock / current price" requests, or when catalog data is missing.
- **web.search:** rate limited, TTL cache (60–300 s), always keeps the source URL, logs requests and responses.
- **Spoken summary:** ≤ ~15 s (≈40 words), no citation markers. The full answer and table go on screen.
- **Safety:** respect age grades and repeat only the safety warnings a source states (choking hazards, magnets, button batteries), use domain restrictions on web results, never commit secrets.
- **Prompt disclosure:** every important prompt must live in `prompts/` (or be documented), mapped to its node.
  Don't bury prompts inline in code without also disclosing them there.

## Conventions

- Python, Pydantic v2. Code, comments, docs, and commit messages in English.
- `.env` (gitignored) holds **secrets only**: API keys and tokens. Every new secret also goes in `.env.example`
  with an empty value. Non-secret configuration (provider, model, dataset slug, paths, TTLs, allowed domains)
  does not go in `.env`.
- Don't commit datasets, vector indexes, or audio files. Commit the scripts that build them.
- Keep changes inside the area you were asked to work on. Each component has an owner (see deliverables.md).
