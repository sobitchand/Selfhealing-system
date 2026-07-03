---
description: "Use when writing or modifying any Python file in this self-healing system. Covers project-specific conventions: atomic JSON writes via store.py, config constants, bucket structure, filelock patterns, and how to extend the system safely."
applyTo: "demo/**/*.py"
---

# Self-Healing System — Python Conventions

## Telemetry Storage (store.py)

**Always use `store.py` to write to telemetry buckets — never write raw JSON directly.**

```python
from store import append_to_bucket

# Correct: use the store API
append_to_bucket("ui_heals", {"locator": ..., "confidence": ..., "timestamp": ...})

# Wrong: don't write directly to JSON files
with open("data/buckets/ui_heals.json", "w") as f:
    json.dump(data, f)
```

Bucket names are defined in `config.py` as `BUCKET_*` constants. Valid buckets:
- `ui_heals` — heal attempt logs (200-entry rolling limit)
- `infrastructure` — infra recovery actions (200-entry limit)
- `alerts` — critical escalations (200-entry limit)
- `browser_events` — raw browser telemetry (500-entry limit)
- `source_heals` — source patch history (100-entry limit)

## Configuration Constants

**Always read from `config.py` — never hardcode thresholds or paths.**

```python
from config import (
    CONFIDENCE_THRESHOLD_HIGH,   # 0.75 — auto-heal
    CONFIDENCE_THRESHOLD_LOW,    # 0.20 — cautious / halt boundary
    SOURCE_HEAL_ENABLED,         # bool
    SOURCE_HEAL_TARGETS,         # list of file paths
    FINGERPRINT_FILE,            # path to pomodoro_3d_fingerprints.json
    METRICS_HISTORY_FILE,        # path to metrics_history.json
)
```

## Filelock Pattern

All JSON data files use `filelock` for cross-process safety. Match this pattern when adding new persistent files:

```python
from filelock import FileLock

lock = FileLock(f"{file_path}.lock")
with lock:
    with open(file_path, "r") as f:
        data = json.load(f)
    # mutate data
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)
```

## Atomic Writes

For files that multiple processes read (metrics, fingerprints), use write-then-rename for atomicity:

```python
import os, json, tempfile

def atomic_write_json(path, data):
    dir_ = os.path.dirname(path)
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as f:
        json.dump(data, f, indent=2)
        tmp = f.name
    os.replace(tmp, path)  # atomic on POSIX; near-atomic on Windows
```

## DOM Feature Extraction

Use utilities from `dom_features.py` — don't reimplement XPath or neighbor extraction:

```python
from dom_features import get_xpath, get_neighbors

xpath = get_xpath(driver, element)
neighbors = get_neighbors(element)
```

## Extending the System

### Adding a New Bucket
1. Add `BUCKET_<NAME> = "new_name"` to `config.py`
2. Add the bucket path to the bucket map in `store.py`
3. Use `append_to_bucket("new_name", {...})` in your code

### Adding a New Metric
1. Capture the metric in `selfhealing/metrics_monitor.py` inside the collection loop
2. Add the field to the metrics dict written to `metrics_history.json`
3. Add threshold check + recovery action in `healing_engine.py`'s `DynamicInfrastructureHealer`

### Modifying Confidence Thresholds
Only change values in `config.py` — never inline threshold literals elsewhere in the code.

## Error Handling

- **Source healer** (`source_healer.py`): must be best-effort — catch all exceptions, log, never raise
- **Metrics monitor** (`metrics_monitor.py`): must be resilient — catch exceptions in the background thread loop
- **Handlers** (`handlers.py`): active heal path exceptions propagate to Selenium; passive path must swallow and log
