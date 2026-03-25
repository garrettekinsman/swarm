---
*Prepared by **Agent: Mei (梅)** — PhD candidate, Tsinghua KEG Lab. Specialist in Chinese AI ecosystem, inference optimization, and MoE architectures.*
*Running: anthropic/claude-sonnet-4-5*

*Human in the Loop: Garrett Kinsman*

---

# Xcode LangGraph Team Setup v1-2026-03-24

## Overview

EldrChat's native iOS/macOS development uses a **5-agent LangGraph team pipeline** to iteratively build and refine SwiftUI views. This document describes the team structure, model selection, cost implications, and how OpenRouter integration fits into the workflow.

---

## ⚠️ Orchestration Rule (NON-NEGOTIABLE — burned in 2026-03-24)

**Gaho never runs the pipeline loop directly. Gaho always spawns an Opus orchestrator sub-agent.**

```
WRONG:  exec(command="python3 web_swarm.py")       ← locks main chat for 10+ min
RIGHT:  sessions_spawn(task="...", model="claude-opus-4-6") → sessions_yield()
```

- **Gaho's role:** dispatch only — read the task, spawn the orchestrator, yield
- **Orchestrator sub-agent's role:** run the LangGraph graph, monitor progress, report completion
- **Why:** Running inference loops in main session blocks all other messages and violates main session hygiene
- **Framework1 constraint:** One inference at a time — orchestrator must route heavy tasks to cloud, light tasks to local. Inject `FRAMEWORK1_CONSTRAINT` into every orchestrator prompt (see `FRAMEWORK1-ORCHESTRATOR-CONSTRAINT.md`)

---

## 1. Team Structure

### 1.1 Agent Roles

```
┌─────────────────────────────────────────────────────────────────┐
│  5-AGENT LANGGRAPH TEAM PIPELINE                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [1] GAHO (Orchestrator)                                        │
│      ├─ Model: Claude Opus 4-6 (cloud)                          │
│      ├─ Role: Plans iterations, decides when to stop            │
│      └─ State: Reviews confidence score from GARRO              │
│                                                                 │
│  [2] GARRO (Design)                                             │
│      ├─ Model: Claude Opus 4-6 (cloud)                          │
│      ├─ Role: Creates SwiftUI design specs from web UI ref      │
│      └─ Output: Detailed color palette, layout, components      │
│                                                                 │
│  [3] CODER (Implementation)                                     │
│      ├─ Model: qwen3-coder-next (local/OpenRouter/cloud)        │
│      ├─ Role: Implements SwiftUI views from GARRO's spec        │
│      ├─ Fallback: Local → OpenRouter → Opus (3-tier)           │
│      └─ Output: 5 Swift files (ContentView, ContactList, etc.)  │
│                                                                 │
│  [4] BUILDER (Build & Screenshot)                               │
│      ├─ Tool: swift build + xcrun simctl                        │
│      ├─ Role: Writes files, builds, captures simulator screenshot│
│      └─ Output: PNG screenshot (720×480, compressed)            │
│                                                                 │
│  [5] VERA (Security Audit)                                      │
│      ├─ Model: Claude Sonnet 4-6 (cloud)                        │
│      ├─ Role: Audits code for security/architecture issues      │
│      └─ Output: P0/P1/P2 issue list                             │
│                                                                 │
│  [6] GARRO (Review)                                             │
│      ├─ Model: Claude Opus 4-6 with vision (cloud)              │
│      ├─ Role: Reviews screenshot vs design spec                 │
│      ├─ Input: Screenshot, design spec, Vera's audit            │
│      └─ Output: Confidence score (0-100), issue list            │
│                                                                 │
│  Loop: If confidence < 80% and iteration < 5, repeat            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Workflow

1. **GAHO plans** — Reviews previous iteration, decides iterate or done
2. **GARRO designs** — Creates SwiftUI spec matching web UI reference
3. **CODER implements** — Generates 5 Swift files from spec
4. **BUILDER writes & builds** — Writes files to disk, runs `swift build`, screenshots simulator
5. **VERA audits** — Security/architecture review
6. **GARRO reviews** — Compares screenshot to spec, assigns confidence score
7. **Loop** until confidence ≥ 80% or max 5 iterations

---

## 2. LangGraph Direct Agent Deployment (Architecture Pattern)

### 2.1 Why Deploy Agents as LangGraph Nodes

**Traditional sub-agent spawning:**
```python
# Spawn a sub-agent for each task
garro_session = sessions_spawn(agentId="garro", task="Design UI")
coder_session = sessions_spawn(agentId="coder", task="Implement")
# Wait for results, parse messages, route to next agent...
```

**Problems:**
- Multiple processes → message passing overhead
- Session spawn latency (~1-2s per agent)
- Scattered logs across sub-agent sessions
- Complex orchestration (polling, parsing, error handling)
- Hard to track state flow between agents

**LangGraph node deployment:**
```python
# Each agent = one node in a single workflow
MODEL_GAHO = "claude-opus-4-6"
MODEL_GARRO = "moonshotai/kimi-k2.5"
MODEL_CODER = "dispatch via model router"

def node_gaho_plan(state): ...
def node_garro_design(state): ...
def node_coder_implement(state): ...

