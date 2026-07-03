---
name: debug-heal-failure
description: "Use when a self-heal produced a wrong element, failed with low confidence, locked a locator, or threw an unexpected error. Step-by-step checklist to diagnose heal failures using JSON telemetry buckets, fingerprint comparison, and feedback loop state."
argument-hint: "Paste the broken locator string or describe the symptom (wrong element, low confidence, locked, crashed)"
---

# Debug Heal Failure

## When to Use
- A heal fired but clicked/interacted with the wrong element
- Confidence was unexpectedly low (below 75% or below 20%)
- The locator is "locked" and the feedback loop is blocking all further heals
- A `NoSuchElementException` was NOT healed even though a matching element exists
- Source patching didn't happen after a high-confidence heal

## Diagnostic Files

| File | Contains |
|------|---------|
| `demo/data/buckets/ui_heals.json` | Every heal attempt: locator, candidates, R1–R4 scores, confidence, outcome |
| `demo/data/buckets/alerts.json` | Escalations, critical failures, locked locators |
| `demo/data/buckets/source_heals.json` | Source patch history (file, old→new token, timestamp) |
| `demo/data/pomodoro_3d_fingerprints.json` | Golden fingerprints (baseline truth) |
| `demo/data/heal_state.json` | Feedback loop state: consecutive failures, locked locators |
| `demo/data/metrics_history.json` | Infrastructure metrics at time of failure |

## Checklist

### 1. Confirm the Heal Attempt Was Logged
- Open `demo/data/buckets/ui_heals.json`
- Find the entry by `locator` value and timestamp
- If **not present**: the exception may not have reached `SelfHealingWebDriver` — check that the test uses `automation_wrapper.py`'s `SelfHealingWebDriver`, not raw Selenium

### 2. Check Confidence and Outcome
From the heal log entry:
- `confidence >= 0.75` → should have auto-healed; if not, check `outcome` field for errors
- `0.20 <= confidence < 0.75` → cautious heal; element was rerouted but flagged
- `confidence < 0.20` → halted; check `alerts.json` for escalation entry
- `outcome: "wrong_element"` → top candidate was incorrect; go to Step 4

### 3. Check the Feedback Loop State
- Open `demo/data/heal_state.json`
- Find the entry for the failing locator
- `consecutive_failures >= 3` → locator is **locked** — healing is blocked
- **Fix**: Delete the locator's entry from `heal_state.json` to unlock it

### 4. Compare R1–R4 Scores Against the Fingerprint
From the heal log, note the per-rule scores. Then open `demo/data/pomodoro_3d_fingerprints.json`:

| Rule | Low Score Means... | Common Fix |
|------|-------------------|------------|
| R1 (text) near 0 | Button text changed in the app | Update fingerprint `text` field |
| R2 (xpath) near 0 | DOM structure was significantly restructured | Re-learn fingerprint with Learning Mode |
| R3 (classes) near 0 | CSS class names were refactored | Update fingerprint `classes` field |
| R4 (neighbors) near 0 | Surrounding elements changed | Update fingerprint `neighbors` field |

If **all rules are low**, the fingerprint is stale — trigger full re-learning.

### 5. Check for Source Patching
- Open `demo/data/buckets/source_heals.json`
- If a high-confidence heal happened but no source patch: check `config.py` for `SOURCE_HEAL_ENABLED` (must be `True`) and `SOURCE_HEAL_TARGETS` (must include the test file path)

### 6. Check Alerts for Escalations
- Open `demo/data/buckets/alerts.json`
- Look for entries with `severity: "CRITICAL"` near the failure timestamp
- These indicate the feedback loop escalated after repeated failures

## Fix Actions

### Unlock a Locked Locator
Edit `demo/data/heal_state.json` — remove or reset the entry for the locked locator:
```json
{ "locator_value": { "consecutive_failures": 0, "locked": false } }
```

### Fix a Stale Fingerprint
1. Open `demo/data/pomodoro_3d_fingerprints.json`
2. Find the entry for the element
3. Update the stale field (text, classes, xpath, or neighbors)
4. Or delete the entire entry and trigger re-learning by re-running the demo

### Re-enable Source Patching
In `demo/config.py`:
```python
SOURCE_HEAL_ENABLED = True
SOURCE_HEAL_TARGETS = ["path/to/your_test.py"]  # add the test file
```

### Reset the Entire Demo State
```bash
cd demo
python demo_show.py --reset   # restores .bak files and clears heal state
```

## Output Format

After running through this checklist, provide:
1. **Root Cause**: Which step identified the issue
2. **Evidence**: Specific values from the JSON files
3. **Fix**: Exact file edits or commands to resolve
