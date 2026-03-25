# EldrChat Agent Swarm — Team Docs & Test Scripts

**Last updated:** 2026-03-24  
**Canonical repo:** `github.com/garrettekinsman/eldr-swarm`  
**Source code lives in:** `projects/EldrChat/` (this repo)

---

## What Is the Swarm?

EldrChat uses a **LangGraph multi-agent pipeline** to generate, iterate, and audit iOS SwiftUI views. Instead of a single model writing code, a team of specialized agents passes work through a defined graph — each agent does what it's best at.

This directory documents how the swarm is structured, how to run it, lessons learned, and what each script does.

---

## Agent Team

```
┌─────────────────────────────────────────────────────────────────┐
│  ELDR iOS SWARM PIPELINE                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [GAHO]  Claude Opus 4-6                                         │
│          Orchestrator. Plans iterations, decides when to stop.   │
│          Reviews GARRO's confidence score each round.            │
│                                                                  │
│  [GARRO] kimi-k2.5 via OpenRouter                                │
│          Designer. Writes SwiftUI design specs from reference.   │
│          Also does final visual review: compares screenshot       │
│          to spec, outputs confidence score (0-100).              │
│                                                                  │
│  [CODER] qwen3-coder-next  (10 parallel branches)                │
│          Implementer. Takes GARRO's spec → writes Swift files.   │
│          1 branch runs local (Framework1 via model router).      │
│          Up to 9 additional branches run via OpenRouter.         │
│          3-tier fallback: local → OpenRouter → Sonnet            │
│                                                                  │
│  [BUILDER] xcrun simctl + swift build                            │
│          Tool node (no LLM). Writes files to disk, builds,       │
│          captures simulator screenshot for GARRO review.         │
│                                                                  │
│  [VERA]  Claude Sonnet 4-6                                       │
│          Security auditor. Reviews generated code for P0/P1/P2   │
│          issues before GARRO does visual review.                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Loop:** GAHO → GARRO design → CODER (parallel) → BUILDER → VERA audit → GARRO review → repeat if confidence < 80% or iter < 5

---

## Scripts

### `parallel-qwen-workflow.py` — iOS Parallel Swarm (main pipeline)
Full 5-agent LangGraph loop for iOS SwiftUI generation.

```bash
# Set env vars first
export ANTHROPIC_API_KEY=...
export OPENROUTER_API_KEY=...