graph.add_edge("gaho", "garro")
graph.add_edge("garro", "coder")
```

**Benefits:**
- ✅ Single process, shared state dictionary
- ✅ Instant node transitions (no spawn overhead)
- ✅ Direct model assignment per agent
- ✅ One unified log file
- ✅ Built-in state persistence and checkpointing
- ✅ Easy to swap models (change constant + API call)

---

### 2.2 Agent-as-Node Implementation Pattern

**Step 1: Define model constants**
```python
# Model assignments (single source of truth)
MODEL_GAHO = "claude-opus-4-6"          # Orchestrator
MODEL_GARRO = "moonshotai/kimi-k2.5"    # Designer (via OpenRouter)
MODEL_CODER = "coder"                   # Model router role
MODEL_VERA = "claude-sonnet-4-6"        # Auditor
```

**Step 2: Create node functions**
```python
def node_garro_design(state: TeamState) -> dict:
    """GARRO agent node — design SwiftUI spec from web UI reference."""
    print("🎨 GARRO: Designing SwiftUI spec...")
    
    # Build prompt from state
    prompt = f"""
    You are GARRO, a SwiftUI design specialist.
    
    Task: Create a detailed SwiftUI spec matching this web UI:
    {state["web_ui_reference"]}
    
    Previous issues: {state["issues"]}
    """
    
    # Call model (OpenRouter for GARRO)
    response = call_openrouter(
        system="You are GARRO, SwiftUI design expert.",
        user=prompt,
        model=MODEL_GARRO,
        max_tokens=4000
    )
    
    # Return only changed state keys (LangGraph merge pattern)
    return {
        "design_spec": response,
        "garro_tokens_used": len(response.split())
    }
```

**Step 3: Add edges**
```python
from langgraph.graph import StateGraph

graph = StateGraph(TeamState)

# Add nodes
graph.add_node("gaho", node_gaho_plan)
graph.add_node("garro_design", node_garro_design)
graph.add_node("coder", node_coder_implement)
graph.add_node("builder", node_builder_build)
graph.add_node("vera", node_vera_audit)
graph.add_node("garro_review", node_garro_review)
graph.add_node("final", node_final_report)

# Define workflow
graph.set_entry_point("gaho")
graph.add_edge("gaho", "garro_design")
graph.add_edge("garro_design", "coder")
graph.add_edge("coder", "builder")
graph.add_edge("builder", "vera")
graph.add_edge("vera", "garro_review")
graph.add_conditional_edges(
    "garro_review",
    should_continue,  # Check confidence score
    {
        "continue": "gaho",  # Loop back
        "end": "final"       # Done
    }
)
graph.add_edge("final", END)

app = graph.compile()
```

**Step 4: Run the workflow**
```python
initial_state = {
    "iteration": 0,
    "confidence_score": 0,
    "web_ui_reference": load_reference_doc(),
    "issues": [],
    "design_spec": "",
    "current_code": {},
    # ... other fields
}

final_state = app.invoke(initial_state)
print(f"✅ Pipeline complete: {final_state['confidence_score']}% confidence")
```

---

### 2.3 State Management Best Practices

**TeamState definition:**
```python
from typing import TypedDict, List, Dict

class TeamState(TypedDict):
    # Iteration tracking
    iteration: int
    confidence_score: int
    
    # Input data
    web_ui_reference: str
    
    # Agent outputs
    design_spec: str           # GARRO output
    current_code: Dict[str, str]  # CODER output {filename: content}
    audit_issues: List[str]    # VERA output
    review_feedback: str       # GARRO review output
    
    # Metadata
    issues: List[str]          # All issues across iterations
    build_success: bool
    screenshot_path: str
    
    # Model tracking
    coder_model_used: str
    coder_fallback: bool
    coder_fallback_events: List[str]
```

**Critical rules:**

1. **Return only changed keys** (not full state):
   ```python
   # ❌ WRONG — causes stale merge issues
   def node_example(state):
       return {**state, "new_field": "value"}
   
   # ✅ CORRECT — LangGraph merges automatically
   def node_example(state):
       return {"new_field": "value"}
   ```

2. **Access state as dict, not object**:
   ```python
   # ✅ CORRECT
   design_spec = state["design_spec"]
   
   # ❌ WRONG
   design_spec = state.design_spec
   ```

3. **Initialize all fields in initial state**:
   ```python
   # Every field in TeamState must exist at start
   initial_state = {
       "iteration": 0,
       "confidence_score": 0,
       "design_spec": "",  # ← Don't skip this
       # ...
   }
   ```

---

### 2.4 Multi-Model API Integration

**OpenRouter helper:**
```python
def call_openrouter(system: str, user: str, model: str, max_tokens: int = 2048) -> str:
    from openai import OpenAI
    import os
    
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1"
    )
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        max_tokens=max_tokens
    )
    
    return response.choices[0].message.content
```

**Model router helper:**
```python
def call_model_router(role: str, prompt: str, timeout: int = 180) -> str:
    import subprocess, json
    
    result = subprocess.run(
        ["bash", "projects/model-router/scripts/dispatch.sh",
         "--role", role, "--prompt", prompt],
        capture_output=True,
        text=True,
        timeout=timeout
    )
    
    return result.stdout.strip()
```

**Anthropic helper:**
```python
def call_claude(prompt: str, model: str, max_tokens: int = 2048) -> str:
    from anthropic import Anthropic
    import os
    
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.content[0].text
```

**Vision helper (for screenshot analysis):**
```python
def call_openrouter_vision(system: str, user: str, image_path: str, model: str) -> str:
    import base64
    from openai import OpenAI
    import os
    
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1"
    )
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                    }
                ]
            }
        ],
        max_tokens=4096
    )
    
    return response.choices[0].message.content
