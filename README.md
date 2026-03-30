# Swarm Skills

Autonomous AI agent swarm patterns for OpenClaw. Each directory is a specialized swarm type.

## Swarms

| Directory | Purpose |
|-----------|---------|
| `xcode-swarm/` | Autonomous iOS/Swift build loop — parallel Sonnet+Qwen coders until `xcodebuild` passes |
| `pbar/` | Population-Based Annealed Research — parallel branches with softmax selection + temperature annealing |

## Common Patterns

All swarms share:
- **LangGraph StateGraph** — enforced node execution, nodes cannot be skipped
- **Model routing** — Sonnet for complex reasoning/crypto, Qwen for boilerplate (40× cheaper)
- **Heartbeat pings** to Discord after each major step
- **Stuck detection** — same error 3× → pause + notify human
- **Sub-agent isolation** — never run swarm loops in main session
- **API timeout resilience** — explicit `httpx.Timeout` + retry on Anthropic overload

## Adding a New Swarm

Copy `xcode-swarm/` as a template. Replace:
1. `SKILL.md` — swap Swift/Xcode references for your language/build system
2. `SWARM-PATTERNS.md` — add your domain-specific lessons
3. Build check command (`xcodebuild` → your equivalent)

## License

MIT
