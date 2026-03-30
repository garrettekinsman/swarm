# PBAR Field Lessons

Lessons learned from running PBAR on real research tasks. Read before designing a new loop.

---

## Lesson 1: Branch Convergence Kills Coverage

**Source:** CA oil/diesel shortage research (2026-03-29)

In the first full LangGraph PBAR run, one branch type dominated by Gen 2 and never let go. The Hormuz/crude price angle scored 1.00 every generation because it had specific numbers (Brent $100.XX on March 8) and credible sources.

**Result:** All 4 branches converged on the crude price angle by Gen 3. The final report had a vague stockpile section with no actual inventory numbers — despite EIA PADD 5 days-of-supply data being publicly available and critical to the analysis.

**The irony:** A manual parallel search (Report 1) with hardcoded branch topics was more insightful than the "intelligent" PBAR run. Forced diversity > softmax-optimized coverage.

---

## Lesson 2: Locked Anchor Branches Fix This

**v2 fix:** Designate 1-2 branches as "anchors" with mandatory topic coverage. Anchors survive every softmax round regardless of score.

```python
# Before softmax selection:
anchors = [b for b in branches if b['id'] in ANCHOR_IDS]
floatable = [b for b in branches if b['id'] not in ANCHOR_IDS]

# Run softmax only on floatable branches
selected_floatable = softmax_select(floatable, temperature, n_select=max(0, 2 - len(anchors)))
selected = anchors + selected_floatable
```

**Real example anchors for supply chain research:**
- Anchor A: stockpile/inventory levels (EIA data, days-of-supply)
- Anchor B: refinery capacity (named facilities, throughput numbers)

These are "boring" topics that score 0.7 but are *necessary* for a complete analysis. Don't let softmax eliminate them.

---

## Lesson 3: Diversity Penalty Prevents Collapse

When 2 branches converge on the same topic cluster, penalize the duplicate before softmax:

```python
def apply_diversity_penalty(branches):
    clusters = cluster_by_topic(branches)
    for cluster in clusters:
        if len(cluster) > 1:
            # Keep highest scorer, penalize the rest
            cluster.sort(key=lambda b: b['score'], reverse=True)
            for dup in cluster[1:]:
                dup['score'] -= 0.2
    return branches
```

**The -0.2 penalty** is calibrated: enough to prevent duplicate selection without completely killing a valid branch. If the duplicate is genuinely scoring much higher (0.9 vs 0.5), it probably deserves selection anyway.

---

## Lesson 4: Coverage Check After Gen 5

Even with anchors and diversity penalty, gaps can slip through. After the final generation, do an explicit coverage audit before synthesis:

```python
REQUIRED_TOPICS = [
    "stockpile_levels",
    "refinery_capacity", 
    "current_prices",
    "supply_chain_disruption"
]

covered = assess_coverage(all_branch_results, REQUIRED_TOPICS)
gaps = [t for t in REQUIRED_TOPICS if not covered[t]]

for gap in gaps:
    # Force a targeted search to fill the gap
    gap_result = web_search(build_gap_query(gap, topic))
    all_branch_results.append(gap_result)
```

This adds at most 4 extra searches at the end — cheap insurance against a hollow report.

---

## Lesson 5: Report 1 (Manual) Beat Report 2 (PBAR)

**The uncomfortable truth from CA oil research:**

| Metric | Report 1 (Manual Parallel) | Report 2 (LangGraph PBAR) |
|--------|---------------------------|--------------------------|
| SPR data | 415M bbl, 64 days coverage | Vague/missing |
| CA structural deficit | 23M bbl/year | Not mentioned |
| Refinery capacity table | Specific, named facilities | Absent |
| Price specificity | Named exec quotes, exact dates | Generic headlines |
| Coverage | All 4 required topics | 2/4 required topics |

Report 1 was produced by manually assigning one agent per topic (no softmax). Report 2 was "smarter" but converged on what's exciting rather than what's complete.

**Takeaway:** PBAR's intelligence is only as good as its incentive structure. Without explicit coverage constraints, it will optimize for dramatic specificity at the expense of boring-but-critical data.

---

## Lesson 6: 5 Generations Is the Right Budget

- **3 gens**: Too shallow. Temperature only anneals to 0.72 — still in high-exploration territory. Doesn't develop the branch evolution meaningfully.
- **5 gens**: Sweet spot. Full annealing cycle. Enough for mutant branches to prove themselves.
- **7+ gens**: Diminishing returns past Gen 5 on most research topics. Better to run a second loop on a different angle.

---

## Lesson 7: Mutant Branches Find Non-Obvious Signals

In the CA oil run, the highest-value signal came from a *mutant* branch, not the original seed:

- Original: "California fuel prices Brent crude"
- Mutant (cross-pollinated): "Valero Benicia refinery California fuel margin premium"
- Result: Found the Valero +$1.21/gal margin estimate by August — one of the most actionable findings

**Don't skip mutation.** The cross-pollination of query elements is where PBAR earns its keep.

---

## Huawei Ternary Chip Research (2026-03-29)

A second PBAR run on Huawei's ternary chip architecture confirmed the convergence pattern:

- **Early convergence:** TSMC export control angle dominated by Gen 2 (geopolitically dramatic)
- **Missed:** Actual power efficiency benchmarks for ternary logic vs CMOS
- **Fix applied:** Locked "efficiency_benchmarks" as anchor branch
- **Outcome:** Recovered the technical comparison data that softmax had eliminated

This confirmed: **the fix works**. Locked anchors successfully prevented the geopolitical drama from crowding out the technical specs.
