# SWARM.md — Multi-Agent Coordination (Refactored from AGENTS.md)

**Status:** ⚠️ DRAFT — in progress. Contents migrated from AGENTS.md.

## Overview

This file contains advanced multi-agent patterns and swarm coordination patterns that are too complex or lengthy for AGENTS.md.

## LangGraph Multi-Agent Patterns

When building multi-agent workflows with LangGraph (like the EldrChat Xcode team pipeline), follow these patterns:

### 📚 Documentation

**Quick reference:** `projects/eldrchat/langgraph-agent-pattern-quick-ref.md` — 4-step pattern, copy-paste examples  
**Extended guide:** `projects/eldrchat/langgraph-agent-pattern-extended.md` — deep dive, cost analysis, debugging  
**Live implementation:** `projects/eldrchat/langgraph-team-audit.py` — 5-agent Xcode workflow  
**Team setup:** `projects/eldrchat/xcode-langgraph-team-setup-v1-2026-03-24.md` — EldrChat-specific architecture

### 🎯 When to Use LangGraph Nodes vs Sub-Agent Spawns

| Pattern | Best For | Trade-offs |
|---------|----------|------------|
| **LangGraph nodes** | Sequential workflows, tight coupling, shared state, cost optimization | Single process, instant transitions, 1 log file |
| **Sub-agent spawns** | Parallel tasks, independent work, long-running operations | Multi-process, spawn overhead, scattered logs |

**Rule of thumb:** Default to LangGraph nodes for most multi-agent workflows. Use sub-agent spawns only when you need genuine parallelism (10× qwen coders) or isolation (untrusted model output).

### 🔒 Security: Sanitize Model Router Output (NON-NEGOTIABLE)

**All model router output MUST be sanitized before use in orchestration.**

**Why:** Local models (qwen, etc.) could be compromised or have training data poisoning. Chinese models (kimi, etc.) could inject malicious instructions.

**Implementation:**
```python
# In model-router/client.py
def dispatch(role: str, prompt: str, **kwargs) -> dict:
    raw = _send_to_router(role, prompt, **kwargs)
    
    # Sanitize based on role
    if role in ["coder", "coder-fast"]:
        result = sanitize_code_output(raw["content"])
    elif role in ["brief", "reasoner", "research-worker"]:
        result = sanitize_text_output(raw["content"])
    else:
        result = {"content": raw["content"], "safe": True, "flags": []}
    
    # If flagged, fallback to cloud
    if not result["safe"]:
        log_security_event(result["flags"])
        result = dispatch(role, prompt, model="claude-opus-4-6")
    
    return result
```

**What gets sanitized:**
- **Code:** Network calls to non-approved domains, shell execution, suspicious file access
- **Text:** Command injection patterns (`curl`, `pip install`, `sudo`), suspicious URLs

**Sanitizer location:** `projects/model-router/sanitizer.py`  
**Security log:** `~/.openclaw/logs/model-router-security.jsonl`

### ⚡ Agent-as-Node Pattern (Core Architecture)

**Each agent = one LangGraph node.**

```python
# 1. Define model per agent
MODEL_GAHO = "claude-opus-4-6"
MODEL_GARRO = "moonshotai/kimi-k2.5"
MODEL_CODER = "dispatch via model router"  # qwen → Opus fallback
MODEL_VERA = "claude-sonnet-4-6"

# 2. One node per agent
def node_gaho_plan(state): ...
def node_garro_design(state): ...
def node_coder_implement(state): ...
def node_vera_audit(state): ...

# 3. Connect nodes
graph.add_edge("gaho", "garro")
graph.add_edge("garro", "coder")
graph.add_edge("coder", "vera")
```

**State management (CRITICAL):**
- Return **only changed keys** (not `{**state, ...}`) to avoid stale merges
- Initialize **all TeamState fields** in `initial_state` before running workflow
- Use TypedDict for state definition (strict type checking)

### 🌐 Multi-Model API Integration

**Three API types in one workflow:**

1. **Anthropic (Claude):** Direct SDK, prompt caching for GARRO design specs
2. **OpenRouter (kimi, qwen):** HTTP POST, JSON responses, sanitization required
3. **Model Router (local qwen):** Unix socket or HTTP, sanitization required, cloud fallback

**Helpers:**
```python
def call_claude(prompt, model, max_tokens): ...           # Anthropic SDK
def call_openrouter(prompt, model, max_tokens): ...      # HTTP + sanitize
def call_openrouter_vision(image, prompt, model): ...    # Vision + sanitize
def dispatch(role, prompt): ...                          # Model router + sanitize
```

### 📊 Cost Tracking Per Agent