```

---

### 2.5 When to Use LangGraph Nodes vs Sub-Agent Spawns

| Use Case | LangGraph Nodes | Sub-Agent Spawns |
|----------|-----------------|------------------|
| **Tight collaboration** (agents pass state sequentially) | ✅ Perfect fit | ❌ Too much overhead |
| **Parallel independence** (agents work on separate tasks) | ⚠️ Possible with parallel edges | ✅ Better isolation |
| **Long-running tasks** (>5 min per agent) | ⚠️ Blocks workflow | ✅ Background execution |
| **Different runtimes** (ACP harness vs cloud) | ❌ Can't mix runtimes | ✅ Each spawn picks runtime |
| **Shared state** (agents read/write common data) | ✅ Built-in state dict | ❌ Need message passing |
| **Cost tracking** (per-agent model usage) | ✅ Easy (all in one process) | ⚠️ Harder (scattered logs) |
| **Debugging** (trace execution flow) | ✅ Single log file | ❌ Multiple session logs |

**Rule of thumb:**
- **Sequential workflow with shared state?** → LangGraph nodes
- **Independent parallel tasks?** → Sub-agent spawns
- **Mix of both?** → LangGraph for tight steps, spawn for long/parallel work

---

### 2.6 Adding a New Agent to the Team

**Example: Add a new "TESTER" agent that validates Swift syntax**

**Step 1: Define model**
```python
MODEL_TESTER = "claude-haiku-4-2"  # Fast, cheap, good enough for syntax checks
```

**Step 2: Create node function**
```python
def node_tester_validate(state: TeamState) -> dict:
    """TESTER agent node — validate Swift syntax."""
    print("🧪 TESTER: Validating Swift syntax...")
    
    issues = []
    for filename, code in state["current_code"].items():
        # Try to compile (dry-run)
        result = subprocess.run(
            ["swiftc", "-parse", "-"],
            input=code,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            issues.append(f"{filename}: {result.stderr}")
    
    return {
        "syntax_issues": issues,
        "syntax_valid": len(issues) == 0
    }
```

**Step 3: Update TeamState**
```python
class TeamState(TypedDict):
    # ... existing fields
    syntax_issues: List[str]
    syntax_valid: bool
```

**Step 4: Add to graph**
```python
graph.add_node("tester", node_tester_validate)
graph.add_edge("coder", "tester")  # Insert after coder
graph.add_edge("tester", "builder")  # Before builder
```

**Step 5: Initialize in initial_state**
```python
initial_state = {
    # ... existing fields
    "syntax_issues": [],
    "syntax_valid": False
}
```

**Done.** TESTER is now part of the pipeline, runs after CODER, blocks invalid code from reaching BUILDER.

---

### 2.7 Cost Tracking Per Agent

**In each node, track usage:**
```python
def node_garro_design(state: TeamState) -> dict:
    response = call_openrouter(...)
    
    tokens_in = len(prompt.split())  # Rough estimate
    tokens_out = len(response.split())
    
    # Append to usage log
    usage = state.get("usage", [])
    usage.append({
        "agent": "GARRO",
        "model": MODEL_GARRO,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": (tokens_in * 0.00000045) + (tokens_out * 0.0000022)  # kimi pricing
    })
    
    return {
        "design_spec": response,
        "usage": usage
    }
```

**At the end, sum totals:**
```python
def node_final_report(state: TeamState) -> dict:
    total_cost = sum(u["cost_usd"] for u in state["usage"])
    total_tokens = sum(u["tokens_in"] + u["tokens_out"] for u in state["usage"])
    
    print(f"💰 Total cost: ${total_cost:.4f}")
    print(f"📊 Total tokens: {total_tokens}")
    
    # Write metrics
    with open("metrics.json", "w") as f:
        json.dump({
            "total_cost_usd": total_cost,
            "total_tokens": total_tokens,
            "usage_by_agent": state["usage"]
        }, f, indent=2)
    
    return {}
```

---

## 3. Model Selection & Fallback Chain

### 2.1 CODER Agent — 3-Tier Fallback

The CODER agent uses a **3-tier fallback strategy** for code generation:

```
┌──────────────────────────────────────────────────────────────┐
│  CODER MODEL SELECTION                                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Tier 1: Local (Framework1)                                 │
│    ├─ Model: qwen3-coder-next (80B MoE, 3B active)          │
│    ├─ Route: Model router (role="coder")                    │
│    ├─ Cost: $0 (free, on-premises)                          │
│    ├─ Speed: 31 tok/s (warm), 40-90s cold load              │
│    └─ Status: ⚠️ Currently broken (zero-file bug)           │
│                                                              │
│  Tier 2: OpenRouter (PLANNED — not yet deployed)            │
│    ├─ Model: qwen/qwen3-coder-next (80B MoE)                │
│    ├─ Route: Direct OpenAI SDK call to OpenRouter           │
│    ├─ Cost: $0.12/$0.75 per million tokens                  │
│    ├─ Speed: 28 tok/s, 1-2s first token                     │
│    └─ Status: ✅ Tested, ready to deploy                    │
│                                                              │
│  Tier 3: Cloud (Anthropic)                                  │
│    ├─ Model: claude-opus-4-6                                │
│    ├─ Route: Direct Anthropic SDK call                      │
│    ├─ Cost: $15/$75 per million tokens                      │
│    ├─ Speed: 95 tok/s, 0.5-1s first token                   │
│    └─ Status: ✅ Current fallback (all runs use this)       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Decision logic:**

```python
def node_coder_implement(state):
    # Try Tier 1: Local
    response = call_model_router("coder", prompt)
    files = parse_swift_files(response)
    if len(files) > 0:
        return {"coder_model_used": "coder (local)", "current_code": files}
    
    # FUTURE: Try Tier 2: OpenRouter
    # response = call_openrouter(prompt, "qwen/qwen3-coder-next")
    # files = parse_swift_files(response)
    # if len(files) > 0:
    #     return {"coder_model_used": "openrouter/qwen3-coder-next", "current_code": files}
    
    # Tier 3: Cloud fallback
    response = call_claude(prompt, "claude-opus-4-6")
    files = parse_swift_files(response)
    if len(files) > 0:
        return {"coder_model_used": "anthropic/claude-opus-4-6", "current_code": files}
    
    # Both failed → abort iteration
    return {"confidence_score": 0, "issues": ["Coder returned 0 files"]}
```

### 2.2 Other Agents — Cloud Only

All other agents run on Anthropic cloud:

| Agent | Model | Why Cloud | Cost Impact |
|-------|-------|-----------|-------------|
| GAHO (orchestrator) | Opus 4-6 | Lightweight, few calls per run | Low (~$0.02/run) |
| GARRO (design) | Opus 4-6 | Needs high-quality structured output | Medium (~$0.17/run) |
| VERA (audit) | Sonnet 4-6 | Security review, cost-optimized | Low (~$0.01/run) |
| GARRO (review) | Opus 4-6 + vision | Vision API, screenshot analysis | Low (~$0.05/run) |

**Why not OpenRouter for these?**
- GAHO/VERA: Token counts too small to justify switching ($0.01 savings)
- GARRO design: Needs highest quality — Opus > kimi-k2.5 for structured specs
- GARRO review: Anthropic vision API is mature, OpenRouter's is experimental

**Exception:** Could test `moonshotai/kimi-k2.5` for GARRO design node — it's a thinking model optimized for structured planning. Would save 6.8× on cost. Worth experimenting if GARRO design quality becomes a bottleneck.

---

## 3. Cost Analysis

### 3.1 Per-Run Cost Breakdown

**Current (all Opus coder):**

| Agent | Calls | Tokens In | Tokens Out | Cost |
|-------|-------|-----------|------------|------|
| GAHO | 5 | 500 | 200 | $0.0225 |
| GARRO (design) | 5 | 1000 | 2000 | $0.165 |
| CODER | 5 | 1500 | 10000 | **$7.725** |
| VERA | 5 | 3000 | 1000 | $0.012 |
| GARRO (review) | 5 | 1000 | 500 | $0.0525 |
| **TOTAL** | | | | **$7.977** |

**With OpenRouter coder (Tier 2):**

| Agent | Calls | Tokens In | Tokens Out | Cost |
|-------|-------|-----------|------------|------|
| GAHO | 5 | 500 | 200 | $0.0225 |
| GARRO (design) | 5 | 1000 | 2000 | $0.165 |
| CODER | 5 | 1500 | 10000 | **$0.768** ← 90% savings |
| VERA | 5 | 3000 | 1000 | $0.012 |
| GARRO (review) | 5 | 1000 | 500 | $0.0525 |
| **TOTAL** | | | | **$1.020** |

**Savings:** $6.96 per run (87% reduction)

**With local coder working (Tier 1):**

| Agent | Calls | Tokens In | Tokens Out | Cost |
|-------|-------|-----------|------------|------|
| GAHO | 5 | 500 | 200 | $0.0225 |
| GARRO (design) | 5 | 1000 | 2000 | $0.165 |
| CODER | 5 | 1500 | 10000 | **$0.000** ← FREE |
| VERA | 5 | 3000 | 1000 | $0.012 |
| GARRO (review) | 5 | 1000 | 500 | $0.0525 |
| **TOTAL** | | | | **$0.252** |

**Savings:** $7.73 per run (97% reduction)

---

### 3.2 Monthly Projections

**Assumptions:**
- 10 pipeline runs/week (active development)
- 40 runs/month

| Scenario | Cost/Run | Cost/Month | Notes |
|----------|----------|------------|-------|
| All Opus (current) | $7.98 | **$319/mo** | 100% cloud, zero local |
| OpenRouter coder | $1.02 | **$41/mo** | 87% savings |
| Local coder (ideal) | $0.25 | **$10/mo** | 97% savings, free inference |

**Cost optimization priority:**
1. **Fix local zero-file bug** → 97% savings, $10/mo
2. **Deploy OpenRouter Tier 2** → 87% savings, $41/mo (insurance if local fails)
3. **Batch runs** → Reduce total runs by combining design iterations

---

## 4. OpenRouter Integration Details

### 4.1 Current Status

- ✅ **Researched:** Model IDs verified, pricing confirmed
- ✅ **Tested:** Standalone curl tests, LangGraph demo successful
- ✅ **Validated:** Cost tracking, state management, fallback logic
- ❌ **NOT deployed:** Tier 2 fallback commented out in `langgraph-team-audit.py`

### 4.2 What Needs to Happen Before Deployment

1. **Test OpenRouter qwen output format**  
   Confirm `qwen/qwen3-coder-next` produces parsable ````swift:FILENAME.swift` blocks in real pipeline conditions. Run:
   ```bash
   python3 test_openrouter_swift_parsing.py
   ```

2. **Wire Tier 2 into `node_coder_implement()`**  
   Uncomment and test:
   ```python
   # Tier 2: OpenRouter qwen
   or_response = call_openrouter(
       system="You are a SwiftUI expert.",
       user=prompt,
       model="qwen/qwen3-coder-next",
       max_tokens=4000
   )
   files = parse_swift_files(or_response)
   if len(files) > 0:
       state["coder_model_used"] = "openrouter/qwen3-coder-next"
       state["coder_fallback"] = True
       return state
   ```

3. **Update metrics tracking**  
   Add `"openrouter_cost_usd"` field to metrics.json:
   ```json
   {
     "coder_model_used": "openrouter/qwen3-coder-next",
     "openrouter_cost_usd": 0.00689,
     "anthropic_cost_usd": 0.252
   }
   ```

4. **Monitor for 1 week**  
   - Track success rate (% of runs where OpenRouter works)
   - Track fallback frequency (how often Tier 3 is needed)
   - Track cost delta (actual savings vs projected)

### 4.3 OpenRouter Configuration

**API Key:** Stored in `~/.openclaw/secrets.env`
```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Client setup (Python):**
```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "https://eldrchat.dev",
        "X-Title": "OpenClaw-LangGraph"
    }
)

response = client.chat.completions.create(
    model="qwen/qwen3-coder-next",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=4000
)
```

**Pricing:**
- Input: $0.12 per million tokens
- Output: $0.75 per million tokens
- Context: 256K tokens

**Rate limits:** None observed (tested 20+ calls in 90 min)

---

## 5. When to Use Local vs OpenRouter vs Cloud

### 5.1 Decision Tree

```
START: Coder agent needs to generate Swift files
│
├─ Is Framework1 idle? (no other agents using qwen3-coder-next)
│  ├─ YES → Try Tier 1 (local)
│  │   ├─ Parsable output? → USE (free)
│  │   └─ Zero files? → Tier 2
│  └─ NO → Tier 2 (Framework1 saturated)
│
├─ Try Tier 2 (OpenRouter qwen3-coder-next)
│  ├─ Parsable output? → USE ($0.12/$0.75 per million)
│  ├─ 429 rate limit? → Tier 3 (don't retry)
│  └─ Timeout/error? → Tier 3
│
└─ Tier 3 (Anthropic Opus)
   └─ Final fallback ($15/$75 per million)
```

### 5.2 Agent-Specific Rules

| Agent | Local? | OpenRouter? | Cloud? | Why |
|-------|--------|-------------|--------|-----|
| GAHO | ❌ | ❌ | ✅ | Lightweight, few calls, needs reliability |
| GARRO (design) | ❌ | ⚠️ Test kimi-k2.5 | ✅ | Needs highest quality structured output |
| CODER | ✅ Try first | ✅ Fallback | ✅ Final fallback | Heaviest token consumer, cost-sensitive |
| BUILDER | N/A (tool) | N/A | N/A | Local shell commands only |
| VERA | ❌ | ❌ | ✅ Sonnet | Security review, must be reliable |
| GARRO (review) | ❌ | ❌ | ✅ Opus + vision | Vision API, screenshot analysis |

---

## 6. Debugging & Monitoring

### 6.1 Metrics to Track

Every pipeline run writes `team-audit-metrics.json`:

```json
{
  "run_timestamp": "2026-03-24T15:38:20.259944",
  "iterations": 5,
  "final_confidence": 0,
  "build_success": false,
  
  "coder_model_used": "anthropic/claude-opus-4-6",
  "coder_fallback": true,
  "coder_fallback_events": [
    "[Iter 1] ⚠️ Local coder returned 0 files — falling back to Opus",
    "[Iter 2] ⚠️ Local coder returned 0 files — falling back to Opus"
  ],
  
  "usage": [
    {"model": "claude-opus-4-6", "tokens": 10234, "cost_usd": 0.234},
    {"model": "qwen/qwen3-coder-next", "tokens": 9142, "cost_usd": 0.0069}
  ],
  
  "total_tokens": 19376,
  "total_cost_usd": 0.2409,
  
  "log_file": "/path/to/team-audit.log"
}
```

**Key metrics:**
- `coder_fallback` — True if local failed (watch this for local model health)
- `coder_model_used` — Which tier actually ran (local/openrouter/cloud)
- `total_cost_usd` — Track spend per run, trend over time
- `final_confidence` — Quality metric (higher = fewer iterations needed)

### 6.2 Alerts

**Set up alerts when:**
1. `coder_fallback == true` for 10 consecutive runs → local model is dead, investigate
2. `total_cost_usd > $10` for a single run → something went wrong (excessive iterations or token usage)
3. `final_confidence < 50` after 5 iterations → design/implementation mismatch, review web UI reference

### 6.3 Common Issues

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| All runs fall back to Opus | Local qwen zero-file bug | Prompt engineering, or wait for OpenRouter deploy |
| High cost despite OpenRouter | OpenRouter returning 0 files → Opus fallback | Test OpenRouter output format, fix prompt |
| Low confidence scores | Design spec doesn't match web UI | Update web UI reference doc |
| Build failures every iteration | Syntax errors in generated code | Review coder system prompt, add examples |
| Long run times (>10 min) | Cold model loads on Framework1 | Pre-warm qwen before pipeline run |

---

## 7. Local Model (Framework1) — Current Issues

### 7.1 Zero-File Bug

**Symptom:** Framework1's qwen3-coder-next returns well-formatted responses explaining the code, but **zero parsable ````swift:FILENAME.swift` blocks**.

**Example response:**
```
I'll implement the SwiftUI views as follows:

1. ContentView.swift — The main app shell uses NavigationSplitView...
2. ContactListView.swift — Displays contacts in a List with search...

[No actual code blocks]
```

**Root cause:** Unknown. Possibly:
- Prompt doesn't emphasize format strongly enough
- Model interprets format as suggestion, not requirement
- Inference parameters suppress repetitive backtick sequences

**Current workaround:** All pipeline runs fall back to Opus (Tier 3).

**Next steps:**
1. Strengthen prompt:
   ```
   CRITICAL: Output ONLY code blocks in this exact format:
   
   ```swift:ContentView.swift
   import SwiftUI
   ...
   ```
   
   Do NOT explain. Do NOT describe. Output code blocks ONLY.
   ```

2. Test different inference parameters:
   - Temperature: 0.1 (vs 0.3)
   - Repetition penalty: 1.0 (vs 1.1)
   - Top-p: 0.9 (vs 0.95)

3. Try explicit few-shot example in system prompt

### 7.2 When Local Works

Local qwen3-coder-next is **excellent** when it works:
- Quality matches OpenRouter qwen (same model family)
- Fast (31 tok/s warm, 18s per file)
- Free (on-premises, no API costs)

The zero-file bug is a **format issue, not a capability issue**. Fixing this unlocks 97% cost savings.

---

## 8. Future Optimizations

### 8.1 Batch Design Iterations

Instead of GARRO → CODER → BUILDER → VERA → GARRO for each iteration, try:

**GARRO → [CODER + BUILDER + VERA] × 3 parallel → GARRO reviews all 3**

Benefits:
- Explore design variations in parallel
- Reduce GARRO calls (most expensive agent)
- Find optimal solution faster

Tradeoff:
- Higher concurrency = higher peak cost
- Needs 3× Framework1 capacity (or all-cloud)

### 8.2 Cache Web UI Reference

Web UI reference doc is 8KB, included in every GARRO design prompt → 5 calls × 8KB = 40KB redundant.

**Fix:** Use Anthropic prompt caching:
```python
system = [
    {
        "type": "text",
        "text": "You are GARRO, design specialist.",
        "cache_control": {"type": "ephemeral"}
    },
    {
        "type": "text",
        "text": web_ui_reference,  # 8KB cached
        "cache_control": {"type": "ephemeral"}
    }
]
```

**Savings:** 40KB → 8KB (1st call full, 4 subsequent calls cached at 90% discount)

### 8.3 Pre-Warm Local Models

Before starting a pipeline run, pre-load qwen3-coder-next:
```bash
curl -s http://100.112.143.23:11434/api/generate \
  -d '{"model":"qwen3-coder-next:latest","prompt":"warmup","keep_alive":-1}' \
  | jq -r .response
```

**Impact:** Eliminates 40-90s cold load on first coder call. Faster runs = fewer iterations = lower cost.

### 8.4 Vision API for CODER

Instead of GARRO → CODER (text spec), try:

**GARRO → screenshot of web UI → CODER (vision)**

Give CODER the web UI screenshot directly, ask it to replicate in SwiftUI. Might reduce design → implementation gap.

**Tradeoff:** Vision API is slower and more expensive than text. Test if quality delta justifies cost.

---

## 9. Parallel Agent Coordination (10× Qwen Coders)

### 9.1 Architecture: Opus Orchestrator + 10 Parallel Qwen + Sonnet Reviewer

**Use case:** Rapid parallel development — break a design spec into 10 independent components, implement in parallel via OpenRouter, then aggregate and review.

**Why parallel:** 10× faster than sequential local qwen (but 20× more expensive).

**Pattern:** Sub-agent spawns (not LangGraph nodes) — each agent is an independent process.

```
┌─────────────────────────────────────────────────────────────┐
│  PARALLEL QWEN TEAM (10 CODERS)                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [1] OPUS (Architect)                                       │
│      ├─ Model: Claude Opus 4-6                              │
│      ├─ Breaks design into 10 parallel tasks                │
│      ├─ Manages Xcode tool orchestration                    │
│      └─ Integrates feedback from Sonnet reviewer            │
│                                                             │
│  [2] 10 × QWEN CODERS (Parallel via OpenRouter)            │
│      ├─ Model: qwen/qwen3-coder-next (OpenRouter)           │
│      ├─ 5 with Mei persona (Chinese AI specialist)          │
│      ├─ 5 with Vera persona (Security specialist)           │
│      └─ Each implements one SwiftUI component               │
│                                                             │
│  [3] SONNET (Reviewer)                                      │
│      ├─ Model: Claude Sonnet 4-6                            │
│      ├─ Security audit (backdoors, data leaks)              │
│      ├─ Code quality check (architecture, best practices)   │
│      └─ Confidence score + feedback for next iteration      │
│                                                             │
│  Loop: If confidence < 80%, feed Sonnet feedback → Opus     │
│        → re-spawn 10 qwen coders with updated instructions  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 9.2 Why Sub-Agent Spawns (Not LangGraph Nodes)

| Aspect | LangGraph Nodes | Sub-Agent Spawns |
|--------|-----------------|------------------|
| **Parallel execution** | ⚠️ Via parallel edges (complex) | ✅ Natural (10 independent processes) |
| **Independent tasks** | ❌ Share state dict | ✅ Fully isolated |
| **Long tasks (5 min each)** | ❌ Blocks workflow | ✅ Background execution |
| **Model diversity** | ⚠️ Requires helper functions | ✅ Each spawn picks model |
| **Persona injection** | ⚠️ Manual state mgmt | ✅ Each task gets own persona |

**For 10 parallel coders:** Sub-agent spawns are the right pattern.

---

### 9.3 Implementation Pattern

```python
def parallel_qwen_workflow(design_spec: str, max_iterations: int = 5):
    """
    Opus architects → 10 parallel qwen coders → Sonnet reviews → iterate.
    """
    iteration = 0
    confidence = 0
    feedback = ""
    
    while confidence < 80 and iteration < max_iterations:
        print(f"\n{'='*60}")
        print(f"ITERATION {iteration + 1}")
        print(f"{'='*60}\n")
        
        # STEP 1: Opus architects 10 parallel tasks
        print("🏗️  OPUS: Breaking design into 10 parallel tasks...")
        opus_prompt = f"""
        You are the architect for an iOS app. Manage Xcode tool orchestration.
        
        Design spec: {design_spec}
        Previous feedback from Sonnet: {feedback}
        
        Break this into 10 independent SwiftUI components that can be
        implemented in parallel:
        
        Tasks 1-5: Assign to Mei (Chinese AI ecosystem specialist)
        Tasks 6-10: Assign to Vera (Security specialist)
        
        For each task, provide:
        - component_name (e.g., "ContactListView.swift")
        - requirements (specific implementation details)
        - dependencies (if any, or "None")
        - integration_points (how it connects to other components)
        
        Output JSON array of 10 tasks.
        """
        
        tasks_json = call_claude(opus_prompt, "claude-opus-4-6", max_tokens=4000)
        tasks = json.loads(tasks_json)
        
        # STEP 2: Spawn 10 qwen coders in parallel
        print("💻 Spawning 10 qwen coders in parallel...")
        sessions = []
        
        for i, task in enumerate(tasks):
            persona_name = "Mei" if i < 5 else "Vera"
            persona_file = f"agents/{persona_name.lower()}.md"
            
            # Read persona
            with open(persona_file) as f:
                persona = f.read()
            
            # Build task prompt with persona injected
            task_prompt = f"""
{persona}

---

You are {persona_name}. Implement this SwiftUI component:

Component: {task['component_name']}
Requirements: {task['requirements']}
Dependencies: {task.get('dependencies', 'None')}
Integration: {task.get('integration_points', 'None')}

Output ONLY the Swift code in this format:

```swift:{task['component_name']}
import SwiftUI
...
```

CRITICAL: Output code ONLY. No explanations. No markdown outside code block.
"""
            
            # Spawn sub-agent (OpenRouter qwen)
            session = sessions_spawn(
                task=task_prompt,
                model="qwen/qwen3-coder-next",  # OpenRouter
                runtime="subagent",
                mode="run",
                runTimeoutSeconds=300,  # 5 min per agent
                label=f"qwen-coder-{i+1}-{persona_name}"
            )
            sessions.append((session, task['component_name']))
        
        # STEP 3: Wait for all to complete (parallel execution)
        print("⏳ Waiting for all 10 coders to complete...")
        results = {}
        for session, filename in sessions:
            result = wait_for_result(session)  # Blocks until complete
            code = extract_swift_code(result)  # Parse ```swift:... blocks
            results[filename] = code
        
        print(f"✅ Collected {len(results)} Swift files")
        
        # STEP 4: Aggregate into project structure
        combined_code = "\n\n".join(
            f"// {fname}\n{code}" for fname, code in results.items()
        )
        
        # STEP 5: Sonnet reviews for security + quality
        print("🔍 SONNET: Reviewing code...")
        review_prompt = f"""
        Review this SwiftUI code for:
        
        1. Security issues:
           - Backdoors or malicious code
           - Data leaks (user data sent to external servers)
           - Unsafe API usage
        
        2. Code quality:
           - Architecture (MVVM compliance)
           - Naming conventions
           - SwiftUI best practices
        
        3. Integration issues:
           - Do components work together?
           - Are dependencies handled correctly?
        
        Code:
        {combined_code}
        
        Output JSON:
        {{
          "security_issues": ["issue1", "issue2", ...],
          "quality_issues": ["issue1", "issue2", ...],
          "confidence_score": 0-100,
          "feedback": "High-level feedback for architect to improve next iteration"
        }}
        """
        
        review_json = call_claude(review_prompt, "claude-sonnet-4-6", max_tokens=2048)
        review = json.loads(review_json)
        
        confidence = review["confidence_score"]
        feedback = review["feedback"]
        
        print(f"📊 Confidence: {confidence}%")
        print(f"🔒 Security issues: {len(review['security_issues'])}")
        print(f"✨ Quality issues: {len(review['quality_issues'])}")
        
        iteration += 1
    
    print(f"\n✅ Workflow complete: {confidence}% confidence after {iteration} iterations")
    return results, review
```

---

### 9.4 Cost Analysis (10 Parallel Qwen)

**Per iteration:**

| Agent | Calls | Tokens In | Tokens Out | Model | Cost |
|-------|-------|-----------|------------|-------|------|
| Opus (architect) | 1 | 2,000 | 4,000 | claude-opus-4-6 | $0.33 |
| Qwen × 10 (OpenRouter) | 10 | 1,500 ea | 3,000 ea | qwen/qwen3-coder-next | **$0.54** |
| Sonnet (reviewer) | 1 | 30,000 | 2,000 | claude-sonnet-4-6 | $0.12 |
| **TOTAL** | **12** | | | | **$0.99** |

**5 iterations:** ~$5/run

**vs sequential local qwen (5-agent LangGraph):** $0.25/run (but 10× slower)

**Tradeoff:** Parallel is **10× faster** but **20× more expensive**. Worth it for rapid iteration when speed matters.

---

### 9.5 Hardware Constraint: Why OpenRouter?

**Framework1 VRAM:** ~100GB total, qwen3-coder-next uses 61GB.

**Can run:** **1 qwen instance at a time** (local sequential only).

**For 10 parallel:** Must use **OpenRouter** (cloud-hosted qwen instances).

**Local parallel not possible** without adding 9 more Framework1-class machines.

---

### 9.6 Persona Injection (Critical for Local Models)

**Problem:** Local models don't have access to `agents/*.md` — they only see what's in the prompt.

**Solution:** Read persona file and prepend to task prompt.

```python
# Read Mei or Vera persona
with open(f"agents/{persona_name.lower()}.md") as f:
    persona = f.read()

# Inject into task prompt
task_prompt = f"""
{persona}

---

You are {persona_name}. Implement this component:
...
"""
```

**Why this matters:** Without persona injection, agents run without identity and will hallucinate backstory, location, personality, etc.

**Applies to:** All sub-agent spawns with local models (qwen, gpt-oss, etc.). Cloud models running in main session context already have persona access.

---

### 9.7 OpenRouter Rate Limits (Test Before Production)

**Need to verify:** Can OpenRouter handle 10 simultaneous `qwen/qwen3-coder-next` calls?

**Test script:**
```bash
# Spawn 10 parallel curl requests
source ~/.openclaw/secrets.env

for i in {1..10}; do
  (curl -s -X POST https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "model": "qwen/qwen3-coder-next",
      "messages": [{"role": "user", "content": "Write hello world in Swift"}],
      "max_tokens": 500
    }' > /tmp/openrouter-test-$i.json &)
done
wait

# Check for 429 errors
grep -l "429" /tmp/openrouter-test-*.json
```

**If no 429 errors:** OpenRouter can handle 10 parallel calls → production ready.

**If 429 errors:** Reduce concurrency (e.g., 5 parallel, then 5 more) or add retry logic.

---

### 9.8 Testing Plan (Before Production)

1. **Test OpenRouter rate limits** (see 9.7 above)

2. **Test with 2 agents first:**
   ```python
   # Spawn 2 qwen coders (1 Mei, 1 Vera)
   # Verify results aggregate correctly
   # Check cost aligns with estimates (~$0.20/iteration)
   ```

3. **Scale to 5 agents:**
   ```python
   # Monitor OpenRouter response times
   # Check if results degrade with concurrency
   ```

4. **Full production (10 agents):**
   ```python
   # Run 1-2 iterations
   # Monitor total cost ($1-2)
   # Validate quality matches sequential runs
   ```

---

### 9.9 When to Use Parallel vs Sequential

| Use Case | Sequential (LangGraph) | Parallel (Sub-Agents) |
|----------|------------------------|----------------------|
| **Rapid prototyping** (speed > cost) | ❌ | ✅ 10× faster |
| **Budget-constrained** (cost > speed) | ✅ 20× cheaper | ❌ |
| **Complex integration** (tight coupling) | ✅ Easier to coordinate | ⚠️ Requires careful task decomposition |
| **Independent components** | ⚠️ Overkill for parallel edges | ✅ Natural fit |
| **Local-first development** | ✅ Single qwen instance | ❌ Requires OpenRouter |

**Rule of thumb:** Use parallel when deadline is tight and budget allows. Use sequential for cost-optimized iteration.

---

### 9.10 Code Location

**Full implementation:** `projects/eldrchat/parallel-qwen-workflow.py` (to be created)

**Dependencies:**
- `agents/mei.md` — Mei persona
- `agents/vera.md` — Vera persona
- OpenRouter API key in `~/.openclaw/secrets.env`
- `sessions_spawn` for sub-agent orchestration

---

## 10. Quick Reference

### 9.1 Pipeline Commands

```bash
# Run pipeline (current working directory: projects/eldrchat)
python3 langgraph-team-audit.py

# Check metrics
cat langgraph-team-audit/team-audit-metrics.json | jq .

# View log
tail -f langgraph-team-audit/team-audit-*.log

# Screenshot output
open langgraph-team-audit/screenshot-iter5.png
```

### 9.2 Model Router Health Check

```bash
# Check what's loaded on Framework1
ssh -i ~/.ssh/framework_key gk@100.112.143.23 "ollama ps"

# Pre-warm qwen3-coder-next
curl -s http://100.112.143.23:11434/api/generate \
  -d '{"model":"qwen3-coder-next:latest","prompt":"warmup","keep_alive":-1}' \
  | jq -r .response
```

### 9.3 OpenRouter Health Check

```bash
# Test OpenRouter connection
source ~/.openclaw/secrets.env
curl -s https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  | jq -r '.data[] | select(.id | contains("qwen3-coder-next")) | .id'

# Test qwen3-coder-next
curl -s -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3-coder-next",
    "messages": [{"role": "user", "content": "Write hello world in Swift"}],
    "max_tokens": 200
  }' | jq -r '.choices[0].message.content'
```

---

## 10. Summary

**Current state:**
- ✅ Pipeline runs, builds, audits, iterates
- ⚠️ Local coder broken (zero-file bug) → all runs use Opus ($8/run)
- ✅ OpenRouter tested, ready to deploy
- ❌ Tier 2 fallback not yet wired in

**Next actions:**
1. Deploy OpenRouter Tier 2 → reduce cost to $1/run (87% savings)
2. Fix local zero-file bug → reduce cost to $0.25/run (97% savings)
3. Monitor metrics for 1 week, validate savings

**Long-term vision:**
- Local-first (free inference)
- OpenRouter as safety net (cheap cloud)
- Anthropic as premium tier (quality/reliability)
- Total cost: <$50/mo for active development

---

*Document compiled: 2026-03-24 16:30 PDT*  
*See also: `team-openrouter-integration-v1-2026-03-24.md` for OpenRouter integration details*
