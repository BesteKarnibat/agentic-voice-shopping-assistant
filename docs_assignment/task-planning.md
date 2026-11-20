# Task Planning

Team plan: who owns what, the critical path, handoffs, and branches.
Requirements are in [deliverables.md](deliverables.md). The original assignment is in [assignment.md](assignment.md).

## Ownership

| # | Area | Owns | Key deliverables | Responsible |
|---|------|------|------------------|-------------|
| 1 | Data & RAG | Dataset → index → retrieval | Clean curated slice, parquet files, embeddings, FAISS/Chroma, hybrid search (vector + metadata filters), optional reranker, price-per-unit normalization | Akshaj |
| 2 | MCP Server | Tool layer | Two-tool MCP server, tool discovery, JSON schemas, Brave/Serper wrapper, TTL cache, rate limiting, request/response logging, MCP README | Juan |
| 3 | LangGraph Lead | Orchestration and integration | Graph wiring, Router, Planner, Retriever node (calls MCP), reconciliation of private vs. live results, step logging, owns the `main` branch and integration | Devanshu |
| 4 | Voice & UI | Front and back of the experience | Whisper ASR (fragment-based), TTS (~15 s summary), Streamlit app with mic, transcript, step log, comparison table, citations, doc IDs, live links, audio playback | Alekhya |
| 5 | Answerer/Critic, Safety & Eval | Quality and evidence | Answerer + Critic nodes, citation enforcement, guardrails, ProofAgent integration, test and adversarial scenarios, scorecard, failure analysis | Beste |

Added after the original plan (Nov 20):

- **Presentation + demo:** Juan builds the slides. Alekhya owns the live demo on the UI (script, backup video, rehearsal).
- `prompts/` **disclosure:** Devanshu (Router, Planner, Retriever) and Beste (Answerer, Critic, guardrails).
- **Run orchestration:** Devanshu, as integrator. pydoit is suggested.

## Schedule

Thanksgiving is Thursday, November 26, and no work is planned that day.
The plan's Days 1–11 are compressed into Nov 21–30. Dec 1–2 are the team test and the official deadline. Bold rows are milestones that must not slip.

| Date | Plan day | Milestone | Done when |
|------|----------|-----------|-----------|
| **Fri Nov 20** | 0 | **Kick-off** | Plan approved, docs merged, branches created, technical decisions closed, API keys obtained |
| Sat Nov 21 | 1 | Parallel start | Everyone working on their own branch |
| **Sun Nov 22** | 2 | **Sample data + graph skeleton** | ~100-product sample file shared (Akshaj); stub graph runs (Devanshu); `web.search` works (Juan) |
| Mon Nov 23 | 3 | `rag_search()` v0 | Akshaj hands Juan a working search on the real index |
| **Tue Nov 24** | 4 | **MCP server ready** | Both tools served and discoverable (Juan); `run_agent(transcript) → state` exposed (Devanshu) |
| **Wed Nov 25** | 5 | **First end-to-end (text)** | Real Answerer/Critic in the graph (Beste); UI calls `run_agent` (Alekhya) |
| Thu Nov 26 | — | Thanksgiving | — |
| Fri Nov 27 | 6–7 | Voice integration | Mic → ASR → graph → TTS → UI works end to end |
| **Sat Nov 28** | 8 | **Feature freeze + first ProofAgent run** | No new features after this; Beste reports failures to owners |
| Sun Nov 29 | 9 | Fix loop + submission prep | Second ProofAgent run, scorecard, failure analysis, README, `prompts/`, slides |
| **Mon Nov 30** | 10 | **Repo ready (internal target)** | Everything merged into `main`; clean-machine test passes; slides and backup video done |
| Tue Dec 1 | — | Full-team test and rehearsal | Whole team rehearses the ≤7-min session on the final repo; only critical fixes |
| **Wed Dec 2** | — | **Official deadline** | Submission / demo |

## Critical path

**Akshaj's index → Juan's** `rag.search` **→ Devanshu's Retriever → Beste's answer quality → full ProofAgent evaluation**

Akshaj ships a rough v0 of the search by Day 3–4 and improves it afterward.

## Fully parallel from Day 1

- Juan builds `web.search`.
- Alekhya builds Whisper, TTS, and the UI layout.
- Beste writes evaluation scenarios and guardrail rules, and learns ProofAgent.
- Devanshu builds the graph skeleton with stub nodes.
- Akshaj exports ~100 real products as a sample file so everyone can test with real data early.

## Handoff points

"Plan day" is from the original plan. "Target date" compresses it to fit the internal target (repo ready Mon Nov 30, 2026; official deadline Wed Dec 2) around Thanksgiving. See the full [schedule](#schedule).

| Plan day | Target date | Who hands off | To whom | What |
|----------|-------------|---------------|---------|------|
| 2 | Sun Nov 22 | Akshaj | Everyone | Sample file of ~100 real products |
| 2 | Sun Nov 22 | Devanshu | Alekhya, Beste | Runnable graph skeleton with stub nodes |
| 3–4 | Mon Nov 23 | Akshaj | Juan | v0 `rag_search()` function on the real index |
| 4–5 | Tue Nov 24 | Juan | Devanshu | MCP server running with both tools |
| 5 | Tue Nov 24 | Devanshu | Alekhya, Beste | Entry point `run_agent(transcript) → state` |
| 5–6 | Wed Nov 25 | Beste | Devanshu | Real Answerer and Critic nodes plugged into the graph |
| 7–8 | Fri Nov 27 | Everyone | Everyone | End-to-end integration, led by Devanshu |
| 9 | Sat Nov 28 | Devanshu | Beste | Stable full system for the first ProofAgent run |

## Helping the bottleneck

- Juan will likely finish `web.search` early and can help Akshaj with data cleaning or indexing.
- Alekhya may finish the UI layout early and can help Beste turn test scenarios into ProofAgent format.
- During the fix loop, Beste reports failures and the owner fixes them:

| Failure type | Goes to |
|--------------|---------|
| Retrieval | Akshaj |
| Tool / MCP | Juan |
| Routing and planning | Devanshu |
| Voice and display | Alekhya |

## Branches

| Branch | Owner |
|--------|-------|
| `feature/rag` | Akshaj |
| `feature/mcp` | Juan |
| `feature/graph` | Devanshu |
| `feature/ui` | Alekhya |
| `feature/eval` | Beste |

Everyone merges into `main` through pull requests that Devanshu reviews.
