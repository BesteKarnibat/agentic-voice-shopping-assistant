# Final Project: Agentic Voice-to-Voice AI Assistant for Product Discovery (E-Commerce)

> Original assignment text, reformatted as Markdown. Content is unchanged.
> For the actionable checklist, see [deliverables.md](deliverables.md).

## Project Context

In e-commerce, customers often ask for product recommendations by speaking naturally — for example:

> "I need an eco-friendly stainless-steel cleaner under $15."

Traditional chatbots can struggle to interpret intent, search private product catalogs, check live availability, compare alternatives, and provide grounded answers — especially in a hands-free experience.

In this project, you will build a voice-to-voice, multi-agent AI assistant that understands spoken requests, plans a solution, retrieves grounded evidence from a private product catalog (Amazon Product Dataset 2020), optionally compares results with live web information through MCP tools, and responds using text-to-speech (TTS) with citations and safety checks.

The agentic workflow must be orchestrated using **LangGraph**.

## Scope of the Project

Build an AI assistant that:

- Enables voice-to-voice interaction for product discovery and comparison.
- Uses a multi-agent workflow: **Intent → Plan → Retrieve/Tools → Answer/Critic → Voice Response**
- Uses LangGraph for agent orchestration.
- Uses Agentic RAG over a private product catalog.
- Uses an MCP server with two tools for private retrieval and live web search.
- Provides grounded recommendations with citations.
- Includes basic guardrails and safety checks.
- Evaluates the completed agent using the ProofAgent evaluation harness.
- Provides a simple UI showing the transcript, agent execution, results, citations, and evaluation evidence.

ASR/TTS may be fragment-based (non-streaming) or streaming. Fragment-based implementation is acceptable and encouraged for simplicity.

## Key Components

### 1. Agentic Orchestration — LangGraph

**Objective:** Structure the end-to-end workflow as a graph of cooperating agents.

**Tasks**

- **Router — Intent Classifier**
  - Identify the user's task.
  - Extract constraints such as budget, material, brand, category, or preferences.
  - Detect basic safety concerns.
- **Planner**
  - Determine which sources and tools should be used.
  - Decide whether private RAG, live web search, or both are necessary.
  - Define retrieval fields and comparison criteria.
- **Retriever — Agentic RAG**
  - Search the private product catalog.
  - Apply vector search and metadata filters.
  - Optionally invoke MCP tools for current prices or availability.
  - Reconcile conflicting information when necessary.
- **Answerer / Critic**
  - Generate a concise recommendation.
  - Verify grounding against retrieved evidence.
  - Include citations.
  - Apply safety and response-quality checks.

**Outcome:** A transparent, tool-aware agent pipeline with logged plans, tool calls, results, and citations.

### 2. Speech Recognition — ASR

**Objective:** Convert user speech into reliable text input for the agent.

**Tasks**

- Implement Whisper or a comparable ASR model.
- Support fragment-based recording (WAV/MP3) or streaming.
- Handle common accents and speech variations.
- Return timestamps when available.

**Outcome:** Accurate transcripts that can be passed directly into the LangGraph workflow.

### 3. Agentic RAG — Private + Live Data

**Objective:** Retrieve grounded product information from private data and augment it with live information when needed.

**Tasks**

- Index a curated subset of the Amazon Product Dataset 2020, such as Household Cleaning.
- Generate embeddings using fields such as:
  - Title
  - Features
  - Product description
  - Selected review snippets
- Store metadata such as:
  - Brand
  - Price
  - Rating
  - Ingredients
  - Category
- Implement hybrid retrieval using vector similarity + metadata filtering.
- Optionally implement a reranker.
- Use MCP-based web search for current price or availability when appropriate.
- Reconcile product matches using SKU, brand, title, or similarity.

**Outcome:** High-quality retrieval with clear provenance and conflict handling.

### 4. Tool & MCP Layer — Two-Tool MCP Server

**Objective:** Expose private retrieval and external search through a unified tool interface.

Build one MCP server exposing two tools:

#### `web.search`

Wrap a legitimate web-search API such as Brave, Serper, or Bing.

Example response:

```
{title, url, snippet, price?, availability?}
```

Requirements:

- Rate limiting
- Caching (TTL approximately 60–300 seconds)
- Source URLs
- Request/response logging

#### `rag.search`

Query the local vector database containing the Amazon dataset.

Example response:

