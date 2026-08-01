"""
One-command demo reset. Run this right before presenting to judges.

What it does (all idempotent, safe to run repeatedly):
  1. Clears every telemetry bucket (ui_heals, infrastructure, alerts,
     browser_events, source_heals) to an empty list, so the dashboard starts
     clean and the audience watches it fill LIVE.
  2. Truncates metrics_history.json so the infra pulse starts fresh.
  3. Re-arms the source-heal demo: restores run_selenium_heal.py from its .bak
     so BROKEN_LOCATOR is the broken `old-start-btn` again (ready to self-heal).

Usage:
  python reset_demo.py            # full clean + re-arm
  python reset_demo.py --keep-history   # clean buckets but keep metrics history
"""

import json
import os
import shutil
import sys

import config


def _write_empty(path, value):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2)
    os.replace(tmp, path)


def clear_buckets():
    os.makedirs(config.BUCKET_DIR, exist_ok=True)
    for bucket in config.BUCKETS:
        path = os.path.join(config.BUCKET_DIR, f"{bucket}.json")
        _write_empty(path, [])
        print(f"  cleared bucket: {bucket}")


def clear_history():
    _write_empty(config.METRICS_HISTORY_PATH, [])
    print("  cleared metrics_history.json")


def clear_heal_state():
    """Wipe the feedback-loop lock store (data/heal_state.json). Without this a
    locator that failed FAIL_THRESHOLD times in a prior session stays 'locked',
    so Case E would show the 'repeated failures' halt instead of the scripted
    fresh 0.0%-confidence safe-halt. Clearing it re-arms the safety-gate demo."""
    path = os.path.join(config.DATA_DIR, "heal_state.json")
    _write_empty(path, {})
    print("  cleared heal_state.json (feedback locks reset)")


def rearm_source():
    restored = 0
    for path in config.SOURCE_HEAL_TARGETS:
        bak = path + ".bak"
        if os.path.exists(bak):
            shutil.copy2(bak, path)
            restored += 1
            print(f"  re-armed (broken locator restored): {os.path.basename(path)}")
    if restored == 0:
        print("  no .bak files found to re-arm (source already in baseline state)")


def main():
    print("=== DEMO RESET ===")
    clear_buckets()
    if "--keep-history" not in sys.argv:
        clear_history()
    clear_heal_state()
    rearm_source()
    print("Done. Dashboard is clean; source-heal target is armed.")
    print("Start order: dashboard -> collector -> target app -> run the cases.")


if __name__ == "__main__":
    main()
