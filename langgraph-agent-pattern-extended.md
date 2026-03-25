# LangGraph Agent Deployment Pattern — Extended Guide

---

**Pattern:** Deploy autonomous agents as LangGraph nodes instead of spawning independent sub-agent sessions.

**Use when:** Multiple agents need to collaborate sequentially with shared state.

**Avoid when:** Agents run independently in parallel for >5 min each, or require different runtimes (ACP harness vs cloud).

---

## Table of Contents

1. [Why LangGraph Nodes Over Sub-Agent Spawns](#1-why-langgraph-nodes-over-sub-agent-spawns)
2. [Core Implementation Pattern](#2-core-implementation-pattern)
3. [State Management Deep Dive](#3-state-management-deep-dive)
4. [Multi-Model API Integration](#4-multi-model-api-integration)
5. [Adding New Agents to a Team](#5-adding-new-agents-to-a-team)
6. [Cost Tracking and Metrics](#6-cost-tracking-and-metrics)
7. [Conditional Edges and Loops](#7-conditional-edges-and-loops)
8. [Error Handling and Fallbacks](#8-error-handling-and-fallbacks)
9. [Debugging and Observability](#9-debugging-and-observability)
10. [When to Use Nodes vs Sub-Agent Spawns](#10-when-to-use-nodes-vs-sub-agent-spawns)
11. [Real-World Example: EldrChat iOS Team](#11-real-world-example-eldrchat-ios-team)

---

## 1. Why LangGraph Nodes Over Sub-Agent Spawns

### 1.1 Traditional Sub-Agent Spawning

**Flow:**
```python
# Spawn agent for each task
garro_session = sessions_spawn(
    agentId="garro",
    task="Design SwiftUI spec for contact list",
    runtime="subagent",
    mode="run"
)
# Wait for completion, parse result from message
result = wait_for_result(garro_session)

# Spawn next agent with result as input
coder_session = sessions_spawn(
    agentId="coder",
    task=f"Implement this spec: {result}",
    runtime="subagent",
    mode="run"
)
```

**Problems:**
- **Spawn overhead:** 1-2s per agent session creation
- **Message parsing:** Results come back as text, need structured extraction
- **Log fragmentation:** Each agent writes to separate session logs
- **State complexity:** Need to manually track what each agent produced
- **Error handling:** Timeouts, malformed output require per-spawn retry logic

---

### 1.2 LangGraph Node Deployment

**Flow:**
```python
# Define agents as nodes
def node_garro_design(state):
    response = call_model(MODEL_GARRO, build_prompt(state))
    return {"design_spec": response}

def node_coder_implement(state):
    response = call_model(MODEL_CODER, state["design_spec"])
    return {"current_code": parse_files(response)}

# Build graph
graph = StateGraph(TeamState)
graph.add_node("garro", node_garro_design)
graph.add_node("coder", node_coder_implement)
graph.add_edge("garro", "coder")
app = graph.compile()

# Run
final_state = app.invoke(initial_state)
```

**Benefits:**
- **Instant transitions:** No spawn overhead between nodes
- **Structured state:** All data in a typed dict, no parsing
- **Single log:** Entire workflow in one execution trace
- **Built-in checkpointing:** LangGraph persists state after each node
- **Direct model control:** Each node calls its own model explicitly

---

### 1.3 Comparison Table

| Aspect | LangGraph Nodes | Sub-Agent Spawns |
|--------|-----------------|------------------|
| **Transition speed** | Instant (function call) | 1-2s per spawn |
| **State management** | Shared TypedDict | Message passing + parsing |
| **Logging** | Single unified log | Scattered session logs |
| **Model assignment** | Direct per node | Inherit session or override |
| **Cost tracking** | Easy (all in one process) | Harder (aggregate across sessions) |
| **Debugging** | One execution trace | Multi-session reconstruction |
| **Parallelism** | Via parallel edges | Natural (independent processes) |
| **Long tasks (>5 min)** | Blocks workflow | Runs in background |
| **Mixed runtimes** | Can't mix (single process) | Can mix (ACP + cloud) |

---

## 2. Core Implementation Pattern

### 2.1 Step-by-Step Setup

#### Step 1: Define Model Assignments

Create constants for each agent's model. This is your **single source of truth** for which model each agent uses.

```python
# Model assignments
MODEL_ORCHESTRATOR = "claude-opus-4-6"        # High-level planning
MODEL_DESIGNER = "moonshotai/kimi-k2.5"       # Creative, structured output
MODEL_CODER = "coder"                         # Model router role (qwen3-coder-next)
MODEL_AUDITOR = "claude-sonnet-4-6"           # Security review
MODEL_REVIEWER = "claude-opus-4-6"            # Final quality check
```

**Why constants?**
- Easy to swap models (change one line, entire team updates)
- Clear documentation of who uses what
- Cost tracking becomes trivial (map usage to constant name)

---

#### Step 2: Define State Schema

Use `TypedDict` to define the shared state all agents read/write.

```python
from typing import TypedDict, List, Dict

class TeamState(TypedDict):
    # Iteration tracking
    iteration: int
    max_iterations: int
    confidence_score: int
    
    # Input data
    web_ui_reference: str
    user_requirements: str
    
    # Agent outputs
    design_spec: str                  # Designer output
    current_code: Dict[str, str]      # Coder output {filename: content}
    audit_issues: List[str]           # Auditor output
    review_feedback: str              # Reviewer output
    
    # Metadata
    issues: List[str]                 # Accumulated issues
    build_success: bool
    screenshot_path: str
    
    # Model tracking
    coder_model_used: str
    usage: List[Dict]                 # Cost tracking
```

**Rules:**
- Every field agents need must be defined here
- Use specific types (`Dict[str, str]`, not `dict`)
- Initialize ALL fields in `initial_state` (see Step 4)

---

#### Step 3: Create Node Functions

Each agent = one function that takes `state` and returns a dict of **changed keys only**.

```python
def node_designer(state: TeamState) -> dict:
    """Designer agent — creates SwiftUI spec from web UI reference."""
    print(f"🎨 [Iter {state['iteration']}] Designer: Creating spec...")
    
    # Build prompt from state
    prompt = f"""
    You are a SwiftUI design specialist.
    
    Create a detailed spec matching this web UI:
    {state['web_ui_reference']}
    
    User requirements: {state['user_requirements']}
    Previous issues to address: {state['issues']}
    
    Output a structured design spec with:
    - Color palette (exact hex codes)
    - Layout hierarchy
    - Component list
    - Interaction patterns
    """
    
    # Call model (OpenRouter for Designer)
    response = call_openrouter(
        system="You are a SwiftUI design expert.",
        user=prompt,
        model=MODEL_DESIGNER,
        max_tokens=4000
    )
    
    # Track usage
    usage = state.get("usage", [])
    usage.append({
        "agent": "Designer",
        "model": MODEL_DESIGNER,
        "tokens_in": len(prompt.split()),
        "tokens_out": len(response.split()),
        "cost_usd": calculate_cost(MODEL_DESIGNER, len(prompt.split()), len(response.split()))
    })
    
    # Return ONLY changed keys (LangGraph merges automatically)
    return {
        "design_spec": response,
        "usage": usage
    }
```

**Critical:** Return `{"design_spec": response}`, NOT `{**state, "design_spec": response}`. LangGraph handles merging.

---

```python
def node_coder(state: TeamState) -> dict:
    """Coder agent — implements SwiftUI from design spec."""
    print(f"💻 [Iter {state['iteration']}] Coder: Implementing...")
    
    prompt = f"""
    Implement SwiftUI views matching this design spec:
    {state['design_spec']}
    
    Output exactly 5 files in this format:
    
    ```swift:ContentView.swift
    import SwiftUI
    ...
    ```
    
    ```swift:ContactListView.swift
    ...
    ```
    """
    
    # Try local first (model router)
    try:
        response = call_model_router("coder", prompt, timeout=180)
        files = parse_swift_files(response)
        if len(files) > 0:
            return {
                "current_code": files,
                "coder_model_used": "coder (local qwen3-coder-next)"
            }
    except Exception as e:
        print(f"⚠️ Local coder failed: {e}")
    
    # Fallback to cloud
    response = call_claude(prompt, MODEL_CODER, max_tokens=8000)
    files = parse_swift_files(response)
    
    return {
        "current_code": files,
        "coder_model_used": MODEL_CODER,
        "coder_fallback": True
    }
```

---

#### Step 4: Build the Graph

```python
from langgraph.graph import StateGraph, END

# Create graph
graph = StateGraph(TeamState)

# Add nodes
graph.add_node("orchestrator", node_orchestrator)
graph.add_node("designer", node_designer)
graph.add_node("coder", node_coder)
graph.add_node("auditor", node_auditor)
graph.add_node("reviewer", node_reviewer)
graph.add_node("final_report", node_final_report)

# Define workflow edges
graph.set_entry_point("orchestrator")
graph.add_edge("orchestrator", "designer")
graph.add_edge("designer", "coder")
graph.add_edge("coder", "auditor")
graph.add_edge("auditor", "reviewer")

# Conditional loop: if confidence < 80%, iterate
graph.add_conditional_edges(
    "reviewer",
    should_continue,  # Function that checks confidence_score
    {
        "continue": "orchestrator",  # Loop back
        "end": "final_report"         # Done
    }
)
graph.add_edge("final_report", END)

# Compile
app = graph.compile()
```

---

#### Step 5: Run the Workflow

```python
# Initialize state (ALL TeamState fields must be set)
initial_state = {
    "iteration": 0,
    "max_iterations": 5,
    "confidence_score": 0,
    "web_ui_reference": load_web_ui_doc(),
    "user_requirements": "Modern iOS app, SF Symbols, native feel",
    "design_spec": "",
    "current_code": {},
    "audit_issues": [],
    "review_feedback": "",
    "issues": [],
    "build_success": False,
    "screenshot_path": "",
    "coder_model_used": "",
    "usage": []
}

# Run
print("🚀 Starting LangGraph team workflow...")
final_state = app.invoke(initial_state)

# Results
print(f"✅ Complete: {final_state['confidence_score']}% confidence")
print(f"💰 Total cost: ${sum(u['cost_usd'] for u in final_state['usage']):.4f}")
print(f"📊 Files generated: {len(final_state['current_code'])}")
```

---

## 3. State Management Deep Dive

### 3.1 Critical Rule: Return Only Changed Keys

**❌ WRONG:**
```python
def node_example(state: TeamState) -> dict:
    # Creates a NEW dict with stale copies of all fields
    return {**state, "new_field": "value"}
```

**Why wrong?** If another node modified `state["other_field"]` in parallel (or if state was checkpointed), you're overwriting it with the old value.

**✅ CORRECT:**
```python
def node_example(state: TeamState) -> dict:
    # Only return what you changed
    return {"new_field": "value"}
```

LangGraph automatically merges this into the existing state.

---

### 3.2 Accessing State

**✅ CORRECT:**
```python
design_spec = state["design_spec"]
iteration = state["iteration"]
```

**❌ WRONG:**
```python
design_spec = state.design_spec  # TypedDict is not a class
```

---

### 3.3 Updating Lists/Dicts in State

**Problem:** If you return `{"issues": new_issues}`, it **replaces** the entire list.

**Solution:** Read, append, return.

```python
def node_example(state: TeamState) -> dict:
    # Read current list
    issues = state.get("issues", [])
    
    # Append new items
    issues.append("New issue found")
    
    # Return updated list
    return {"issues": issues}
```

Same for dicts:
```python
def node_example(state: TeamState) -> dict:
    code = state.get("current_code", {})
    code["NewFile.swift"] = "import SwiftUI\n..."
    return {"current_code": code}
```

---

### 3.4 Initialization Checklist

Every field in `TeamState` must be initialized in `initial_state`:

```python
class TeamState(TypedDict):
    iteration: int
    design_spec: str
    current_code: Dict[str, str]
    issues: List[str]

# ✅ CORRECT
initial_state = {
    "iteration": 0,
    "design_spec": "",
    "current_code": {},
    "issues": []
}

# ❌ WRONG — missing fields will cause KeyError
initial_state = {
    "iteration": 0
}
```

---

## 4. Framework1 Scheduling Constraint

**Critical:** Framework1 is a **single-inference bottleneck**. Only one model runs at a time.

### 4.1 The Problem

```python
# ❌ BAD: Parallel local dispatches
for i in range(5):
    results.append(dispatch(role="coder", prompt=f"Implement component {i}"))
# All 5 tasks queue serially → 15+ minutes total
```

**Why it's bad:**
- qwen3-coder-next uses 61GB VRAM (100% of GPU)
- Tasks queue one-by-one, can't run in parallel
- Orchestrator thinks it's sending parallel work, but it's actually serial

### 4.2 The Fix

**Route by task complexity:**

```python
def node_coder_implement(state: TeamState) -> dict:
    prompt = build_prompt(state)
    
    # Estimate complexity
    est_tokens = estimate_output_tokens(prompt)
    
    if est_tokens < 2000:  # Light task (< 2 min)
        # Use local fast model (gpt-oss:20b, 3× faster than qwen)
        result = dispatch(role="coder-fast", prompt=prompt)
    else:  # Heavy task
        # Use cloud (parallel-safe, no queue blocking)
        result = call_claude(prompt, "claude-opus-4-6", max_tokens=8000)
    
    return {"current_code": parse_files(result)}
```

### 4.3 Orchestrator Context Injection

**Include this in orchestrator system prompt:**

```python
FRAMEWORK1_CONSTRAINT = """
Framework1 runs ONE inference at a time (qwen3-coder-next = 61GB, 100% GPU).
Tasks queue serially. Keep local tasks light (<2 min). Heavy tasks → cloud.

Examples:
- Light: Brief summaries, small code snippets, quick reviews → local
- Heavy: Multi-file generation, complex reasoning, long analysis → cloud

If you plan to dispatch 3+ tasks in parallel, send them to cloud (Opus/Sonnet).
"""
```

**Inject it:**

```python
def node_orchestrator(state: TeamState) -> dict:
    system = f"""
    {AGENT_PERSONA_ORCHESTRATOR}
    
    {FRAMEWORK1_CONSTRAINT}
    """
    
    response = call_claude(
        system=system,
        user=build_plan_prompt(state),
        model="claude-opus-4-6"
    )
    
    return {"plan": parse_plan(response)}
```

### 4.4 Decision Matrix

| Task Type | Est. Time | Route To | Why |
|-----------|-----------|----------|-----|
| Brief summary | <1 min | `coder-fast` (gpt-oss:20b) | Fast local, doesn't block |
| Small snippet | 1-2 min | `coder` (qwen3-coder-next) | Good quality, acceptable wait |
| Multi-file code | 3-5 min | Cloud (Opus) | Would block queue |
| Complex reasoning | 5+ min | Cloud (Opus) | Too slow for local |
| 3+ parallel tasks | Any | Cloud (Sonnet/Opus) | Avoid serial queue |

---

## 5. Multi-Model API Integration

### 4.1 OpenRouter Helper

```python
def call_openrouter(
    system: str,
    user: str,
    model: str,
    max_tokens: int = 2048,
    temperature: float = 0.7
) -> str:
    """Call OpenRouter API (OpenAI-compatible)."""
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
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    return response.choices[0].message.content
```

**Supported models:**
- `qwen/qwen3-coder-next` — $0.12/$0.75 per million tokens
- `moonshotai/kimi-k2.5` — $0.45/$2.20 per million tokens
- `google/gemini-2.0-flash-001` — $0.075/$0.30 per million tokens

---

### 4.2 Model Router Helper (Local Inference)

```python
def call_model_router(role: str, prompt: str, timeout: int = 180) -> str:
    """Dispatch to local model via model router."""
    import subprocess
    
    result = subprocess.run(
        ["bash", "projects/model-router/scripts/dispatch.sh",
         "--role", role,
         "--prompt", prompt],
        capture_output=True,
        text=True,
        timeout=timeout
    )
    
    if result.returncode != 0:
        raise Exception(f"Model router failed: {result.stderr}")
    
    return result.stdout.strip()
```

**Available roles:**
- `coder` → qwen3-coder-next (80B MoE, 3B active)
- `brief` → gpt-oss:20b
- `reasoner` → qwen3-coder-next
- `research-worker` → qwen3-coder-next

---

### 4.3 Anthropic Helper

```python
def call_claude(prompt: str, model: str, max_tokens: int = 2048, system: str = "") -> str:
    """Call Anthropic Claude API."""
    from anthropic import Anthropic
    import os
    
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    
    messages = [{"role": "user", "content": prompt}]
    
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system
    
    response = client.messages.create(**kwargs)
    return response.content[0].text
```

---

### 4.4 Vision API Helper (Screenshot Analysis)

```python
def call_openrouter_vision(
    system: str,
    user: str,
    image_path: str,
    model: str = "anthropic/claude-3.5-sonnet"
) -> str:
    """Call OpenRouter vision API with image."""
    import base64
    from openai import OpenAI
    import os
    
    # Encode image
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
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        }
                    }
                ]
            }
        ],
        max_tokens=4096
    )
    
    return response.choices[0].message.content
```

---

## 5. Adding New Agents to a Team

**Scenario:** You have a 3-agent team (Designer → Coder → Reviewer). You want to add a **Tester** agent between Coder and Reviewer to validate Swift syntax.

---

### Step 1: Define Model
```python
MODEL_TESTER = "claude-haiku-4-2"  # Fast, cheap, good enough for syntax checks
```

---

### Step 2: Update TeamState
```python
class TeamState(TypedDict):
    # ... existing fields
    syntax_issues: List[str]
    syntax_valid: bool
```

---

### Step 3: Create Node Function
```python
def node_tester(state: TeamState) -> dict:
    """Tester agent — validate Swift syntax before building."""
    print(f"🧪 [Iter {state['iteration']}] Tester: Validating syntax...")
    
    issues = []
    for filename, code in state["current_code"].items():
        # Dry-run compile
        result = subprocess.run(
            ["swiftc", "-parse", "-"],
            input=code,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            issues.append(f"{filename}: {result.stderr.strip()}")
    
    return {
        "syntax_issues": issues,
        "syntax_valid": len(issues) == 0
    }
```

---

### Step 4: Add to Graph
```python
graph.add_node("tester", node_tester)

# Insert between coder and reviewer
graph.add_edge("coder", "tester")
graph.add_edge("tester", "reviewer")  # Remove old "coder" → "reviewer" edge
```

---

### Step 5: Initialize in initial_state
```python
initial_state = {
    # ... existing fields
    "syntax_issues": [],
    "syntax_valid": False
}
```

---

**Done!** Tester is now part of the workflow. If it finds syntax errors, those flow into the next iteration.

---

## 6. Cost Tracking and Metrics

### 6.1 Per-Node Usage Tracking

```python
def node_designer(state: TeamState) -> dict:
    prompt = build_prompt(state)
    response = call_openrouter(..., model=MODEL_DESIGNER)
    
    # Calculate tokens (rough estimate)
    tokens_in = len(prompt.split())
    tokens_out = len(response.split())
    
    # Look up pricing
    cost_usd = calculate_cost(MODEL_DESIGNER, tokens_in, tokens_out)
    
    # Append to usage log
    usage = state.get("usage", [])
    usage.append({
        "agent": "Designer",
        "model": MODEL_DESIGNER,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd
    })
    
    return {
        "design_spec": response,
        "usage": usage
    }
```

---

### 6.2 Cost Calculation Helper

```python
def calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate USD cost for a model call."""
    pricing = {
        "claude-opus-4-6": (15.00, 75.00),           # per million
        "claude-sonnet-4-6": (3.00, 15.00),
        "moonshotai/kimi-k2.5": (0.45, 2.20),
        "qwen/qwen3-coder-next": (0.12, 0.75),
        "claude-haiku-4-2": (0.25, 1.25)
    }
    
    if model not in pricing:
        return 0.0  # Local models are free
    
    price_in, price_out = pricing[model]
    cost_in = (tokens_in / 1_000_000) * price_in
    cost_out = (tokens_out / 1_000_000) * price_out
    
    return cost_in + cost_out
```

---

### 6.3 Final Metrics Report

```python
def node_final_report(state: TeamState) -> dict:
    """Generate final metrics and save to JSON."""
    import json
    
    total_cost = sum(u["cost_usd"] for u in state["usage"])
    total_tokens = sum(u["tokens_in"] + u["tokens_out"] for u in state["usage"])
    
    metrics = {
        "run_timestamp": datetime.now().isoformat(),
        "iterations": state["iteration"],
        "final_confidence": state["confidence_score"],
        "build_success": state["build_success"],
        
        "coder_model_used": state["coder_model_used"],
        "coder_fallback": state.get("coder_fallback", False),
        
        "usage_by_agent": state["usage"],
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4)
    }
    
    # Write to file
    with open("team-metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    
    print(f"💰 Total cost: ${total_cost:.4f}")
    print(f"📊 Total tokens: {total_tokens:,}")
    print(f"🔁 Iterations: {state['iteration']}")
    
    return {}
```

---

## 7. Conditional Edges and Loops

### 7.1 Should Continue Logic

```python
def should_continue(state: TeamState) -> str:
    """Decide whether to iterate or finish."""
    confidence = state["confidence_score"]
    iteration = state["iteration"]
    max_iter = state["max_iterations"]
    
    # Stop conditions
    if confidence >= 80:
        print(f"✅ High confidence ({confidence}%) — finishing")
        return "end"
    
    if iteration >= max_iter:
        print(f"⚠️ Max iterations ({max_iter}) reached — finishing")
        return "end"
    
    if not state["build_success"]:
        print(f"❌ Build failed — finishing")
        return "end"
    
    # Continue iterating
    print(f"🔁 Confidence {confidence}% < 80%, iterating...")
    return "continue"
```

---

### 7.2 Wiring Conditional Edges

```python
graph.add_conditional_edges(
    "reviewer",              # Source node
    should_continue,         # Decision function
    {
        "continue": "orchestrator",  # Loop back to start
        "end": "final_report"        # Exit to final node
    }
)
```

**Flow:**
1. Reviewer node runs, sets `confidence_score`
2. LangGraph calls `should_continue(state)`
3. If returns `"continue"` → route to orchestrator node
4. If returns `"end"` → route to final_report node

---

## 8. Error Handling and Fallbacks

### 8.1 Tiered Fallback Pattern

```python
def node_coder(state: TeamState) -> dict:
    prompt = build_prompt(state)
    
    # Tier 1: Try local (free)
    try:
        response = call_model_router("coder", prompt, timeout=180)
        files = parse_swift_files(response)
        if len(files) > 0:
            return {
                "current_code": files,
                "coder_model_used": "local (qwen3-coder-next)"
            }
        print("⚠️ Local coder returned 0 files")
    except Exception as e:
        print(f"⚠️ Local coder failed: {e}")
    
    # Tier 2: Try OpenRouter (cheap cloud)
    try:
        response = call_openrouter(
            system="You are a SwiftUI expert.",
            user=prompt,
            model="qwen/qwen3-coder-next"
        )
        files = parse_swift_files(response)
        if len(files) > 0:
            return {
                "current_code": files,
                "coder_model_used": "openrouter/qwen3-coder-next",
                "coder_fallback": True
            }
        print("⚠️ OpenRouter coder returned 0 files")
    except Exception as e:
        print(f"⚠️ OpenRouter coder failed: {e}")
    
    # Tier 3: Cloud fallback (expensive but reliable)
    response = call_claude(prompt, "claude-opus-4-6", max_tokens=8000)
    files = parse_swift_files(response)
    
    return {
        "current_code": files,
        "coder_model_used": "anthropic/claude-opus-4-6",
        "coder_fallback": True
    }
```

---

### 8.2 Graceful Degradation

If a node fails completely, return degraded state:

```python
def node_example(state: TeamState) -> dict:
    try:
        result = risky_operation()
        return {"output": result}
    except Exception as e:
        print(f"❌ Node failed: {e}")
        # Log error and continue with empty output
        issues = state.get("issues", [])
        issues.append(f"Node failed: {str(e)}")
        return {
            "output": "",
            "issues": issues,
            "confidence_score": 0  # Signal failure to reviewer
        }
```

---

## 9. Debugging and Observability

### 9.1 Logging Strategy

**Print at every node:**
```python
def node_designer(state: TeamState) -> dict:
    print(f"🎨 [Iter {state['iteration']}] Designer: Starting...")
    response = call_model(...)
    print(f"   ✅ Generated {len(response)} chars")
    return {"design_spec": response}
```

**Redirect to file:**
```bash
python3 team_workflow.py 2>&1 | tee workflow.log
```

---

### 9.2 State Snapshots

After each iteration, save state to JSON:

```python
def node_orchestrator(state: TeamState) -> dict:
    iteration = state["iteration"] + 1
    
    # Save snapshot
    with open(f"state-iter{iteration}.json", "w") as f:
        json.dump(dict(state), f, indent=2)
    
    return {"iteration": iteration}
```

---

### 9.3 Visualizing the Graph

```python
from IPython.display import Image, display

# Generate graph visualization
display(Image(app.get_graph().draw_mermaid_png()))
```

Produces a flowchart showing nodes and edges.

---

## 10. When to Use Nodes vs Sub-Agent Spawns

### 10.1 Decision Matrix

| Question | Nodes | Spawns |
|----------|-------|--------|
| Do agents need to share complex state? | ✅ | ❌ |
| Are transitions frequent (>5 per workflow)? | ✅ | ❌ |
| Do agents run in parallel independently? | ⚠️ | ✅ |
| Does any agent take >5 min to complete? | ❌ | ✅ |
| Do you need different runtimes (ACP + cloud)? | ❌ | ✅ |
| Do you want a single unified log? | ✅ | ❌ |
| Is cost tracking critical? | ✅ | ⚠️ |

---

### 10.2 Hybrid Approach

**Pattern:** Use LangGraph for tight coordination, spawn sub-agents for long/parallel work.

```python
def node_research(state: TeamState) -> dict:
    """Spawn 3 parallel research sub-agents, aggregate results."""
    tasks = [
        "Research market trends",
        "Analyze competitors",
        "Review technical feasibility"
    ]
    
    # Spawn in parallel
    sessions = [
        sessions_spawn(task=t, runtime="subagent", mode="run")
        for t in tasks
    ]
    
    # Wait for all to complete
    results = [wait_for_result(s) for s in sessions]
    
    # Aggregate
    combined = "\n\n".join(results)
    return {"research_summary": combined}
```

Use this when:
- One node needs to delegate to multiple long-running sub-tasks
- Results don't need tight state coupling (just aggregate at the end)

---

## 11. Real-World Example: EldrChat iOS Team

**Full implementation:** `projects/eldrchat/langgraph-team-audit.py`

### 11.1 Team Composition

```
┌─────────────────────────────────────────────────────────┐
│  ELDR CHAT iOS TEAM (5 AGENTS)                           │
├─────────────────────────────────────────────────────────┤
│  [1] GAHO (Orchestrator) → claude-opus-4-6             │
│  [2] GARRO (Designer) → moonshotai/kimi-k2.5           │
│  [3] CODER → qwen3-coder-next (local) → Opus fallback  │
│  [4] VERA (Auditor) → claude-sonnet-4-6                │
│  [5] GARRO (Reviewer) → claude-opus-4-6 + vision       │
└─────────────────────────────────────────────────────────┘
```

### 11.2 Workflow

```
START
  ↓
GAHO plans iteration
  ↓
GARRO designs SwiftUI spec
  ↓
CODER implements 5 Swift files
  ↓
BUILDER writes files + builds + screenshots simulator
  ↓
VERA audits for security issues
  ↓
GARRO reviews screenshot vs spec, assigns confidence score
  ↓
  confidence >= 80% OR iteration >= 5?
    YES → FINAL REPORT → END
    NO  → loop back to GAHO
```

### 11.3 Cost Reduction

| Scenario | Cost/Run | Savings |
|----------|----------|---------|
| All Opus coder (baseline) | $7.98 | 0% |
| OpenRouter qwen coder | $1.02 | 87% |
| Local qwen coder (when working) | $0.25 | 97% |

**Current state (2026-03-24):** Local coder has zero-file bug → all runs use Opus fallback ($8/run). OpenRouter tier tested and ready to deploy.

---

## Summary

**LangGraph agent deployment is ideal when:**
- Multiple agents collaborate sequentially
- Shared state is complex (dicts, lists, metadata)
- You want single-log observability
- Cost tracking matters
- Transitions are frequent

**Use sub-agent spawns when:**
- Agents run independently in parallel
- Tasks are long (>5 min each)
- You need mixed runtimes (ACP + cloud)

**Best practice:** Start with nodes. If a node becomes a bottleneck (>5 min), refactor it to spawn sub-agents internally.

---

**Quick ref:** `langgraph-agent-pattern-quick-ref.md`  
**Live example:** `projects/eldrchat/langgraph-team-audit.py`

*Last updated: 2026-03-24*