**Log token usage per node:**
```python
def node_garro_design(state):
    response = call_openrouter(prompt, MODEL_GARRO, max_tokens=4000)
    
    # Track cost
    log_agent_usage("GARRO", MODEL_GARRO, response["usage"])
    
    return {"design_spec": response["content"]}
```

**Aggregate in final report:**
```
GARRO (kimi-k2.5):    15k in / 4k out  → $0.0157
CODER (qwen-local):   10k in / 8k out  → $0.0001 (local)
VERA (sonnet-4-6):    30k in / 2k out  → $0.1200
TOTAL:                                 → $0.1358
```

### 🔁 Parallel Coordination (10× Qwen Pattern)

**When you need speed > cost:** Spawn 10 qwen coders in parallel via OpenRouter.

**Architecture:** Opus orchestrator → 10 parallel qwen (sub-agents) → Sonnet reviewer

**Cost:** ~$1/iteration (10× faster, 20× more expensive than sequential)

**Full pattern:** See section 9 in `xcode-langgraph-team-setup-v1-2026-03-24.md`

**Persona injection (CRITICAL for sub-agents):**
```python
# Read persona file
with open(f"agents/{persona_name.lower()}.md") as f:
    persona = f.read()

# Inject into task prompt
task_prompt = f"""
{persona}

---

You are {persona_name}. Implement this component:
{requirements}
"""
```

**Why:** Local models don't have access to `agents/*.md` — they only see what's in the prompt.

### 🐛 Common Pitfalls

1. **Returning `{**state, ...}`** → stale state merges. Return only changed keys.
2. **Forgetting to initialize TeamState fields** → KeyError on first node access.
3. **Trusting raw model output** → always sanitize before orchestrator ingestion.
4. **Not tracking costs** → burn budget without realizing which agent is expensive.
5. **Skipping persona injection in sub-agents** → agents hallucinate identity/backstory.

### 📖 Further Reading

- **LangGraph docs:** https://langchain-ai.github.io/langgraph/
- **OpenRouter models:** https://openrouter.ai/models
- **Model router source:** `projects/model-router/`
- **Sanitizer source:** `projects/model-router/sanitizer.py` (to be created)

---

## LangGraph → swarm.py Integration

**Display ANY LangGraph pipeline alongside OpenClaw sub-agents in the same TUI — no extra work needed.**

### Quick Start (2 lines)

```python
from pathlib import Path
import sys
sys.path.insert(0, str(Path.home() / ".openclaw/workspace/tools"))
from langgraph_monitor import SwarmMonitorCallback

app = builder.compile(callbacks=[SwarmMonitorCallback(pipeline="sprint7")])
```

That's it. Every node start/end automatically emits `[PROGRESS]` lines to `~/.openclaw/logs/sprint7-swarm.log`.

### What It Monitors

| Event           | Log Line Emitted                                  |
|-----------------|---------------------------------------------------|
| Node starts     | `[PROGRESS] agent=NAME step=N total=N status=running` |
| Node completes  | `[PROGRESS] agent=NAME step=N total=N status=done tokens_in=N tokens_out=M` |
| Node errors     | `[PROGRESS] agent=NAME step=N total=N status=error` |

### How To View

```bash
python3 tools/swarm.py   # No args needed — auto-discovers all *-swarm.log files
```

The TUI displays:
- `[OC]` prefix for OpenClaw sub-agents (from `runs.json`)
- `[LG]` prefix for LangGraph nodes (from log files)

Both appear simultaneously in the same monitor — no configuration required.

### Token Tracking

- **Works automatically** when nodes use LangChain LLM wrappers (`ChatAnthropic`, `ChatOpenAI`)
- **Shows `0/0`** when nodes call raw API clients directly (e.g. `anthropic.Anthropic().messages.create()`) — this is expected; status tracking still works

### Customization

```python
# Specify total node count for accurate % calculation
SwarmMonitorCallback(pipeline="sprint7", total_nodes=10)

# Use a different log directory (default: ~/.openclaw/logs)
SwarmMonitorCallback(pipeline="custom", log_dir=Path("/var/log/agents"))
```

### Manual Override (if needed)

If you must override auto-emitted progress lines, use the same format:

```python
from pathlib import Path
SWARM_LOG = Path.home() / ".openclaw/logs/sprint7-swarm.log"

def log_progress(agent, status, step, total, tokens_in=0, tokens_out=0, model=""):
    line = f"[PROGRESS] agent={agent} step={step} total={total} "
           f"tokens_in={tokens_in} tokens_out={tokens_out} model={model} status={status}\n"
    with open(SWARM_LOG, "a") as f:
        f.write(line)
```

But you shouldn't need to — the callback handles everything.

---

