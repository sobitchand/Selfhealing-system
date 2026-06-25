"""
Learning Mode (proposal §3.3 Step 1, §3.4.2, Fig 3.4).

The system maps the application UI BEFORE any failure. If no baseline fingerprint
metadata exists, it auto-enters Learning Mode: scan the live AUT, capture a Golden
Fingerprint for every interactive element, and persist it. Healing Mode can then
compare against this baseline. This also covers the "Database Recovery" test
(§3.8.3): delete the fingerprint JSON and it rebuilds itself on the next run.
"""

import os
import json

from fingerprint_manager import FingerprintManager


def _has_baseline(fingerprint_path):
    """True when a non-empty fingerprint registry already exists."""
    try:
        if os.path.getsize(fingerprint_path) <= 0:
            return False
        with open(fingerprint_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return isinstance(data, dict) and len(data) > 0
    except Exception:
        return False


def ensure_fingerprints(driver, fingerprint_path):
    """Auto-bootstrap the baseline if missing. Returns True if it ran Learning
    Mode, False if a baseline already existed (no-op)."""
    if _has_baseline(fingerprint_path):
        return False
    print("🧠 No baseline fingerprints found — entering LEARNING MODE...")
    manager = FingerprintManager(driver, fingerprint_path=fingerprint_path)
    manager.scan_interactive()
    print("✅ Baseline reference created. Proceeding to monitoring/healing.")
    return True
