---
description: "Use when editing healing_engine.py — adding or modifying heuristic scoring rules (R1-R4+), adjusting confidence thresholds, changing the infrastructure healer logic, or modifying how candidates are ranked and selected."
applyTo: "demo/healing_engine.py"
---

# Healing Engine — Modification Guidelines

## Rule Architecture

Rules are implemented inside `UIHeuristicEngine.evaluate_live_candidates()`. Each candidate is scored against a stored golden fingerprint using weighted similarity functions.

### Rule Calculation Pattern

```python
# R<N>: <attribute description> (<weight>%)
r_n = similarity_function(candidate.get("field"), fingerprint.get("field"))
```

All rule scores (`r1`–`r_n`) are floats in **[0.0, 1.0]**. The final score is a weighted sum:

```python
score = r1 * W1 + r2 * W2 + r3 * W3 + r4 * W4  # must sum to 1.0
```

**Rule weights MUST sum to exactly 1.0.** Verify with: `assert abs(W1+W2+W3+W4 - 1.0) < 1e-9`

## Current Rule Reference

| Rule | Field | Weight | Function |
|------|-------|--------|----------|
| R1 | `text` | 0.40 | `SequenceMatcher(None, a, b).ratio()` |
| R2 | `xpath` | 0.30 | depth-delta formula |
| R3 | `classes` | 0.20 | set intersection ratio |
| R4 | `neighbors` | 0.10 | list similarity |

## Confidence Routing

After scoring, the best candidate's score is compared against thresholds from `config.py`:

```python
if score >= CONFIDENCE_THRESHOLD_HIGH:   # 0.75
    # Auto-heal: reroute + patch source
elif score >= CONFIDENCE_THRESHOLD_LOW:  # 0.20
    # Cautious: reroute, flag for review
else:
    # Halt: raise alert, do not reroute
```

**Never hardcode 0.75 or 0.20 — always import from config.**

## Infrastructure Healer

`DynamicInfrastructureHealer.analyze_and_heal()` reads from `metrics_history.json` and executes recovery actions.

### Adding a New Recovery Action

1. Add the trigger condition in the `analyze_and_heal()` method
2. Define the recovery function — it must:
   - Log to `infrastructure` bucket via `append_to_bucket("infrastructure", {...})`
   - Be idempotent (safe to run multiple times)
   - Never block — all recovery must complete quickly or be offloaded
3. Add a corresponding alert to `alerts` bucket if the condition is critical

### Infrastructure Recovery Pattern

```python
def _handle_new_condition(self, metrics):
    action = "description of what was done"
    append_to_bucket("infrastructure", {
        "timestamp": time.time(),
        "trigger": "condition_name",
        "metric_value": metrics["relevant_field"],
        "action": action,
    })
```

## Intent-Aware Matching

The engine prevents two broken locators from healing to the same element. This is tracked via `_heal_registry` — a dict mapping `fingerprint_id → claimed_by_locator`.

When modifying candidate selection, **never remove this guard** — it prevents cascade misheals where multiple broken selectors all resolve to the most visually prominent element.

## Adding a Result Field for Dashboard

If your new rule produces a per-candidate score that should appear in the dashboard:
1. Add the field to the candidate result dict returned by `evaluate_live_candidates()`
2. Update `dashboard.py` Tab 1 to include the new column in the R1–R4 breakdown chart
