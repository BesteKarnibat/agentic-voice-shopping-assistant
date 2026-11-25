# Prompts

The assignment requires disclosing every important prompt in the system and mapping it to the LangGraph node,
agent, or tool that uses it. This is worth 5 points and is graded on completeness.

**Owners:** Devanshu (Router, Planner, Retriever) and Beste (Answerer, Critic, guardrails).

## Rules

- Every prompt the code sends to an LLM lives here as its own file, and the code loads it from here.
  That way this folder always matches what actually runs.
- One file per prompt, named `<node>_<purpose>.md`, e.g. `router_system.md`.
- Few-shot examples go in the same file as their prompt, or in `<node>_examples.md`.
- When you add or rename a prompt, update the table below.

## Prompt → node mapping

| Prompt file | Type | LangGraph node / tool | `AgentState` fields it produces | Owner | Status |
|-------------|------|-----------------------|---------------------------------|-------|--------|
| `system.md` | Shared system prompt | All LLM nodes | — | Devanshu | todo |
| `router_system.md` | Router prompt | `router` | `intent`, `constraints`, `safety`, `clarification_question` | Devanshu | todo |
| `planner_system.md` | Planner prompt | `planner` | `plan` | Devanshu | todo |
| `retriever_tools.md` | Tool-call instructions | `retriever` → `rag.search`, `web.search` | `rag_results`, `web_results`, `reconciled` | Devanshu | todo |
| `answerer_system.md` | Answerer prompt | `answerer` | `draft_answer`, `final_answer`, `comparison_table`, `citations`, `spoken_summary` | Beste | todo |
| `critic_system.md` | Critic prompt | `critic` | `critic` | Beste | todo |
| `guardrails.md` | Guardrail instructions | `router` (input), `critic` (output) | `safety`, `critic.safety_issues` | Beste | todo |
| `asr_initial_prompt.md` | Whisper decoding prompt (vocabulary bias, not an LLM prompt) | `asr` ([asr/transcriber.py](../asr/transcriber.py)) | `transcript`, `asr_segments` | Alekhya | done |
| `tts_instructions.md` | Voice-style instructions for OpenAI `gpt-4o-mini-tts` | `tts` ([tts/synthesizer.py](../tts/synthesizer.py)) | `tts_audio_path` | Alekhya | done |

Add rows for any other prompt, for example a separate spoken-summary prompt or a ProofAgent judge prompt.
