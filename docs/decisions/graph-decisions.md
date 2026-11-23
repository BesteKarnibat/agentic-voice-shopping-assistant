# Decisions: LangGraph / integration (Devanshu)

Each section below can be pasted as-is as a comment on the issue and on #2.

---

## #4 · LLM provider/model and how model-agnostic is implemented

**Decision:** OpenAI `gpt-4o-mini` for development and the demo; Anthropic `claude-haiku-5-5` supported as the
second provider (used for the #16 swap demo). Mechanism: LangChain `init_chat_model(model, model_provider=...)`
behind one helper, `agent.llm.get_chat_model(node)` / `invoke_structured(...)`.

- Config keys (every node reads them the same way, [config/llm.py](../../config/llm.py)): `LLM_PROVIDER`, `LLM_MODEL`,
  `LLM_TEMPERATURE` (default 0.2), `LLM_MAX_TOKENS_<NODE>`, optional `LLM_MODEL_<NODE>`. Defaults live in code; env
  vars override. `.env` holds only the API keys.
- Tool calling stays on: Router and Planner structured output uses `with_structured_output(method="function_calling")`,
  tested against OpenAI.
- `LLM_PROVIDER=fake` gives an offline deterministic stand-in for tests.
- **Still open:** who pays for the demo key.

**Why:** two strings switch providers, with no custom adapter code to maintain, and it covers OpenAI, Anthropic, Bedrock,
Gemini and Ollama if we need them later.

---

## #20 · MCP transport and tool-name mapping

**Decision (proposed, Juan to confirm):** **stdio**. The Retriever starts the server as a subprocess
(`MCP_SERVER_COMMAND` + `MCP_SERVER_ARGS` in [config/graph.py](../../config/graph.py)) and keeps one session open per
process. **Tool names stay `rag.search` / `web.search`** in MCP; no mapping is needed because the Retriever calls tools
directly by MCP name. The LLM never gets them as function names: the Planner (LLM) chooses the tools, the Retriever runs them.

What the graph needs from the real server (the mock in `mocks/mcp_server.py` already does this):
1. stdio transport, startable as `python -m <module>` from the repo root.
2. `list_tools` advertises both tools with `inputSchema` = `TOOLS[name]["input"].model_json_schema()`.
3. `call_tool` returns the output model as `structuredContent` (or the same JSON as text), e.g.
   `return RagSearchOutput(...).model_dump(mode="json")` with the low-level server.
4. Errors → `isError` result (the graph logs it and continues).
5. Pin `mcp>=1.20,<2` (already in `pyproject.toml`): mcp 2.x renamed FastMCP and changed the server API.

**Why stdio:** one process, no port or extra doit task to start a server, and the simplest path for the
one-command run. Streamable HTTP is only worth it if the server must run on another machine, and that isn't planned.

---

## #21 · `run_agent()` signature

```python
from agent import run_agent

state: dict = run_agent(
    transcript: str,
    *,
    session_id: str | None = None,        # generated if None
    asr_segments: list[dict] | None = None,
    on_step: Callable[[StepLogEntry], None] | None = None,
)
```

- **Sync.** Internally the graph runs on a background asyncio loop that also keeps the MCP connection open.
- **Returns** the final `AgentState` as a JSON-serializable dict: `final_answer`, `comparison_table`, `citations`,
  `spoken_summary`, `step_log`, `errors`, plus every intermediate field.
- **Streaming:** `on_step(entry)` is called **in the caller's thread** as each node finishes, so Streamlit can render
  the step log live. The full log is also in the returned state.
- **Errors:** never raises for agent failures. Tool, LLM and MCP failures go to `errors`; `final_answer` and
  `spoken_summary` always contain speakable text.
- **Timeout:** `RUN_TIMEOUT_S` (default 120 s) → partial state + an `errors` entry.
- One turn per call (no multi-turn memory yet). A clarifying question comes back as `final_answer` with `intent = "unclear"`;
  the UI sends the user's reply as a new transcript.

---

## #39 · How ProofAgent calls the agent

**Proposal (Beste to confirm against the harness):** ProofAgent calls the **Python callable** `run_agent(transcript)`
directly, with transcripts as scenario inputs. No HTTP server.

- Text scenarios: `state = run_agent(scenario["input"])`. Score from `final_answer`, `citations`, `comparison_table`,
  `step_log` (tool calls, plan) and `errors`.
- Voice scenarios: audio fixtures (WAV) → Alekhya's ASR function → `run_agent(transcript, asr_segments=...)`, so ASR
  errors show up in the failure analysis by stage.
- If the harness can only call an HTTP endpoint, I'll add a thin FastAPI wrapper around `run_agent`; it's about 20 lines.
- Use a fixed `LLM_PROVIDER` / `LLM_MODEL` for scored runs and record them with the scorecard (they're in each
  run's `step_log`).

**Why:** the callable is simplest, exposes the full state for tool-use and grounding scores, and needs no server.
