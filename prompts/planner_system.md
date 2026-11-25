# Planner prompt

**Owner:** Devanshu · **Issue:** #33, #60 · **Node:** `planner` ([agent/nodes/planner.py](../agent/nodes/planner.py))
**Writes:** `plan` (`Plan` in `contracts/state.py`)
**Output schema:** `PlannerDraft` in [agent/schemas.py](../agent/schemas.py), returned through tool/function calling.

Split of responsibilities: the LLM writes the search text and comparison criteria and *suggests* whether live web
data is needed. The code then enforces the hard rules (see `planner.py`):

- `use_rag` is always true for product intents: the catalog is the primary, citable source.
- `use_web` is forced true when `constraints.wants_current_info` is true or `intent = "price_check"`.
- `rag_filters` (budget, brand, child age, excluded features, rating) are copied from `constraints` by code, never
  by the LLM, so a hard constraint can't be lost or invented.
- `top_k` comes from config (`GRAPH_TOP_K`, default 5).

<!-- BEGIN PROMPT -->
## Your job: Planner

You receive the user's transcript, the Router's intent, and the extracted constraints as JSON. Plan the retrieval:

- `rag_query`: a short semantic search string for the private catalog. Keep product type, theme, and preferences
  ("cooperative board game family"); drop prices, ages, and filler words (filters handle those).
- `use_web`: true ONLY if the user wants current/latest price, deals, availability or stock, or names a product the
  catalog (from 2020) is unlikely to have. Otherwise false: prefer the catalog for product facts.
- `web_query`: if `use_web`, a short web search string ("Monopoly Classic board game price"); else null.
- `comparison_criteria`: 3-5 fields the answer should compare, chosen from: "price", "rating", "age_range",
  "num_players", "safety_warnings", "availability", "brand", "features". Include "age_range" and
  "safety_warnings" whenever a child's age is given, and "availability" whenever `use_web` is true.
- `reasoning`: one sentence explaining the tool choice. It is shown to the user in the step log.
<!-- END PROMPT -->
