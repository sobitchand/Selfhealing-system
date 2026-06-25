import os
import sys

# Force UTF-8 console output so emoji-laden print() calls don't crash on the
# Windows cp1252 default codepage (UnicodeEncodeError). Imported by every entry
# point, so this fixes stdout process-wide.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base directory layout mapping
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Absolute paths for data assets
POMODORO_FINGERPRINTS_PATH = os.path.join(DATA_DIR, "pomodoro_3d_fingerprints.json")
METRICS_HISTORY_PATH = os.path.join(DATA_DIR, "metrics_history.json")

# Global threshold configuration policies
CONFIDENCE_THRESHOLD_HIGH = 75.0  # Automatic runtime healing threshold
CONFIDENCE_THRESHOLD_LOW = 20.0   # Minimum acceptable match score before system halt

# ---------------- Source-code self-healing (write-back) ----------------
# After a HIGH-confidence runtime heal, the wrapper writes the corrected locator
# back into the test/automation source so the stale selector is permanently fixed
# (see source_healer.py). Gated, idempotent, and reversible via per-file .bak.
SOURCE_HEAL_ENABLED = True
SOURCE_HEAL_TARGETS = [
    os.path.join(BASE_DIR, "run_selenium_heal.py"),
]

# ---------------- Per-bucket atomic storage (see store.py) ----------------
# Each telemetry bucket lives in its own file under BUCKET_DIR and is written
# atomically under a cross-process lock with a rolling-window size cap.
BUCKET_DIR = os.path.join(DATA_DIR, "buckets")
BUCKETS = ["ui_heals", "infrastructure", "alerts", "browser_events", "source_heals"]
BUCKET_LIMITS = {
    "ui_heals": 200,
    "infrastructure": 200,
    "alerts": 200,
    "browser_events": 500,
    "source_heals": 100,
}
BUCKET_DEFAULT_LIMIT = 200