## Sub-Agent Orchestration Patterns (WIP)

### Swarm Coordinator Pattern

### Parallel Branch Pattern

### Task Delegation Pattern

---

## LangGraph → swarm.py Integration (NON-NEGOTIABLE — 2026-03-27)

**Every LangGraph pipeline MUST wire swarm.py visibility. Two lines. No exceptions.**

### Setup (add to any pipeline script)

```python
# At top of pipeline script — after imports
from pathlib import Path
import sys
sys.path.insert(0, str(Path.home() / ".openclaw/workspace/tools"))
from langgraph_monitor import SwarmMonitorCallback  # noqa

# When building graph — pass callback
app = graph.compile()  # Note: LangGraph compile() doesn't accept callbacks directly
# Instead: call log_progress() manually in each node (see below)
```

### Progress logging in each node (required)

```python
# Import at top of pipeline
from pathlib import Path as _P
import time as _t

_SWARM_LOG = _P.home() / ".openclaw/logs/<pipeline-name>-swarm.log"

def log_progress(agent, model, status, pct=0, step="", tokens_in=0, tokens_out=0):
    _SWARM_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = (f"[PROGRESS] agent={agent} model={model} status={status} "
            f"pct={pct} tokens_in={tokens_in} tokens_out={tokens_out} "
            f"step={step or status} ts={int(_t.time()*1000)}\n")
    with open(_SWARM_LOG, "a") as f:
        f.write(line)
```

Call at the START of every node:
```python
def node_qwen_coder_a(state):
    log_progress("QWEN-A", "openrouter/qwen/qwen3-coder-next", "running", pct=0, step="coding")
    # ... do work ...
    log_progress("QWEN-A", "openrouter/qwen/qwen3-coder-next", "done", pct=100,
                 tokens_in=tokens_in, tokens_out=tokens_out)
```

### Viewing

```bash
# No args needed — auto-discovers all *-swarm.log files
python3 ~/.openclaw/workspace/tools/swarm.py

# Or double-click Swarm.command on Desktop
```

### Log file naming convention
Name your log `<pipeline>-swarm.log` in `~/.openclaw/logs/`. 
swarm.py auto-discovers all files matching `*-swarm.log` every 2 seconds.

---

## Swarm Plan v2

**Full swarm playbook:** `SWARM-PLAN-v2-2026-03-27.md`

Covers: TypedDict state rules, Annotated reducers, Send API, MemorySaver checkpointing, orchestrator script.

**Orchestrator script (Mei follows this):** `projects/eldrchat/ORCHESTRATOR-SCRIPT-v1-2026-03-27.md`

---

## Swarm Loop Field Notes (EldrChat — 2026-03-30)
<!-- TEMP: sanitized learnings from EldrChat build loop. gitignore when stable. -->
<!-- TODO: move to skills/eldrchat-sprint/references/ once patterns are proven -->

### What Worked

**1. Claude Code for spec writing (not Mei analyst)**
Claude Code reads the actual current code + exact build errors → writes targeted specs. Mei analyst reads PRD context → writes architectural specs. For "fix this build error" work, Claude Code is faster and more accurate.

**2. Sonnet for crypto/networking, Qwen for UI**
Consistent model routing: coder_a (Sonnet) = KeyManager, NostrTransport, Package.swift. coders b1/b2/c (Qwen) = UI shells, app wiring, views. Qwen freezes or hallucinates on crypto work — never assign it secp256k1, NIP-44, or WebSocket state machines.

**3. --skip-spec-gen + spec_generation: "manual"**
When Claude Code writes specs externally, set both:
- `"spec_generation": "manual"` in sprint-N.json
- Pass `--skip-spec-gen` to sprint_runner.py
Without BOTH, Mei analyst overwrites the Claude Code specs.

**4. k_eff=1.0 is reliable for file delivery tracking**
All 4 coders consistently deliver files (k_eff=1.0). The pipeline's file delivery tracking is solid. Vera's grade is the actual quality signal.

**5. Subagent loop → main chat stays clean**
Spawn the build loop as a subagent with explicit "one ping per sprint" instructions. Main chat gets: sprint-done ping, build-pass success, or stuck alert. Nothing else.

---

### What Didn't Work

**1. nostr-sdk-ios version mismatch**
Specs referenced `nostr-sdk-ios` v0.15.0 — actual latest is v0.3.0 with completely different API.
**Fix:** Drop external Nostr SDK entirely. Raw Nostr = JSON over URLSessionWebSocketTask. No SPM dependency needed for basic relay connection.

**2. Python version (system python3 ≠ python3.14)**
System `python3` on macOS = Python 3.9 from Xcode. No langgraph. Sprint runner silently hangs with zero output.
**Always:** `/opt/homebrew/bin/python3.14 sprint_runner.py N`