# Run (spawns Opus orchestrator as sub-agent — don't run directly in main session)
python3 parallel-qwen-workflow.py
```

**Outputs:**
- `ios-swarm-output/Sources/EldrChat/*.swift` — generated Swift files
- `ios-swarm-TIMESTAMP.log` — full run log
- `ios-swarm-metrics-TIMESTAMP.json` — iteration stats, confidence scores, model usage

### `swarm-viz.py` — Live ASCII Dashboard
Tails a swarm log and renders a real-time status dashboard.

```bash
# Auto-find latest log and watch live
python3 swarm-viz.py

# Print once and exit
python3 swarm-viz.py --once

# HTTP server with SSE (for remote watching)
python3 swarm-viz.py --serve 8888
```

### `langgraph-team-audit/eldrchat_ui_pipeline.py` — Earlier Single-Branch Pipeline
The original (pre-parallel) single-coder pipeline. Used during early sprint testing.

```bash
python3 langgraph-team-audit/eldrchat_ui_pipeline.py
```

---

## LangGraph: Why We Use It

Traditional approach: spawn sub-agents one at a time, parse messages, route manually. Brittle, verbose.

LangGraph approach: define a **state graph** where each agent is a node. Edges encode routing logic. The framework handles state passing, conditional branching, and loop termination.

```python
# Simplified graph structure
graph.add_node("orchestrator", gaho_node)
graph.add_node("designer",     garro_node)
graph.add_node("coder",        parallel_coder_node)   # 10 concurrent workers
graph.add_node("auditor",      vera_node)
graph.add_node("reviewer",     garro_review_node)

graph.add_edge("orchestrator", "designer")
graph.add_edge("designer",     "coder")
graph.add_edge("coder",        "auditor")
graph.add_edge("auditor",      "reviewer")
graph.add_conditional_edges("reviewer", route_fn)  # loop or done
```

Each node receives the full `SwarmState` TypedDict and returns a partial update. Clean, auditable, reproducible.

---

## OpenRouter Integration

**Why OpenRouter for parallel branches?**  
Framework1 runs one model at a time (61GB qwen fills VRAM). For parallel CODER branches, OpenRouter gives us horizontal scale without spinning up new hardware.

**Models used via OpenRouter:**
| Agent | Model | Notes |
|-------|-------|-------|
| GARRO design | `moonshotai/moonshot-kimi-k2.5` | kimi-k2.5, strong at design specs |
| CODER branches 2-10 | `qwen3-coder-next` | same model as local, just cloud-hosted |
| VERA fallback | `anthropic/claude-sonnet-4-6` | via Anthropic directly, not OpenRouter |

**Config:** `langgraph-team-audit/team-openrouter-integration-v1-2026-03-24.md`

---

## Lessons Learned (First Sprint — 2026-03-24)

From `ios-swarm-metrics-20260324-182720.json`:

| Issue | Fix |
|-------|-----|
| kimi-k2.5 returns prose, not JSON | More robust JSON extraction; fallback to Sonnet for scoring |
| `KeyManager.swift` failed regex in iter 2 | Recovered in iter 3 via OpenRouter qwen — retry logic works |
| SIGTERM during iter 3 GARRO review | Increase timeout to 900s; add early fallback before GARRO review |
| OPENROUTER_TIMEOUT at 60s too short | Set to 120s minimum — kimi regularly hits 90s |
| Confidence 72% on iter 1 is normal | Pipeline correctly continues to iter 2 |
| Fake SRI hashes in generated code | VERA flags them; sanitizer auto-strips |

**Final output:** 10 Swift files written, confidence ~65% (GARRO JSON parse failed all 3 iterations — real score unconfirmed but Vera estimated ~65%).

---

## Key Design Decisions

**Sanitizer is mandatory in the pipeline.**  
All LLM output passes through `sanitizer_v2.sanitize_text()` before being written to disk or passed to the next agent. Prevents injection attacks from model outputs.

**Gaho never runs the pipeline directly.**  
The orchestrator sub-agent runs the loop. Gaho's job: dispatch only, then `sessions_yield()`. Running inference loops in the main session blocks all other messages.

**Framework1 constraint is injected into every orchestrator prompt.**  
One inference at a time on local hardware. Orchestrator must route heavy tasks to cloud and light tasks to local. See `FRAMEWORK1-ORCHESTRATOR-CONSTRAINT.md`.

---

## File Index

```
EldrChat/
├── parallel-qwen-workflow.py       ← iOS parallel swarm (main)
├── swarm-viz.py                    ← live ASCII dashboard
├── swarm-viz-server-arch.md        ← architecture for SSE server mode
├── ios-swarm-output/               ← generated Swift files
├── ios-swarm-*.log                 ← run logs (gitignored — large)
├── ios-swarm-metrics-*.json        ← run metrics
├── langgraph-team-audit/
│   ├── eldrchat_ui_pipeline.py     ← early single-branch pipeline
│   ├── team-audit-*.log            ← audit run logs
│   ├── team-audit-metrics.json     ← audit metrics
│   ├── team-openrouter-integration-v1-2026-03-24.md
│   ├── team-audit-report-*.md      ← iteration reports
│   └── PIL-MOCKUP-TECHNIQUE.md     ← mockup generation technique
├── langgraph-ui-sprint/
│   ├── eldrchat_ui_pipeline.py     ← UI sprint pipeline
│   └── pipeline-*.log
└── xcode-langgraph-team-setup-v1-2026-03-24.md  ← full team architecture doc
```

---

## References

- Full team architecture: `xcode-langgraph-team-setup-v1-2026-03-24.md`
- OpenRouter integration: `langgraph-team-audit/team-openrouter-integration-v1-2026-03-24.md`
- Framework1 constraint: `FRAMEWORK1-ORCHESTRATOR-CONSTRAINT.md`
- Sanitizer: `projects/agent-collaboration/sanitizer_v2.py`
- Model router: `projects/model-router/`
