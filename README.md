# Swarm Skills

Autonomous AI agent swarm patterns for OpenClaw. Each directory is a specialized swarm type.

## Swarms

- **xcode-swarm/** — Autonomous iOS/Swift build loop. Runs parallel Sonnet+Qwen coders until xcodebuild passes.
- **pbar/** — Population-Based Annealed Research. Parallel research branches with softmax selection and temperature annealing.
- **eldr-swarm/** — EldrChat-specific sprint tooling.

## Common Patterns

All swarms share:
- LangGraph StateGraph for enforced node execution (nodes cannot be skipped)
- Sonnet for complex reasoning, Qwen for boilerplate (40x cheaper)
- Heartbeat pings to Discord after each major step
- Stuck detection: same error 3x → pause + notify human
- Sub-agent isolation: never run swarm loops in main session