```
{sku, title, price, rating, brand?, ingredients?, doc_id}
```

#### Additional Requirements

- Implement MCP tool discovery.
- Define tool names and JSON schemas.
- Use stdio or streamable HTTP/SSE transport.
- Log tool requests, responses, timestamps, and sources.
- Respect applicable API terms and source restrictions.

**Outcome:** Auditable and unified access to private and live information.

### 5. Text-to-Speech — TTS

**Objective:** Convert the final recommendation into a natural spoken response.

**Tasks**

- Use fragment-based synthesis or streaming with a TTS solution such as:
  - OpenAI TTS / Realtime
  - ElevenLabs
  - Azure Speech
  - Amazon Polly
  - Coqui
- Generate a concise spoken summary of approximately 15 seconds or less, aligned with the detailed results and citations displayed on screen.

**Outcome:** Natural voice output completing the voice-to-voice experience.

### 6. User Interface

**Objective:** Build a simple interface demonstrating the complete agent workflow.

Use Streamlit or React.

The UI should include:

- Microphone recording/upload
- Speech transcript
- Agent execution/step log
- Product comparison table
- Citations
- Private document IDs
- Live-source links
- TTS playback

**Outcome:** A clean interface that makes the agentic workflow and its evidence visible to the user.

### 7. Agent Evaluation with ProofAgent

**Objective:** Evaluate the completed voice-to-voice multi-agent assistant using ProofAgent to measure reliability, grounding, tool use, safety, and overall task performance.

Evaluation should be performed on the developed end-to-end agent, not only on the underlying LLM.

**Tasks**

Integrate the completed system with the ProofAgent evaluation harness and create representative evaluation scenarios covering:

- Product discovery
- User constraints and preferences
- RAG retrieval
- MCP/tool calls
- Product comparison
- Grounded recommendations
- Safety and guardrails
- Voice-based interactions

Evaluate relevant dimensions such as:

- Task Success
- Hallucination Resistance / Grounding
- Tool-Use Correctness
- Safety & Guardrail Compliance
- Response Quality

Include several adversarial or edge-case tests, for example:

- Ambiguous user requests
- Conflicting private and live information
- Products outside the requested budget
- Missing or unavailable products
- Incorrect tool results
- Unsupported product claims
- Unsafe requests

Use the evaluation results to analyze where failures occur across the system:

**ASR → Router → Planner → RAG/MCP → Answerer → TTS**

Students must include the final ProofAgent scorecard/results and analyze at least two failure cases, including how the agent could be improved.

**Outcome:** A measurable evaluation demonstrating not only that the agent works, but how reliably, safely, and consistently it performs before deployment.

## Choice of LLM — Model-Agnostic Requirement

Teams may use any LLM, commercial or open-weight, as long as the model is swappable through environment variables or configuration.

**Hosted Models**

- OpenAI GPT
- Anthropic Claude
- Google Gemini
- AWS Bedrock providers

**Open-Weight Models**

- Llama 3.x
- Mistral
- Qwen
- Phi
- Other suitable models

**Requirements**

- Keep tool/function calling enabled.
- Limit context to grounded evidence where possible.
- Require citations for factual product recommendations.
- Log important prompts and system messages.
- Avoid hard-coding the entire application to one model provider.

## Example Voice Interaction

**User — Voice**

> "Recommend an eco-friendly stainless-steel cleaner under fifteen dollars."

**System — Voice**

> "Here are three options that fit your budget and material. My top recommendation is Brand X Steel-Safe Eco Cleaner, with plant-based surfactants, a 4.6-star rating, and a typical price of $12.49. I compared it with two alternatives. Details and sources are displayed on screen. Would you like the most affordable or the highest-rated option?"

**On Screen**

A top-3 comparison table displaying:

| Product | Price | Rating | Ingredients | Source | Citation |
|---------|-------|--------|-------------|--------|----------|

The interface should include citations to private document IDs and, when applicable, live sources.

## Data

Use the **Amazon Product Dataset 2020 (Kaggle)** as the primary private corpus.

### Target Schema

**`products.parquet`**

- `id`
- `title`
- `brand`
- `category`
- `price`
- `rating`
- `features`
- `ingredients`

**`reviews.parquet` — Optional**

- `product_id`
- `stars`
- `summary/snippets`

### Indexing

Generate embeddings over:

- Title + Features + Selected Review Snippets

Store the vectors using:

