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

# ---------------- Target application under test ----------------
# Overridable so a demo can step aside when something else already owns 8000 on
# the presenter's machine. demo.py picks a free port automatically and exports
# TARGET_URL; the standalone scenario scripts read it from here.
TARGET_APP_PORT = int(os.environ.get("TARGET_APP_PORT", "8000"))
TARGET_URL = os.environ.get("TARGET_URL", f"http://127.0.0.1:{TARGET_APP_PORT}")
TARGET_HTML_FILE = os.environ.get("TARGET_HTML_FILE", "")  # e.g., "web.html"

# Absolute paths for data assets
FINGERPRINT_DIR = os.path.join(DATA_DIR, "fingerprints")
POMODORO_FINGERPRINTS_PATH = os.path.join(DATA_DIR, "pomodoro_3d_fingerprints.json")
ACTIVE_FINGERPRINT_PATH = POMODORO_FINGERPRINTS_PATH
# Which registered application the framework is currently operating on. Set by
# app_registry.activate(); empty until an app is registered (see app_registry).
ACTIVE_APP_ID = ""
METRICS_HISTORY_PATH = os.path.join(DATA_DIR, "metrics_history.json")

# Global threshold configuration policies
CONFIDENCE_THRESHOLD_HIGH = 75.0  # Automatic runtime healing threshold
CONFIDENCE_THRESHOLD_LOW = 20.0   # Minimum acceptable match score before system halt

# ---------------- Approval Workflow ----------------
# When enabled, healed locators are queued for human review instead of auto-applying.
# This is the industry best practice for safe script updates (Testim, Mabl, Healenium pattern).
APPROVAL_MODE_ENABLED = True  # Heals are queued for review; scripts are never edited silently

# ---------------- Git Integration ----------------
# When enabled, approved heals can automatically create git branches and PRs.
# This demonstrates DevOps integration and modern CI/CD workflow understanding.
GIT_INTEGRATION_ENABLED = False  # Set to True to enable automatic PR creation

# ---------------- Source-code self-healing (write-back) ----------------
# After a HIGH-confidence runtime heal, the wrapper writes the corrected locator
# back into the test/automation source so the stale selector is permanently fixed
# (see source_healer.py). Gated, idempotent, and reversible via per-file .bak.
# DISABLED BY DEFAULT. The framework repairs the EXECUTION of the test, never
# the test file: a repaired locator is reported to QA as a reviewable
# recommendation (see approval_workflow.py and report §1.4.1 / §3.4.3 Step 8).
# Silent rewriting of committed test code is the one behaviour a QA team cannot
# audit, so it is opt-in only.
SOURCE_HEAL_ENABLED = False
SOURCE_HEAL_TARGETS = []

# ---------------- Per-bucket atomic storage (see store.py) ----------------
# Each telemetry bucket lives in its own file under BUCKET_DIR and is written
# atomically under a cross-process lock with a rolling-window size cap.
BUCKET_DIR = os.path.join(DATA_DIR, "buckets")
BUCKETS = ["ui_heals", "infrastructure", "alerts", "browser_events", "source_heals", "drift"]
BUCKET_LIMITS = {
    "ui_heals": 200,
    "infrastructure": 200,
    "alerts": 200,
    "browser_events": 500,
    "source_heals": 100,
    "drift": 100,
}
BUCKET_DEFAULT_LIMIT = 200