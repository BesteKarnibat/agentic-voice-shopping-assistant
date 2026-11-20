# Deliverables

What we have to hand in, who owns each piece, and how we know it is done.
Actionable version of [assignment.md](assignment.md). If the two disagree, `assignment.md` wins.
Task order, handoffs, and branches are in [task-planning.md](task-planning.md).

**Deadline: Monday, November 30, 2026.** Feature freeze: Saturday, November 28.

The project is finished when these two deliverables are done:

1. **[Repo](#1-repo)**: a working voice-to-voice agent, its evaluation, its documentation, and the prompts, all in one repository.
2. **[Demo and presentation](#2-demo-and-presentation)**: one session of **7 minutes or less** (the assignment gives a single limit for both) that shows the agent working and explains how it was built and evaluated.

Checkpoint items are assigned to a person and appears in that person's checklist below, tagged **[CP1]** or **[CP2]**. See [Checkpoints](#3-checkpoints) for the full tables.

---

## Grading → owner

100 points. Every graded area has a named owner. The owner makes sure the points are earned, but doesn't have to do all the work alone.

| Graded area | Pts | Owner(s) | What earns the points |
|-------------|----:|----------|-----------------------|
| Functionality | 25 | Devanshu (integration, routing), Alekhya (voice in/out), Beste (citations) | Voice flow works end to end, multi-agent routing, app runs, answers are cited |
| Agentic RAG Quality | 20 | Akshaj | Retrieval accuracy, hybrid search, grounding, good recommendations |
| MCP Server | 15 | Juan | Two tools, discovery, schemas, caching, logging |
| Planning & Tool Use | 10 | Devanshu | Planner picks the right tools; private vs live reconciliation |
| ProofAgent Evaluation | 10 | Beste | Scenarios, adversarial cases, scorecard, ≥2 failure analyses |
| UI/UX | 8 | Alekhya | Transcript, step log, comparison table, citations, audio playback |
| Presentation | 7 | Juan (slides), Alekhya (demo) | ≤7-min session covering architecture, results, evaluation, limitations |
| Prompt Disclosure | 5 | Devanshu + Beste | `prompts/` complete and mapped to nodes |


---

## 1. Repo

A clean repository on `main` that anyone can clone and run. **A fresh clone plus a filled-in** `.env` **must launch a working app with one command** (test this on a clean machine before Mon Nov 30). The repo contains:

- Working voice-to-voice agent: Voice → ASR → LangGraph → RAG/MCP → Answer → TTS.
- MCP server
- Streamlit UI
- ProofAgent evaluation
- Build and run scripts (index build, MCP server, app) -> Orchestrated via **doit**
- Documentation: a README plus one section per component, written by that component's owner.
- A `prompts/` folder with every important prompt, each mapped to its LangGraph node or tool.
- `.env.example` with every secret (empty values).

Everything merges into `main` through a PR that Devanshu reviews.

### 1.1 Data & RAG: Akshaj (`feature/rag`)

Turns a curated slice of the Amazon Product Dataset 2020 into a searchable private catalog.
Contract: `RagSearchInput` / `RagProduct` in `contracts/tool_schemas.py`. Grading: **Agentic RAG Quality (20)**.

- [ ] **[CP1]** Selected data slice: while analyzing the data, Akshaj picks the category to use. Confirm it has rating, ingredients, and reviews.
- [ ] **Reminder: update the contracts once the category is chosen.** The `category` filter example in `contracts/tool_schemas.py` (`RagSearchInput.category`, line 26) still holds a placeholder category. Replace it with the chosen one, then regenerate the JSON from the repo root. `tool_schemas.py` is Juan's contract, so tell Juan before changing it.
  ```bash
  python -c "from contracts.tool_schemas import export_json_schemas; export_json_schemas('contracts/tool_schemas.json')"
  ```
  `contracts/tool_schemas.json` is generated. Never edit it by hand.
- [ ] **[CP2]** RAG evaluation plan: how retrieval quality will be measured (queries, expected products, metrics).
- [ ] Kaggle download script that uses the user's own API key (no data committed)
- [ ] Cleaning and the curated slice
- [ ] `products.parquet` with `id, title, brand, category, price, rating, features, ingredients`
- [ ] `reviews.parquet` (optional) with `product_id, stars, summary/snippets`
- [ ] Unit normalization where needed (e.g. price per ounce)
- [ ] Embeddings over title + features (+ description) + selected review snippets
- [ ] Metadata stored: brand, price, rating, ingredients, category
- [ ] Vector store: Chroma
- [ ] **Hybrid retrieval:** vector similarity + metadata filters
- [ ] Stable `doc_id` returned for citations
- [ ] `rag_search()` v0 handed to Juan by Mon Nov 23, with the ~100-product sample file by Sun Nov 22
- [ ] Optional: reranker
- [ ] Docs: data preprocessing and indexing section of the README
- [ ] Index build script

### 1.2 MCP server: Juan (`feature/mcp`)

One MCP server that exposes private retrieval and live web search through a single tool interface.
Contract: `contracts/tool_schemas.py` (Juan owns it). Grading: **MCP Server (15)**.

- [ ] **[CP2]** MCP/tool calls: how the agent calls `rag.search` and `web.search`, with example requests and responses.
- [ ] **[CP2]** MCP README and schemas: tool names, JSON schemas, discovery, transport.
- [ ] **One** MCP server exposing **two** tools: `rag.search` and `web.search`
- [ ] Tool discovery, tool names, and JSON schemas
- [ ] Transport: stdio or streamable HTTP/SSE
- [ ] `rag.search` returns `{sku, title, price, rating, brand?, ingredients?, doc_id}`
- [ ] `web.search` wraps a legitimate API (Brave or Serper) and normalizes to `{title, url, snippet, price?, availability?}`
- [ ] `web.search` rate limiting
- [ ] `web.search` caching, TTL 60–300 s
- [ ] Source URL kept on every live result
- [ ] Logging of tool requests, responses, timestamps, and sources
- [ ] Respects API terms; domain restrictions on web results
- [ ] At least **one live MCP web comparison** shown working
- [ ] **[CP1]** Data ingestion: instead of a notebook, an ingestion script plus a `dodo.py`, documented in the README as the worked example of how we use doit (see [Checkpoint 1](#checkpoint-1--week-6))
- [ ] **[CP1]** Proposed tools: keep the README "Tools" section up to date (see [Checkpoint 1](#checkpoint-1--week-6))
- [ ] Docs: MCP server and tool schemas section of the README (the MCP README)

### 1.3 LangGraph: Devanshu (`feature/graph`)

The multi-agent workflow and the integration of every other component. Also owns `main` and PR reviews.
Contract: `contracts/state.py` (Devanshu owns it). Grading: **Functionality (25, shared)** and **Planning & Tool Use (10)**.

- [ ] **[CP2]** Architecture diagram of the whole system.
- [ ] **[CP2]** LangGraph flow: nodes, edges, state, and the Critic revision loop.
- [ ] Workflow built in **LangGraph**: Router → Planner → Retriever → Answerer/Critic
- [ ] **Router:** classifies intent, extracts constraints (budget, material, brand, category, preferences), flags basic safety concerns
- [ ] **Planner:** decides RAG, web, or both; defines retrieval fields and comparison criteria
- [ ] Planner prefers `rag.search` for product facts; uses `web.search` only for "current / latest / in stock / current price" or when catalog data is missing
- [ ] **Retriever:** vector search + metadata filters; calls the MCP tools when needed
- [ ] Reconciles private vs live results (SKU, brand, title similarity) and handles conflicts
- [ ] Plans, tool calls, results, and citations are logged (`step_log`)
- [ ] Graph skeleton with stub nodes by Sun Nov 22; `run_agent(transcript) → state` by Tue Nov 24
- [ ] Model-agnostic LLM configuration: provider and model swappable by config, tool calling enabled
- [ ] Run orchestration: one command from fresh clone to running app (`dodo.py` / `uv run doit`, extending Juan's example)
- [ ] End-to-end integration, led on Fri Nov 27
- [ ] `prompts/` for Router, Planner, Retriever, each mapped to its node
- [ ] Docs: LangGraph architecture; setup instructions, `.env.example`, and run/build scripts

### 1.4 Voice & UI: Alekhya (`feature/ui`)

The front and back of the experience: speech in, speech out, and the screen that makes the workflow visible.
Contract: `AgentState` input/output fields. Grading: **UI/UX (8)** and part of **Functionality (25)**.

- [ ] **[CP2]** UI wireframe: layout of the Streamlit app.
- [ ] **ASR:** Whisper (or comparable), fragment-based recording (WAV/MP3), handles common accents, timestamps in `asr_segments`
- [ ] **TTS:** a provider (OpenAI, ElevenLabs, Azure, Polly, Coqui, ...); spoken summary **≤ ~15 s** (≈40 words), no citation markers, consistent with the on-screen results
- [ ] **Streamlit app:**
  - [ ] Mic recording / upload
  - [ ] Transcript
  - [ ] Agent execution / step log
  - [ ] Product comparison table (top 3: Product | Price | Rating | Ingredients | Source | Citation)
  - [ ] Citations with private `doc_id`s
  - [ ] Live-source links
  - [ ] TTS playback
- [ ] UI calls `run_agent` (by Wed Nov 25); full voice loop by Fri Nov 27
- [ ] Docs: UI and voice usage section of the README

### 1.5 Answerer/Critic, safety & evaluation: Beste (`feature/eval`)

Answer quality, guardrails, and the ProofAgent evaluation of the finished system.
Contract: `CriticVerdict`, `Citation`, `ComparisonRow`. Grading: **ProofAgent Evaluation (10)**, part of **Functionality (25)** (citations), and **Prompt Disclosure (5, shared)**.

- [ ] **[CP2]** Initial ProofAgent evaluation plan and scenarios.
- [ ] **Answerer:** concise recommendation; every factual product claim cites a private `doc_id` or a live `url`
- [ ] **Critic:** checks grounding against evidence, safety, and response quality; at most `MAX_CRITIC_REVISIONS` (2) rewrites
- [ ] Guardrails on input and output; grounded answers only, no unsupported claims
- [ ] Safe handling of chemical/product advice (e.g. mixing cleaners)
- [ ] Real Answerer and Critic plugged into the graph by Wed Nov 25
- [ ] **ProofAgent evaluation** of the end-to-end agent, not just the LLM:
  - [ ] Evaluation configuration
  - [ ] Scenarios: product discovery, constraints/preferences, RAG retrieval, MCP/tool calls, product comparison, grounded recommendations, safety/guardrails, voice interactions
  - [ ] Dimensions scored: task success, hallucination resistance / grounding, tool-use correctness, safety & guardrail compliance, response quality
  - [ ] Adversarial / edge cases: ambiguous request, private vs live conflict, out-of-budget products, missing/unavailable products, incorrect tool results, unsupported product claims, unsafe requests
  - [ ] First run on Sat Nov 28, second run on Sun Nov 29, failures reported to owners
  - [ ] Final scorecard / results committed
  - [ ] Failure analysis by stage (ASR → Router → Planner → RAG/MCP → Answerer → TTS)
  - [ ] **At least two** failure cases analyzed, with proposed improvements
- [ ] `prompts/` for Answerer, Critic, and guardrails, each mapped to its node
- [ ] Docs: safety considerations; evaluation methodology

### 1.6 Whole-repo checks

Shared by everyone. Devanshu checks them before submission.

- [ ] **Prompt disclosure:** `prompts/` is complete (system, Router, Planner, tool-call, Answerer/Critic, guardrail prompts, few-shot examples if used), and each prompt is mapped to its node, agent, or tool. Owners: Devanshu and Beste.
- [ ] **Model-agnostic:** LLM provider and model are swappable by config; nothing is hard-coded to one provider
- [ ] **Grounding:** context limited to retrieved evidence; citations required for factual recommendations; important prompts and system messages logged
- [ ] **Safety:** web domain allow-list, input/output guardrails, no secrets committed
- [ ] **No data in git:** datasets, indexes, and audio are gitignored; the scripts that build them are committed
- [ ] **README:** top-level README that ties each owner's section together. Owner: Devanshu
- [ ] **Clean-machine test:** fresh clone + `.env` + one command launches a working app

---

## 2. Demo and presentation

One session of **7 minutes or less**. The assignment does not separate the demo from the presentation, so they share the time limit.

"clear and engaging ≤7-minute demonstration covering architecture, results, evaluation, and limitations"

### 2.1 Demo: Alekhya

Alekhya runs the live demo on the Streamlit UI.

- [ ] Demo script: the exact spoken requests, in order, including one that needs a **live MCP web comparison**
- [ ] Demo runs end to end by voice: mic → transcript → step log → comparison table → citations → spoken answer
- [ ] Laptop and microphone chosen and tested in the demo room
- [ ] Recorded backup video, in case an API fails live
- [ ] Rehearsal with the whole team on Tuesday Dic 1

### 2.2 Presentation (slides): Juan

Juan builds and organizes the slide deck. Each owner supplies the content for their part.

Parts the presentation must have:

- [ ] **Problem and goal:** what the assistant does, with the example voice interaction
- [ ] **Architecture:** the diagram (Devanshu) and the pipeline Voice → ASR → LangGraph → RAG/MCP → Answer → TTS
  - [ ] **Agentic RAG:** data slice, hybrid retrieval, citations (Akshaj)
  - [ ] **MCP server:** the two tools, discovery, caching, logging (Juan)
- [ ] **Live demo:** the slot where Alekhya runs the demo
- [ ] **ProofAgent evaluation:** the scorecard and the scenarios covered (Beste)
- [ ] **Limitations and next steps**
- [ ] Total length rehearsed to **7 minutes or less** (demo included)

---

## 3. Checkpoints

The assignment has two course checkpoints. Each item is assigned, and each assigned item is also a tagged checklist entry for that person in [section 1](#1-repo).
Items marked **Skipped** are a team decision: we do not produce them.

### Checkpoint 1 — Week 6

| Item | Owner | How we cover it |
|------|-------|-----------------|
| One-page proposal | — | **Skipped** |
| Problem definition | — | **Skipped** |
| Selected data slice | Akshaj | Curated subset of the Amazon Product Dataset 2020, chosen by Akshaj |
| Proposed tools | Everyone | The README has a "Tools" section. Each owner adds the tools they use. Prefer tools that **uv** can manage (`uv add`), so the repo stays easy to work in. |
| Data ingestion notebook | Juan | Instead of a notebook: an ingestion script plus a `dodo.py`, with the configuration documented in the README. It doubles as the example of how to use doit in this repo. |
| Brief related work | — | **Skipped** |

### Checkpoint 2 — Week 8

| Item | Owner |
|------|-------|
| Architecture diagram | Devanshu |
| LangGraph flow | Devanshu |
| MCP/tool calls | Juan |
| UI wireframe | Alekhya |
| RAG evaluation plan | Akshaj |
| MCP README and schemas | Juan |
| Initial ProofAgent evaluation plan/scenarios | Beste |