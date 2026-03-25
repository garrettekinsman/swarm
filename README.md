# eldr-swarm

LangGraph multi-agent swarm for EldrChat iOS development.

Parallel agent pipeline that generates Swift source files via coordinated AI branches, with live visualization tooling.

## Structure

| File | Purpose |
|------|---------|
| `swarm-viz.py` | TTY + browser-based swarm visualizer |
| `swarm-viz-server-arch.md` | Architecture doc for the viz server |
| `parallel-qwen-workflow.py` | Parallel qwen branch runner |
| `langgraph-agent-pattern-*.md` | LangGraph team patterns (quick ref + extended) |
| `langgraph-team-audit.py` | Audit script for agent team runs |
| `openrouter-integration.md` | OpenRouter setup + model routing notes |
| `xcode-langgraph-team-setup-*.md` | Xcode + LangGraph team wiring |
| `ios-swarm-output/` | Generated Swift source files |

## Swarm Viz

```bash
# TTY mode (watch a single active swarm)
python3 swarm-viz.py

# Browser mode (all active swarms, SSE live updates)
python3 swarm-viz.py --serve 8888
# → open http://<tailscale-ip>:8888
```

## Status

- Sprint 1 complete — 10/10 Swift files generated
- Vera security findings: 3 criticals flagged (ChatView sanitization, npub validation, KeyManager consistency)
- GARRO JSON parsing needs fix (kimi returns prose, not JSON)
