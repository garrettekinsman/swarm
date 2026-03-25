# swarm

A generic multi-agent swarm framework using LangGraph — specialized agent teams that pass work through a defined state graph. Each team lives in its own subfolder.

## Architecture Pattern

Each swarm team follows the same structure:
- **Orchestrator** — plans iterations, decides when to stop (usually Claude Opus)
- **Designer/Planner** — domain-specific spec generation
- **Workers** — parallel implementation branches (local + OpenRouter for scale)
- **Auditor** — security or quality review (Vera)
- **Reviewer** — final confidence scoring, loop-or-done decision

LangGraph wires these as nodes in a state graph. Each node receives the full shared state and returns a partial update. Edges encode routing logic including conditional loops.

## Teams

| Folder | Project | Status |
|--------|---------|--------|
| [`eldr-swarm/`](./eldr-swarm/) | EldrChat iOS SwiftUI generation | Active — first sprint complete |

## Adding a New Team

1. Create `your-project-swarm/` subfolder
2. Copy the agent pattern from `eldr-swarm/langgraph-agent-pattern-quick-ref.md`
3. Define your `SwarmState` TypedDict and agent nodes
4. Wire the graph and add a README

## Key Shared Principles

- **Sanitizer is mandatory** — all LLM output passes through `sanitizer_v2` before writing to disk or passing to next agent
- **Orchestrator runs as sub-agent** — never block the main session with a loop
- **Framework1 constraint** — one local inference at a time; heavy branches route to OpenRouter
- **OpenRouter for parallelism** — horizontal scale without new hardware