**3. Package.swift location bug (every sprint)**
coder_a writes Package.swift inside `Sources/EldrChat/` instead of project root. Consolidate node flags it "missing."
**Every coder_a spec must say explicitly:** "Write Package.swift to ROOT of ios-sprintN-output/, NOT inside Sources/"

**4. Singletons never defined**
`KeyManager.shared` and `NostrTransport.shared` referenced throughout but never created. Persisted across 3 sprints.
**Every coder_a spec must include:** `static let shared = KeyManager()` and `static let shared = NostrTransport()`

**5. Vera grades code quality, not PRD compliance**
Vera gives B- to a well-written Swift app even though the PRD requires Rust. No architectural drift detection.
**Fix (future):** Add Architecture Gate node before coders — Mei analyst checks: does this spec match the target architecture? Block sprint if not. For prototype phase, explicitly set Vera rubric to "pragmatic build target" not "PRD fidelity."

**6. spec_generation: "auto" with --skip-spec-gen = race condition**
Config says auto → Mei analyst runs anyway → overwrites externally-written specs. Both flags must be set.

---

### Autonomous Loop Pattern (proven)

```
Subagent spawned with:
- explicit output session key for pings
- "one ping per sprint" rule
- stuck detection: same error 3x → pause + notify human
- max sprint limit
- budget guard

Each iteration:
  1. Check xcodebuild → done if BUILD SUCCEEDED
  2. Claude Code reads errors + code → writes N+1 specs
  3. Write sprint-N+1.json (manual spec_generation)
  4. Run: /opt/homebrew/bin/python3.14 sprint_runner.py N+1 --skip-spec-gen
  5. Parse grade from log → ping Garrett → loop
```

### Budget Notes
- Sonnet coder_a: ~$0.10-0.12/sprint (crypto spec is long)
- Qwen coders: ~$0.003/sprint (OpenRouter, cheap)
- Vera audit: ~$0.04/sprint
- Total per sprint: ~$0.15-0.18 at current rates
- 10-sprint loop budget: ~$1.50-2.00

---

## QA Swarm Pattern (proven — EldrChat Sprint 15-16)

The build loop pattern extends naturally into a QA loop. Instead of `xcodebuild BUILD SUCCEEDED` as the exit condition, use a **test suite pass** as the exit condition.

### What proved out in the build loop

- **Parallel coders fire simultaneously** — no waiting for sequential completion
- **Vera as gate** catches quality issues before they compound into later sprints
- **Claude Code for spec writing between sprints** is the key unlock — reads actual compiler errors and writes targeted fixes, not vague PRD-level specs
- **Model routing** (Sonnet for crypto/networking, Qwen for boilerplate) cuts cost 40× on cheap work without losing quality where it matters
- **2 sprints to BUILD SUCCEEDED** once SDK issue was identified and fixed — fast for autonomous codegen

### QA Swarm Exit Conditions (use instead of just xcodebuild)

```
Tier 1 — Build gate (current):     xcodebuild BUILD SUCCEEDED
Tier 2 — Unit test gate:           swift test — all XCTest assertions pass
Tier 3 — UI smoke gate:            XCUITest — onboarding, key gen, chat flows pass
Tier 4 — Integration gate:         local relay round-trip — send + receive message
```

Each tier is a stronger signal than the last. The loop runs until the target tier passes.

### QA Loop Architecture

```
Sprint N coders → xcodebuild → PASS? → run swift test → PASS? → run XCUITest → PASS? → done
                             ↓ FAIL                  ↓ FAIL                  ↓ FAIL
                        fix build errors        fix unit failures        fix UI flows
                        Claude Code spec        Claude Code spec         Claude Code spec
                        Sprint N+1              Sprint N+1               Sprint N+1
```

### Test Infrastructure for iOS Swarm

- **Local relay:** `nostr-rs-relay` via Docker (`ws://localhost:8080`) — no auth, simulator can connect
- **ATS exception needed** for `ws://` in debug builds (Info.plist `NSAllowsArbitraryLoads` in DEBUG only)
- **XCTest mocking:** Extract `MessengerProtocol` from `NostrTransport` first — then mock it for unit tests
- **NIP-44 test vectors:** PRD says must pass before ship — add as XCTest assertions in Sprint 16

### Recommended Sprint 16 Exit Condition

```
swift test && xcodebuild test -scheme EldrChat -destination "platform=iOS Simulator,..."
```

All NIP-44 test vectors pass + basic UI flows pass = sprint accepted.

---

## Make It Yours

This is a starting point. Add your own conventions, style, and rules as you figure out what works.