- FAISS
- Chroma
- Or another suitable vector database

Normalize relevant units — for example, price per ounce — when needed for fair product comparisons.

## Expected Deliverables

### 1. Voice-to-Voice Assistant

A functioning multi-agent LangGraph pipeline implementing:

**Voice → ASR → Agentic Workflow → RAG/MCP → Answer → TTS**

### 2. Agentic RAG + MCP

- Private Amazon catalog retrieval
- At least one live MCP web comparison
- Two-tool MCP server
- Tool schemas and discovery
- Logging and citations

### 3. User Interface

Streamlit or React application with:

- Mic input
- Transcript
- Agent execution steps
- Comparison table
- Citations
- TTS playback

### 4. ProofAgent Evaluation

Submit:

- Evaluation configuration
- Evaluation/test scenarios
- Adversarial/edge-case scenarios
- ProofAgent scorecard/results
- Analysis of at least two failures
- Proposed improvements

### 5. Documentation

Include:

- Data preprocessing and indexing
- LangGraph architecture
- MCP server/tool schemas
- Safety considerations
- Evaluation methodology
- Setup instructions
- `.env.example`
- Run/build scripts

## Implementation Guidance

### `web.search`

Call a web-search API and normalize the output:

```
{title, url, snippet, price?, availability?}
```

Cache requests and retain source URLs.

### `rag.search`

Use vector search + metadata filters over the Amazon dataset and return `doc_id` for citation.

### Planner

- Prefer `rag.search` for private product facts.
- When the user requests information such as "current," "latest," "available now," or "current price," the planner should also consider `web.search`.
- Reconcile private and live results using SKU, brand, and title similarity.

### ASR/TTS

Start with a simple fragment-based implementation:

**Record → Transcribe → Process → Synthesize → Play**

Streaming is optional.

### Safety

Implement basic controls including:

- Tool/domain restrictions where appropriate
- Guardrails
- Grounded answers
- Avoidance of unsupported claims
- Safe handling of chemical/product advice
- Protection of secrets and API keys

## Milestones

### Checkpoint 1 — Week 6

Submit:

- One-page proposal
- Problem definition
- Selected data slice
- Proposed tools
- Data ingestion notebook
- Brief related work

### Checkpoint 2 — Week 8

Submit:

- Architecture diagram
- LangGraph flow
- MCP/tool calls
- UI wireframe
- RAG evaluation plan
- MCP README and schemas
- Initial ProofAgent evaluation plan/scenarios

### Final — Week 10

Deliver:

- ≤7-minute live demo
- Working voice-to-voice agent
- ProofAgent evaluation results
- Repository with clean code
- README
- Index/MCP build scripts
- Short presentation

## Grading — 100 Points

| Area | Points | What is graded |
|------|-------:|----------------|
| Functionality | 25 | End-to-end voice flow, multi-agent routing, working application, citations. |
| Agentic RAG Quality | 20 | Retrieval accuracy, grounding, hybrid retrieval, quality of recommendations. |
| MCP Server | 15 | Two functional tools, discovery, schemas, caching, and logging. |
| Planning & Tool Use | 10 | Appropriate planning, tool selection, conflict handling, and reconciliation. |
| ProofAgent Evaluation | 10 | Evaluation coverage, meaningful test scenarios, scorecard/results, adversarial testing, and failure analysis. |
| UI/UX | 8 | Clean interface, transcript, comparison table, citations, and audio playback. |
| Presentation | 7 | Clear and engaging ≤7-minute demonstration covering architecture, results, evaluation, and limitations. |
| Prompt Disclosure | 5 | Complete disclosure of the important prompts used throughout the system. |

## Prompt Disclosure Requirement

Submit a `prompts/` folder or equivalent README section containing the main prompts used by the system, including:

- System prompts
- Router prompts
- Planner prompts
- Tool-call instructions
- Answerer/Critic prompts
- Guardrail instructions
- Few-shot examples, if used

Clearly indicate how each prompt maps to the corresponding LangGraph node, agent, or tool.

## Final System

The completed project should demonstrate the full lifecycle of building and evaluating a production-oriented agentic application:

**🎙 Voice → ASR → Intent → Planning → RAG/MCP Tools → Grounded Answer → TTS → ProofAgent Evaluation**

The goal is not only to demonstrate that an AI agent can work, but also to provide evidence of how well it works, where it fails, and how it can be improved before deployment.
