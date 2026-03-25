# LangGraph Agent Deployment — Quick Reference

**Pattern:** Deploy agents as LangGraph nodes instead of spawning sub-agent sessions.

---

## When to Use

| Use Case | LangGraph Nodes | Sub-Agent Spawns |
|----------|-----------------|------------------|
| Sequential workflow, shared state | ✅ Perfect | ❌ Too much overhead |
| Parallel independent tasks | ⚠️ Possible | ✅ Better isolation |
| Long-running (>5 min per agent) | ⚠️ Blocks workflow | ✅ Background execution |
| Mixed runtimes (ACP + cloud) | ❌ Can't mix | ✅ Each picks runtime |

**Rule:** Tight collaboration → nodes. Independent parallel → spawns.

---

## Framework1 Scheduling Constraint

**Framework1 = single-inference bottleneck.** Only one model runs at a time (qwen3-coder-next uses 100% GPU).

```python
# ❌ BAD: Parallel local tasks (they queue serially → 15+ min total)
for i in range(5):
    dispatch(role="coder", prompt=f"Implement component {i}")

# ✅ GOOD: Light tasks local, heavy tasks cloud
def route_task(task):
    if task.est_tokens < 2000:  # Light task
        return dispatch(role="coder-fast", prompt=task.spec)  # gpt-oss:20b, fast
    else:
        return call_claude(task.spec, "claude-opus-4-6")  # Cloud, parallel-safe
```

**Include in orchestrator system prompt:**
```python
FRAMEWORK1_CONSTRAINT = """
Framework1 runs ONE inference at a time (qwen3-coder-next = 61GB, 100% GPU).
Tasks queue serially. Keep local tasks light (<2 min). Heavy tasks → cloud.
"""
```

---

## Core Pattern (4 Steps)

### 1. Define Models
```python
MODEL_GAHO = "claude-opus-4-6"
MODEL_GARRO = "moonshotai/kimi-k2.5"
MODEL_CODER = "coder"  # Model router role
MODEL_VERA = "claude-sonnet-4-6"
```

### 2. Create Node Functions
```python
def node_garro_design(state: TeamState) -> dict:
    """GARRO agent — design SwiftUI spec."""
    response = call_openrouter(
        system="You are GARRO, SwiftUI expert.",
        user=build_prompt(state),
        model=MODEL_GARRO
    )
    # Return ONLY changed keys (LangGraph merges)
    return {"design_spec": response}
```

### 3. Build Graph
```python
from langgraph.graph import StateGraph, END

graph = StateGraph(TeamState)
graph.add_node("gaho", node_gaho_plan)
graph.add_node("garro", node_garro_design)
graph.add_node("coder", node_coder_implement)

graph.set_entry_point("gaho")
graph.add_edge("gaho", "garro")
graph.add_edge("garro", "coder")
graph.add_edge("coder", END)

app = graph.compile()
```

### 4. Run
```python
initial_state = {
    "iteration": 0,
    "design_spec": "",
    "current_code": {}
}
final_state = app.invoke(initial_state)
```

---

## Critical Rules

### State Management
```python
# ✅ CORRECT — return only changed keys
def node_example(state):
    return {"new_field": "value"}

# ❌ WRONG — causes stale merge
def node_example(state):
    return {**state, "new_field": "value"}
```

### Initialization
```python
# Initialize ALL TeamState fields at start
class TeamState(TypedDict):
    iteration: int
    design_spec: str
    current_code: Dict[str, str]

initial_state = {
    "iteration": 0,
    "design_spec": "",      # ← Don't skip
    "current_code": {}      # ← Don't skip
}
```

---

## API Helpers

### OpenRouter
```python
def call_openrouter(system: str, user: str, model: str, max_tokens: int = 2048):
    from openai import OpenAI
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

### Model Router
```python
def call_model_router(role: str, prompt: str, timeout: int = 180):
    import subprocess
    result = subprocess.run(
        ["bash", "projects/model-router/scripts/dispatch.sh",
         "--role", role, "--prompt", prompt],
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip()
```

### Anthropic
```python
def call_claude(prompt: str, model: str, max_tokens: int = 2048):
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
```

---

## Adding a New Agent

**Example:** Add TESTER agent for syntax validation

```python
# 1. Define model
MODEL_TESTER = "claude-haiku-4-2"

# 2. Create node
def node_tester_validate(state: TeamState) -> dict:
    issues = []
    for filename, code in state["current_code"].items():
        result = subprocess.run(
            ["swiftc", "-parse", "-"],
            input=code, capture_output=True, text=True
        )
        if result.returncode != 0:
            issues.append(f"{filename}: {result.stderr}")
    return {"syntax_issues": issues, "syntax_valid": len(issues) == 0}

# 3. Update TeamState
class TeamState(TypedDict):
    # ... existing
    syntax_issues: List[str]
    syntax_valid: bool

# 4. Add to graph
graph.add_node("tester", node_tester_validate)
graph.add_edge("coder", "tester")
graph.add_edge("tester", "builder")

# 5. Initialize
initial_state = {"syntax_issues": [], "syntax_valid": False, ...}
```

---

## Benefits vs Sub-Agent Spawns

| Aspect | Nodes | Spawns |
|--------|-------|--------|
| Transitions | Instant | 1-2s spawn overhead |
| Logs | Single file | Scattered |
| State | Shared dict | Message passing |
| Model assignment | Direct per node | Inherit or override |
| Debugging | Easy trace | Multi-session complexity |

---

## Cost Tracking

```python
def node_example(state: TeamState) -> dict:
    response = call_model(...)
    
    usage = state.get("usage", [])
    usage.append({
        "agent": "EXAMPLE",
        "model": MODEL_EXAMPLE,
        "tokens_in": len(prompt.split()),
        "tokens_out": len(response.split()),
        "cost_usd": calculate_cost(...)
    })
    
    return {"output": response, "usage": usage}

# Final report
def node_final(state: TeamState) -> dict:
    total_cost = sum(u["cost_usd"] for u in state["usage"])
    print(f"💰 Total: ${total_cost:.4f}")
    return {}
```

---

**Full guide:** `langgraph-agent-pattern-extended.md`  
**Live example:** `projects/eldrchat/langgraph-team-audit.py`

*Last updated: 2026-03-24*
