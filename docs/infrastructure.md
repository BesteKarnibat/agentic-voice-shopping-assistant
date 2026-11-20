# Infrastructure and open questions

Project scope, tooling decisions, and the questions the team still has to close.
This document will eventually move into the root README. The deliverables and owners are in [deliverables.md](../docs_assignment/deliverables.md). The schedule is in [task-planning.md](../docs_assignment/task-planning.md#schedule).

Optional scope (reranker, streaming ASR/TTS) is out unless there is time left after Sat Nov 28.

## Infrastructure

Decided:

- **Python 3.12**, managed with **uv**. There is one `pyproject.toml` and one `uv.lock` at the repo root.
- **Data:** a script downloads the dataset from Kaggle with the user's own API key. No data is committed.
- **Goal:** a fresh clone plus a filled-in `.env` is enough to launch the app and talk to the agent with a single command.

Suggested, not mandatory. Devanshu decides as integrator:

- **Orchestration with [pydoit](https://pydoit.org).** It is simple to use, chains the steps (download → preprocess → index → app), and skips the ones that are already up to date:

```bash
git clone <repo> && cd agentic-voice-shopping-assistant
cp .env.example .env        # add API keys
uv run doit                 # download → preprocess → index → launch app
```

## Open questions

Decide as a team and record the answer here.

**Resolved**

- [x] UI: Streamlit.
- [x] Tooling: uv + Python 3.12, Kaggle download script. pydoit is suggested for orchestration and left to Devanshu.
- [x] Official deadline: Wed Dec 2, 2026. Internal target: repo ready Mon Nov 30, team test Tue Dec 1.
- [x] Deliverables: Repo, and Demo + presentation (one ≤7-minute session).
- [x] Demo: Alekhya. Slides: Juan. Architecture diagram: Devanshu.
- [x] `prompts/`: Devanshu + Beste. Orchestration: Devanshu.
- [x] Checkpoint items skipped: one-page proposal, problem definition, related work.

**Technical decisions (close on Fri Nov 20)**

- [ ] LLM provider/model for development and for the demo, and who pays for the API keys.
- [ ] Embedding model (local or API).
- [ ] ASR (local Whisper or API) and TTS provider.
- [ ] Web-search API: Brave or Serper (Juan).
- [ ] MCP transport: stdio or HTTP/SSE (Juan, with Devanshu).
- [ ] Vector store: FAISS or Chroma (Akshaj).
- [ ] Data slice of the Amazon dataset: Akshaj picks the category while analyzing the data, then updates `contracts/tool_schemas.py` and `.json` (see section 1.1 of [deliverables.md](../docs_assignment/deliverables.md)).

**Interfaces not yet in `contracts/`**

- [ ] `rag_search()` signature (Akshaj ↔ Juan). Proposal: `rag_search(RagSearchInput) -> RagSearchOutput`.
- [ ] `run_agent()` signature (Devanshu ↔ Alekhya, Beste).
- [ ] How ProofAgent calls the agent: audio or transcript (Beste ↔ Devanshu).

**Organization**

- [ ] Owner for the top-level README.
- [ ] Who creates the shared `pyproject.toml` first, so the other branches don't each start their own.
- [ ] Team availability between Wed Nov 25 and Sun Nov 29.
- [ ] Communication channel and a short daily check-in.
- [ ] Were Checkpoints 1 and 2 (Weeks 6 and 8) already submitted? If not, what are their dates?
- [ ] What exactly is submitted on Mon Nov 30, and at what time (repo, slides, live demo)?
