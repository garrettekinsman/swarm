---
name: eldrchat-sprint
description: Run EldrChat iOS coding sprints via the k_eff LangGraph pipeline. Use when Garrett asks to run a sprint, start Sprint N, kick off EldrChat coding, or test the swarm. Triggers on: "run Sprint 12", "kick off next sprint", "start EldrChat sprint", "run the sprint". Produces Swift source files in ios-sprint-N-output/. Requires only sprints/sprint-N.json — analyst generates specs automatically from PRD + handoff.
---

# EldrChat Sprint Runner

## ⚠️ Temporary: Claude Code for spec writing
Using `claude --permission-mode bypassPermissions --print` to analyze build errors and write specs is a workaround — it's clunky but functional until Apple formally supports Claude (Xcode integration / MCP). When that lands, replace this step with a native Xcode-aware agent.
See: SWARM.md → "QA Swarm Pattern" for the intended final architecture.

## Quick start

```bash
cd ~/.openclaw/workspace/projects/eldrchat
# ⚠️ ALWAYS use python3.14 — system python3 (3.9) has no langgraph and silently hangs
/opt/homebrew/bin/python3.14 -u sprint_runner.py <N>   # e.g. sprint 16
# With manually-written specs (Claude Code wrote them):
/opt/homebrew/bin/python3.14 -u sprint_runner.py <N> --skip-spec-gen
```

Watch live:
```bash
python3 ~/.openclaw/workspace/tools/swarm.py
```

## ⚠️ MANDATORY: Send progress updates every 5 minutes

While a sprint is running, you MUST send a Discord DM to Garrett every 5 minutes:

```python
sessions_send(
    sessionKey="agent:gaho:direct:<YOUR_SESSION_KEY>",
    message="[Sprint N] 🔄 X min elapsed — <what's happening: analyst done, coder A running, Vera auditing, etc.>"
)
```

Do this at each major phase transition AND every 5 minutes of silence. Garrett should never have to ask "what's happening." If you're waiting on an LLM call, say so. Format:

```
[Sprint 12] ✅ Analyst done — specs generated (A: 12k chars, B1: 6k, B2: 5k, C: 8k)
[Sprint 12] 🔄 3 coders running in parallel — A(Sonnet), B1(qwen), C(qwen)
[Sprint 12] ⚠️ coder_b1 silent 90s — watchdog flagged, monitoring
[Sprint 12] ✅ Coders done — 7/8 files written. Vera auditing...
[Sprint 12] 🏁 Complete — k_eff=0.875, Grade B+. EldrChatApp.swift ✅ finally written.
```

## Before running a new sprint

1. Create sprint config: `sprints/sprint-N.json` — set `"spec_generation": "manual"` if Claude Code wrote specs
2. If auto-generating specs: just run — analyst reads PRD + handoff automatically
3. If using Claude Code specs: run with `--skip-spec-gen` AND set `spec_generation: manual` in config (BOTH required)

### Model routing (NON-NEGOTIABLE)
- `coder_a` → **Sonnet** — crypto, networking, singletons, Package.swift
- `coder_b1/b2/c` → **Qwen** — UI boilerplate, app shell, views
- Never assign secp256k1 / NIP-44 / WebSocket state machines to Qwen

### Package.swift location (every sprint — every coder_a spec must say this)
Write Package.swift to ROOT of `ios-sprintN-output/`, NOT inside `Sources/`

### Crypto (NON-NEGOTIABLE)
Read `CRYPTO-CONSTRAINTS.md` before writing any spec touching KeyManager.
- secp256k1 → GigaBitcoin (`https://github.com/21-DOT-DEV/swift-secp256k1`)
- Never hand-roll secp256k1. Vera auto-fails any sprint that does.

### Spec requirements (gate will reject if missing)
- Each spec ≥ 5000 chars
- Must have `## Acceptance Criteria` section
- coder_a spec must include static singleton definitions

See `references/config-schema.md` for full config structure and model routing rules.

## Output

- Swift files: `ios-sprint-N-output/Sources/EldrChat/`
- Package: `ios-sprint-N-output/Package.swift` (root)
- Tests: `ios-sprint-N-output/Tests/EldrChatTests/`
- Handoff: `sprint-N-handoff.md`
- Generated specs: `sprints/specs/sprint-N-spec-{a,b,c}.md` (written by analyst, reviewable)

## Scoring (k_eff_v3)

`k_eff = (files_written/8) × (vera_score/100)` — Target: ≥ 0.70

## Observability

