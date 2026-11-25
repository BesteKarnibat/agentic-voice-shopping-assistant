# Prompts

The assignment requires disclosing every important prompt in the system and mapping it to the LangGraph node,
agent, or tool that uses it. This is worth 5 points and is graded on completeness.

**Owners:** Devanshu (Router, Planner, Retriever) and Beste (Answerer, Critic, guardrails).

## Rules

- Every prompt the code sends to an LLM lives here as its own file, and the code loads it from here.
  That way this folder always matches what actually runs.
- One file per prompt, named `<node>_<purpose>.md`, e.g. `router_system.md`.
- Only the section between `<!-- BEGIN PROMPT -->` and `<!-- END PROMPT -->` is sent to the LLM; the rest of the
  file documents it. Load prompts with `agent.prompts.load_prompt("<file stem>", **placeholders)`.
- Few-shot examples go in the same file as their prompt, or in `<node>_examples.md`.
- When you add or rename a prompt, update the table below.

## Prompt → node mapping

| Prompt file | Type | LangGraph node / tool | `AgentState` fields it produces | Owner | Status |
|-------------|------|-----------------------|---------------------------------|-------|--------|
| `system.md` | Shared system prompt | All LLM nodes (`router`, `planner`) | — | Devanshu | draft |
| `router_system.md` | Router prompt (+ embeds `guardrails.md`) | `router` | `intent`, `constraints`, `safety`, `clarification_question` | Devanshu | draft |
| `planner_system.md` | Planner prompt | `planner` | `plan` | Devanshu | draft |
| `retriever_tools.md` | Tool-use policy (no LLM: deterministic execution of the plan) | `retriever` → `rag.search`, `web.search`; `reconcile` | `rag_results`, `web_results`, `reconciled` | Devanshu | draft |
| `refusal.md` | Fixed responses (no LLM), templates parsed from `guardrails.md` | `refuse`, `clarify` | `final_answer`, `spoken_summary` | Devanshu | draft |
| `answerer_system.md` | Answerer prompt | `answerer` | `draft_answer`, `final_answer`, `comparison_table`, `citations`, `spoken_summary` | Beste | todo |
| `critic_system.md` | Critic prompt | `critic` | `critic` | Beste | todo |
| `guardrails.md` | Guardrail instructions | `router` (input), `critic` (output) | `safety`, `critic.safety_issues` | Beste | draft |

Add rows for any other prompt, for example a separate spoken-summary prompt or a ProofAgent judge prompt.
