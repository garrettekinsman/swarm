# eldr-swarm

EldrChat iOS SwiftUI generation pipeline — 5-agent LangGraph team that designs, implements, builds, audits, and iterates on SwiftUI views.

## Agent Team

```
GAHO (Opus)        — orchestrator, plans iterations, stops when confidence ≥ 80%
GARRO (kimi-k2.5)  — design spec writer + visual reviewer + confidence scorer
CODER (qwen3×10)   — parallel Swift implementation (1 local + up to 9 OpenRouter)
BUILDER (xcrun)    — writes files, runs swift build, captures simulator screenshot
VERA (Sonnet)      — security audit (P0/P1/P2 issues) before visual review
```

**Loop:** GAHO → GARRO design → CODER (parallel) → BUILDER → VERA → GARRO review → repeat if confidence < 80%

## Scripts

| Script | What it does |
|--------|-------------|
| `parallel-qwen-workflow.py` | Main iOS parallel swarm pipeline |
| `swarm-viz.py` | Live ASCII dashboard — tails swarm log |
| `langgraph-team-audit.py` | Audit pipeline (earlier iteration) |
| `langgraph-ui-sprint/eldrchat_ui_pipeline.py` | First sprint — single-branch pipeline |
| `langgraph-ui-sprint/web_swarm.py` | Web swarm experiment |

## Running

```bash
export ANTHROPIC_API_KEY=...
export OPENROUTER_API_KEY=...

# Run as sub-agent (don't run directly — blocks main session)
python3 parallel-qwen-workflow.py
```

Watch live progress in another terminal:
```bash
python3 swarm-viz.py
```

## Outputs

- `ios-swarm-output/Sources/EldrChat/*.swift` — generated Swift files
- `ios-swarm-TIMESTAMP.log` — full run log
- `ios-swarm-metrics-TIMESTAMP.json` — iteration stats, model usage, confidence scores

## Lessons Learned (First Sprint — 2026-03-24)

| Issue | Fix |
|-------|-----|
| kimi returns prose not JSON | Robust JSON extraction + Sonnet fallback for scoring |
| `KeyManager.swift` failed regex iter 2 | Retry logic via OpenRouter recovered in iter 3 |
| SIGTERM during GARRO review | Increase timeout to 900s; add early fallback |
| OpenRouter timeout 60s too short | Set `OPENROUTER_TIMEOUT = 120` minimum |
| Confidence 72% on iter 1 is normal | Pipeline correctly continues to iter 2 |

## Architecture Reference

- Full team design: `xcode-langgraph-team-setup-v1-2026-03-24.md`
- OpenRouter integration: `langgraph-team-audit/team-openrouter-integration-v1-2026-03-24.md`
- LangGraph pattern: `langgraph-agent-pattern-quick-ref.md`