### Start swarm preview (live agent monitor)
```bash
python3 ~/.openclaw/workspace/tools/swarm.py
```
Auto-discovers sprint log files. Shows Gaho + watchdog pinned at top, sprint agents below.

### Install watchdog (one-time)
The watchdog monitors for frozen agents and auto-restarts the swarm monitor.
```bash
# Check if already installed
launchctl list | grep keff-watchdog

# Install (if not running)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.keff-watchdog.plist

# Verify
launchctl list | grep keff-watchdog   # should show PID + exit code 0
tail -5 ~/.openclaw/logs/keff-watchdog.log
```

### What the watchdog does
- Restarts swarm.py if it dies ✅ confirmed working
- Detects coder silence: warn (90s) → steer (120s) → kill + re-dispatch (180s)
  - Level 1 warn: ✅ firing correctly
  - Level 2 steer (openclaw agent --session-id): ⚠️ not yet battle-tested on live stuck agent
  - Level 3 kill (ssh pkill qwen): ⚠️ not yet triggered (sprints complete before hitting 3min)
- Logs all interventions to `projects/keff/memory/supervisor-log.jsonl`
- Pings you on Discord on Level 2+ interventions

### 5-minute heartbeat
Sprint runner sends a Discord DM every 5 minutes with current progress from the swarm log.
This is ON by default. Check your DMs during a sprint for live updates.

### Debug heartbeat (on by default during sprints)
Every 10 minutes while a sprint runs, you get a Discord DM with progress.
To disable: `SPRINT_DEBUG=0 python3 sprint_runner.py N`
To change interval: `SPRINT_DEBUG_INTERVAL=300 python3 sprint_runner.py N`

## Troubleshooting

### Swarm shows no agents
- Sprint log may not exist yet — start swarm AFTER sprint begins
- Or: `python3 swarm.py ~/.openclaw/logs/sprint-N-swarm.log` (explicit path)

### Agent froze / no progress
- Watchdog handles this automatically (180s kill timeout)
- Check: `tail -f ~/.openclaw/logs/keff-watchdog.log`
- Manual kill: `kill $(cat /tmp/sprint-N.pid)`

### Spec gate rejection
- Means analyst-generated spec was too short or missing AC section
- Rarely happens with dynamic generation — analyst re-runs automatically
- If persistent: check PRD + handoff are readable by analyst

### Sprint ran but wrong output dir
- Check `sprints/sprint-N.json` output_dir field
- Previous sprint outputs are in `ios-sprint{N-1}-output/`

## Autonomous Build Loop

When Garrett says "run until it builds" or "keep going until tests pass" — spawn a subagent with `sprint_loop.py`:

```bash
# Runs sprints autonomously until xcodebuild passes. One ping per sprint to Garrett's DMs.
cd ~/.openclaw/workspace/projects/eldrchat
/opt/homebrew/bin/python3.14 sprint_loop.py --start-sprint <N> --max-sprints 8
```

Loop behavior:
- Each iteration: Claude Code reads build errors → writes N+1 specs → runs sprint → checks build
- Stuck detection: same error 3× in a row → pauses + notifies Garrett
- Budget guard: ~$0.15-0.18/sprint, ~$1.50 for 10 sprints
- Exit: `xcodebuild BUILD SUCCEEDED` → delivers project path to Garrett's DMs

**Always spawn as subagent** — never run loop in main session.

## QA Exit Conditions (Sprint 16+)

Use test suite pass as exit condition instead of just xcodebuild:

```bash
# Tier 1: build
xcodebuild build -scheme EldrChat -destination "platform=iOS Simulator,name=iPad Pro 13-inch (M4)"

# Tier 2: unit tests  
/opt/homebrew/bin/python3.14 -m pytest   # or: swift test

# Tier 3: integration (requires local relay running)
docker run -d -p 8080:8080 scsibug/nostr-rs-relay  # start local relay
# then run XCUITest suite
```

NIP-44 test vectors must pass before any sprint is accepted as final (PRD requirement).

## See also

- `sprints/specs/` — per-sprint coder specs (auto-generated by analyst)
- `CRYPTO-CONSTRAINTS.md` — secp256k1 rules (read before any sprint touching KeyManager)
- `SWARM.md` → "Swarm Loop Field Notes" — full lessons learned
- `SWARM.md` → "QA Swarm Pattern" — build→test→integration loop architecture
- `memory/projects/eldr-swarm-loop.md` — EldrChat-specific sprint history + decisions
- `SWARM-ARCHITECTURE-v2-2026-03-27.md` — pipeline architecture
- `ELDRCHAT-TEST-SPEC-v1-2026-03-27.md` — PRD test requirements
