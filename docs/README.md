# Documentation

The assignment requires documentation of: data preprocessing and indexing, LangGraph architecture, MCP server/tool
schemas, safety considerations, evaluation methodology, setup instructions, `.env.example`, and run/build scripts.

Each owner writes **one file in [components/](components/)**. Each file already has a skeleton: fill in the
sections, replace every `TODO`, and delete guidance comments (`<!-- ... -->`) when done.

## Who writes what

| Assignment item | File | Owner | Branch | Status |
|-----------------|------|-------|--------|--------|
| Data preprocessing and indexing | [components/data-rag.md](components/data-rag.md) | Akshaj | `feature/rag` | todo |
| MCP server / tool schemas | [components/mcp.md](components/mcp.md) | Juan | `feature/mcp` | todo |
| LangGraph architecture | [components/langgraph.md](components/langgraph.md) | Devanshu | `feature/graph` | todo |
| Setup, `.env.example`, run/build scripts | [components/setup.md](components/setup.md) | Devanshu | `feature/graph` | todo |
| Voice and UI usage | [components/voice-ui.md](components/voice-ui.md) | Alekhya | `feature/ui` | todo |
| Safety considerations | [components/safety.md](components/safety.md) | Beste | `feature/eval` | todo |
| Evaluation methodology | [components/evaluation.md](components/evaluation.md) | Beste | `feature/eval` | todo |

Prompts are documented separately in [../prompts/README.md](../prompts/README.md) (mapped to nodes).
Update the Status column here (`todo` → `draft` → `done`) in the same PR that changes the file.

## Writing rules

- Write for a grader who has not seen the code. Say what it does, why it was designed that way, and how to run it.
- Document what exists. Link real paths, functions, and commands, and check they work before writing them down.
  Mark anything not built yet as `Planned`, never describe it as done.
- Prefer a short table or diagram over a long paragraph. Mermaid diagrams are fine.
- Record **decisions and trade-offs** (what was chosen, what was rejected, why). Graders look for these.
- Include the real numbers when you have them (index size, latency, scores). No numbers, no claim.
- Don't paste secrets, API keys, or raw dataset rows beyond a few illustrative examples.
- Don't duplicate the contracts. Link [../contracts/](../contracts/) and explain how to use them.
- English only. Keep each file under ~2 pages; link to code for the details.

## Review and trim before you submit

The skeletons are a guide, not a form to fill in completely. Before opening your PR, **review your file and remove
information that is not relevant**:

- Delete any section that doesn't apply to your component, instead of leaving it empty or padded with filler.
- Cut details a reader doesn't need to understand, run, or evaluate the component (internal experiments, dead ends,
  obvious facts, anything the code or contracts already say clearly).
- Remove text that was only generated or copied to fill space. Everything left should be accurate and checked by you.
- Keep what graders and teammates need: what it does, key decisions, how to run it, real numbers, and limitations.
- Re-read the file once as a newcomer. If a sentence doesn't help them, delete it.

Devanshu checks this during PR review and may ask you to trim further.

## Definition of done (per file)

- [ ] No `TODO` or guidance comments left
- [ ] Every command was run from a fresh shell and works
- [ ] Every path and link resolves
- [ ] Decisions and limitations are stated
- [ ] Reviewed and trimmed: no irrelevant or empty sections
- [ ] Status updated in the table above

## Final README

The root `README.md` is assembled from these files by Devanshu (integrator): overview, architecture figure, quick start,
and a link to each component file. Don't write the root README yourself.
