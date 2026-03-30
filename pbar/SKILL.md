---
name: pbar
description: Population-Based Annealed Research (PBAR) — autonomous AI-driven research loop. Runs parallel research branches, applies softmax selection with temperature annealing, and iterates over 5 generations. Use when asked to run autonomous research loops, deep-dive investigations, or any multi-angle research task requiring sustained iteration.
license: MIT
---

# PBAR — Research Loop Skill

## Workflow

1. **Spawn as subagent** — never run from main session
2. **Seed 4 branches** — diverse angles on the topic (supply chain, prices, policy, infrastructure, etc.)
3. **Run 5 generations** — search → score → softmax select → evolve → repeat
4. **Heartbeat after each gen** — send progress ping to requester
5. **Synthesize** — collect best signals, write final report

## Running a Loop

Spawn as subagent with the full LangGraph StateGraph schema in the task prompt:

```python
sessions_spawn(
    task="[PBAR task — include StateGraph schema, node responsibilities, heartbeat format]",
    label="pbar-<topic>",
    runtime="subagent",
    model="anthropic/claude-sonnet-4-6"
)
```

Key elements to include in the task prompt:
1. Full StateGraph schema (see `references/` or `pbar-langgraph.py`)
2. Node responsibilities (explicit, not vague)
3. Heartbeat format + target sessionKey
4. Brave API key location (`~/.openclaw/secrets.env`)
5. Output paths (script + report)
6. Prior context to seed Gen 1

## v2 Improvements

### Locked Anchor Branches

1-2 branches with mandatory topic coverage that cannot be eliminated by softmax regardless of score:

```python
ANCHOR_BRANCHES = ["stockpile_levels", "refinery_capacity"]  # always survive
FLOATABLE_BRANCHES = ["price_signals", "supply_chain"]       # subject to softmax
```

This fixes the critical flaw where pure PBAR eliminates "boring but critical" topics (e.g., EIA inventory data) in favor of dramatic headlines.

### Diversity Penalty

If 2+ branches in same topic cluster, penalize duplicate:

```python
if same_cluster(branch_a, branch_b):
    branch_b['score'] -= 0.2  # diversity penalty
```

### Dual Scoring

Score separately for **specificity** (numbers, dates, named sources) AND **topic coverage** (does it address a must-have angle?). Take weighted average.

### Coverage Check

After Gen 5, verify mandatory topics are covered before synthesizing. Force targeted searches to fill any gaps:

```python
REQUIRED_TOPICS = ["stockpiles", "refinery_capacity", "prices", "supply_chain"]
gaps = [t for t in REQUIRED_TOPICS if not covered(t, all_results)]
if gaps:
    for gap in gaps:
        results[gap] = web_search(gap_query(gap))
```

## Heartbeat Format

Send after scoring each generation:

```
[PBAR LG] Gen {gen}/5 | Temp {temp:.2f} | Top: {branch_id} ({score:.2f}) | {one_line_finding}
```

Target: your requester's sessionKey.

## Budget

- ~$0.15–0.18/sprint
- 5 generations ≈ $0.75 total
- Branch generation: Brave API (free tier) or web_search fallback

## State Schema

```python
class BranchState(TypedDict):
    topic: str
    generation: int
    max_generations: int      # 5
    temperature: float        # annealing: 2.0 → 1.2 → 0.72 → 0.43 → 0.26
    branches: List[dict]      # [{id, query, result, score}, ...]
    selected: List[dict]      # top 2 after softmax
    evolved: List[dict]       # 4 new branches after recombination
    report: Optional[str]
    done: bool
```

## Critical Lesson

**Pure annealing converges on excitement, not coverage.** Use locked anchor branches for any research topic with mandatory coverage requirements (financial data, inventory levels, etc.). See `PATTERNS.md`.
