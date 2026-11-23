# System architecture

**Owner:** Devanshu · **Issue:** #30 · Used in the root README and the slides.

```mermaid
flowchart LR
  user((User voice)) --> asr[ASR<br/>Whisper]
  asr -- transcript --> run["run_agent(transcript)"]

  subgraph graph [LangGraph agent]
    direction LR
    router[Router] --> planner[Planner] --> retriever[Retriever] --> reconcile[Reconcile] --> answerer[Answerer]
    answerer <--> critic[Critic]
    router -. unsafe / out of scope .-> refuse[Refuse]
    router -. unclear .-> clarify[Clarify]
  end

  run --> router
  retriever <-- "MCP (stdio)" --> mcp

  subgraph mcp [MCP server]
    rag[rag.search] --> index[(Chroma index<br/>Toys & Games catalog)]
    web[web.search] --> serper[(Serper API<br/>TTL cache, rate limit)]
  end

  critic -- final_answer, table, citations --> ui[Streamlit UI]
  critic -- spoken_summary --> tts[TTS] --> speaker((Voice out))
  run -. step_log .-> ui
  proof[ProofAgent harness] -- transcripts --> run
```

| Stage | Component | Owner | Code |
|-------|-----------|-------|------|
| Voice in / out, UI | Whisper ASR, TTS, Streamlit | Alekhya | `feature/ui` (planned) |
| Orchestration | LangGraph: Router, Planner, Retriever, Reconcile | Devanshu | [agent/](../agent/) |
| Answer quality | Answerer, Critic, guardrails | Beste | stub in [agent/nodes/answerer_stub.py](../agent/nodes/answerer_stub.py) |
| Tools | MCP server: `rag.search`, `web.search` | Juan | mock in [mocks/mcp_server.py](../mocks/mcp_server.py) |
| Private catalog | Preprocessing, Chroma index, `rag_search()` | Akshaj | `feature/rag` (planned) |
| Evaluation | ProofAgent scenarios and scorecard | Beste | `feature/eval` |

Details of the graph: [components/langgraph.md](components/langgraph.md).
