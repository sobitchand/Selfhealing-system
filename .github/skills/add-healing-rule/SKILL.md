---
name: add-healing-rule
description: "Use when adding a new heuristic scoring rule (R5, R6, etc.) to the healing engine, adjusting rule weights, or modifying how candidates are scored. Covers editing healing_engine.py, updating weight constants, and validating the new rule against existing fingerprints."
argument-hint: "Describe the new rule: what element attribute it checks, how similarity should be measured, and the suggested weight (0.0–1.0)"
---

# Add Healing Rule

## When to Use
- Adding a new scoring dimension (e.g., R5: ARIA label match, R6: element position proximity)
- Rebalancing existing rule weights (R1–R4)
- Modifying how a specific rule measures similarity

## Key Files
- `demo/healing_engine.py` — rule calculation lives in `UIHeuristicEngine.evaluate_live_candidates()`
- `demo/dom_features.py` — DOM extraction utilities (xpath, neighbors); add new extractors here
- `demo/config.py` — weight constants if externalized; otherwise weights are inline in healing_engine.py
- `demo/data/pomodoro_3d_fingerprints.json` — golden baseline; new rule needs corresponding field added

## Current Rules (R1–R4)

| Rule | Field | Weight | Similarity Method |
|------|-------|--------|-------------------|
| R1 | `text` (inner text) | 40% | Gestalt `SequenceMatcher` |
| R2 | `xpath` (depth) | 30% | XPath depth delta |
| R3 | `classes` (CSS classes) | 20% | Set intersection ratio |
| R4 | `neighbors` (siblings) | 10% | Tag+text list comparison |

**Rule weights must sum to 1.0** across all active rules.

## Procedure

### Step 1 — Define the New Rule
Before editing code, clarify:
- **What DOM attribute** does R5 check? (e.g., `aria-label`, `name`, `role`, `data-testid`, pixel position)
- **How is similarity measured?** (exact match → 1.0 or 0.0 | string similarity | numeric proximity)
- **What weight?** (must reduce existing weights proportionally to keep total = 1.0)

### Step 2 — Add DOM Extraction (if needed)
If the new rule requires an attribute not already extracted:
1. Open `demo/dom_features.py`
2. Add extraction to the element scanning function (mirror the pattern used for `classes` or `neighbors`)
3. Ensure the extracted field is included in the candidate dict returned to `evaluate_live_candidates()`

### Step 3 — Add the Rule Calculation in healing_engine.py
1. Open `demo/healing_engine.py`
2. Find `evaluate_live_candidates()` — locate the R1–R4 block
3. Add the new rule following this pattern:
```python
# R5: <attribute> match (<weight * 100>%)
r5 = <similarity_function>(candidate.get("<field>", ""), fingerprint.get("<field>", ""))
score = r1 * 0.<r1_weight> + r2 * 0.<r2_weight> + r3 * 0.<r3_weight> + r4 * 0.<r4_weight> + r5 * 0.<r5_weight>
```
4. Update the existing weight multipliers so all weights still sum to 1.0
5. Add `r5` to the result dict returned per candidate (for dashboard display)

### Step 4 — Update Fingerprints
1. Open `demo/data/pomodoro_3d_fingerprints.json`
2. Add the new field to each fingerprint entry (use an empty string `""` or `[]` as default if unknown)
3. Optionally trigger re-learning to auto-populate real values: delete the file and re-run the demo

### Step 5 — Validate
1. Run the demo: `python demo/run_selenium_heal.py` (with `demo_target_app.py` running on port 8000)
2. Check dashboard Tab 1 — the new rule should appear in the R1-R4 breakdown chart
3. Verify confidence scores are reasonable (not inflated or collapsed by the new rule)

## Weight Rebalancing Example

Adding R5 at 10% by redistributing from R1 and R2:

| Rule | Before | After |
|------|--------|-------|
| R1 (text) | 0.40 | 0.35 |
| R2 (xpath) | 0.30 | 0.25 |
| R3 (classes) | 0.20 | 0.20 |
| R4 (neighbors) | 0.10 | 0.10 |
| R5 (new) | — | 0.10 |
| **Total** | **1.00** | **1.00** |

## Common Pitfalls
- Forgetting to rebalance weights → total > 1.0 → all confidence scores > 100%
- New field not present in fingerprint JSON → `KeyError` or always-0 score
- New DOM extraction not included in candidate dict → rule silently scores 0
