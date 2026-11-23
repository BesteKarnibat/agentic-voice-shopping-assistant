# Refusal and clarification responses

**Owner:** Devanshu · **Issue:** #60 · **Nodes:** `refuse`, `clarify` ([agent/nodes/respond.py](../agent/nodes/respond.py))
**Writes:** `final_answer`, `spoken_summary` (no retrieval, no citations)

**No LLM prompt.** Refusals use the fixed template for the safety category. The code parses the templates from
Beste's [guardrails.md](guardrails.md) at runtime (`agent/prompts.py: guardrail_templates()`), so that file stays the
single source of truth. Built-in fallbacks in `respond.py` are used only if its layout changes.

| Router result | Node | Response |
|---------------|------|----------|
| `safety.category = injury_emergency` | `refuse` | guardrails.md §1 template (call 911 / Poison Help) |
| `safety.category = harmful_use` | `refuse` | guardrails.md §2 template |
| `safety.category = minor_exploitation` | `refuse` | guardrails.md §3 template |
| `safety.category = prompt_injection`, `is_safe = false` | `refuse` | guardrails.md §4 template |
| `intent = out_of_scope` | `refuse` | guardrails.md §7 template (redirect) |
| `intent = unclear` | `clarify` | The Router's `clarification_question` (see [router_system.md](router_system.md)) |
| Empty transcript | `clarify` | "Sorry, I didn't catch that. What kind of toy or game are you looking for?" |
