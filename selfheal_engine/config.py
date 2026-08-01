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
# Default fingerprint path: use web_fingerprints.json which is the baseline for web.html
# This can be overridden from the dashboard (saved to data/config_override.json)
_default_fp = os.path.join(FINGERPRINT_DIR, "web_fingerprints.json")
ACTIVE_FINGERPRINT_PATH = _default_fp if os.path.exists(_default_fp) else POMODORO_FINGERPRINTS_PATH
METRICS_HISTORY_PATH = os.path.join(DATA_DIR, "metrics_history.json")

# Global threshold configuration policies
CONFIDENCE_THRESHOLD_HIGH = 75.0  # Automatic runtime healing threshold
CONFIDENCE_THRESHOLD_LOW = 20.0   # Minimum acceptable match score before system halt

# ---------------- Approval Workflow ----------------
# When enabled, healed locators are queued for human review instead of auto-applying.
# This is the industry best practice for safe script updates (Testim, Mabl, Healenium pattern).
APPROVAL_MODE_ENABLED = False  # Set to True to require approval before updating scripts

# ---------------- Git Integration ----------------
# ---------------- Source-code self-healing (write-back) ----------------
# After a HIGH-confidence runtime heal, the wrapper writes the corrected locator
# back into the test/automation source so the stale selector is permanently fixed
# (see source_healer.py). Gated, idempotent, and reversible via per-file .bak.
SOURCE_HEAL_ENABLED = True
SOURCE_HEAL_TARGETS = [
    os.path.join(BASE_DIR, "test_comprehensive.py"),
    os.path.join(BASE_DIR, "test_index.py"),
]

# ---------------- Find-elements healing default ----------------
# When True, find_elements() returning [] will be considered a failure signal
# and the healing engine will attempt to recover (use with caution).
# Can be overridden per-run via selfheal.install(heal_find_elements=...)
HEAL_FIND_ELEMENTS = True

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

# ── Auto-apply dashboard overrides at import time ────────────────────────────
# Any settings saved through the dashboard (data/config_override.json) take
# effect immediately in every process that imports this module — including
# demo_test.py — without requiring a manual apply_overrides() call.
def _apply_overrides_on_import():
    _override_path = os.path.join(DATA_DIR, "config_override.json")
    if not os.path.exists(_override_path):
        return
    try:
        import json as _json
        with open(_override_path, "r", encoding="utf-8") as _f:
            _ov = _json.load(_f)
    except Exception:
        return

    global SOURCE_HEAL_ENABLED, SOURCE_HEAL_TARGETS, CONFIDENCE_THRESHOLD_HIGH
    global CONFIDENCE_THRESHOLD_LOW, APPROVAL_MODE_ENABLED
    global ACTIVE_FINGERPRINT_PATH, POMODORO_FINGERPRINTS_PATH, TARGET_URL
    global TARGET_HTML_FILE, TARGET_APP_PORT

    if "source_heal_enabled" in _ov:
        SOURCE_HEAL_ENABLED = _ov["source_heal_enabled"]
    if "source_heal_targets" in _ov:
        SOURCE_HEAL_TARGETS = _ov["source_heal_targets"]
    if "confidence_threshold_high" in _ov:
        CONFIDENCE_THRESHOLD_HIGH = _ov["confidence_threshold_high"]
    if "confidence_threshold_low" in _ov:
        CONFIDENCE_THRESHOLD_LOW = _ov["confidence_threshold_low"]
    if "approval_mode_enabled" in _ov:
        APPROVAL_MODE_ENABLED = _ov["approval_mode_enabled"]
    if "active_fingerprint_path" in _ov:
        _fp = _ov["active_fingerprint_path"]
        if os.path.exists(_fp):
            ACTIVE_FINGERPRINT_PATH = _fp
            POMODORO_FINGERPRINTS_PATH = _fp  # keep alias in sync
    if "target_url" in _ov:
        TARGET_URL = _ov["target_url"]
    if "target_html_file" in _ov:
        TARGET_HTML_FILE = _ov["target_html_file"]
    if "target_app_port" in _ov:
        TARGET_APP_PORT = _ov["target_app_port"]

_apply_overrides_on_import()