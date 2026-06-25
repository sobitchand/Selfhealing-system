"""
One-click teacher demo: watch the source code heal itself.

Runs the full story with paced gates so an audience can read each stage:
  re-arm (break it) -> show broken source line -> run real self-heal ->
  show the source line REWROTE itself on disk -> point at dashboard evidence.

Usage:
  python demo_show.py          # full demo (re-arm, then heal, then show diff)
  python demo_show.py --reset  # only re-arm (restore broken locator); no heal

Standard library only. Paths come from config so nothing is hardcoded.
"""

import os
import re
import sys
import json
import time
import shutil
import subprocess
import urllib.request

import config

PY = sys.executable  # same interpreter that launched this script
TARGET_URL = "http://127.0.0.1:8000"
DASHBOARD_URL = "http://localhost:8501"
LOCATOR_RE = re.compile(r"^.*BROKEN_LOCATOR\s*=.*$", re.MULTILINE)


# --------------------------- pretty printing ---------------------------
def banner(title):
    line = "=" * 64
    print(f"\n{line}\n  {title}\n{line}")


def gate(msg):
    try:
        input(f"\n>>> {msg} (press Enter) ")
    except EOFError:
        pass  # non-interactive run: just continue


def locator_line(path):
    """Return the BROKEN_LOCATOR line from a source file, or '' if absent."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            m = LOCATOR_RE.search(f.read())
        return m.group(0).strip() if m else ""
    except OSError:
        return ""


# --------------------------- demo steps ---------------------------
def rearm():
    """Restore every target's .bak so the locator is guaranteed broken again."""
    restored = 0
    for path in config.SOURCE_HEAL_TARGETS:
        bak = path + ".bak"
        if os.path.exists(bak):
            shutil.copy2(bak, path)
            restored += 1
    return restored


def target_is_up():
    try:
        with urllib.request.urlopen(TARGET_URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_target_app():
    """Return (proc_or_None). Starts demo_target_app.py if :8000 is down."""
    if target_is_up():
        print("Target app already running at " + TARGET_URL)
        return None
    print("Starting target app (demo_target_app.py)...")
    app = os.path.join(config.BASE_DIR, "demo_target_app.py")
    proc = subprocess.Popen([PY, app], cwd=config.BASE_DIR)
    for _ in range(20):
        if target_is_up():
            print("Target app is up.")
            return proc
        time.sleep(0.5)
    print("WARNING: target app did not come up in time; demo may fail.")
    return proc


def run_heal():
    script = os.path.join(config.BASE_DIR, "run_selenium_heal.py")
    return subprocess.run([PY, script], cwd=config.BASE_DIR).returncode


def latest_source_heal():
    path = os.path.join(config.BUCKET_DIR, "source_heals.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = json.load(f)
        return rows[-1] if rows else None
    except Exception:
        return None


# --------------------------- orchestration ---------------------------
def do_reset():
    banner("RE-ARM ONLY")
    n = rearm()
    print(f"Restored {n} source file(s) to the BROKEN state.")
    for path in config.SOURCE_HEAL_TARGETS:
        print(f"  {os.path.basename(path)}: {locator_line(path)}")
    print("\nReady for another demo run: python demo_show.py")


def do_demo():
    primary = config.SOURCE_HEAL_TARGETS[0]
    name = os.path.basename(primary)

    banner("STEP 1  —  THE SOURCE IS BROKEN ON PURPOSE")
    rearm()
    before = locator_line(primary)
    print(f"File: {name}")
    print(f"  {before}")
    print("\nThis locator points at an element id that does NOT exist on the page.")
    print("A normal test would crash here with NoSuchElementException.")

    gate("Run the real self-healing test now")

    banner("STEP 2  —  RUN THE SELF-HEALING TEST (real headless Chrome)")
    app_proc = ensure_target_app()
    rc = run_heal()

    banner("STEP 3  —  THE SOURCE FILE REWROTE ITSELF")
    after = locator_line(primary)
    print(f"File: {name}")
    print(f"  BEFORE : {before}")
    print(f"  AFTER  : {after}")
    if before != after:
        print("\n>>> The source code on disk changed. The broken locator self-repaired. <<<")
    else:
        print("\n(No change detected — confidence below threshold, source left untouched.)")

    row = latest_source_heal()
    if row:
        print("\nSource-heal log row (data/buckets/source_heals.json):")
        print(f"  {row.get('broken_token')}  ->  {row.get('healed_token')}"
              f"   in {row.get('file')}   ({row.get('occurrences')}x)")

    banner("STEP 4  —  SEE IT ON THE DASHBOARD")
    print(f"Open: {DASHBOARD_URL}")
    print("  Tab 'UI Heuristic Healing'  -> the heal + confidence score")
    print("  Tab 'Source Code Heals'     -> the write-back row above")
    print("\nProof it is permanent: run 'python run_selenium_heal.py' again —")
    print("the locator is valid now, so NO heal fires.")
    print("\nRepeat the demo:  python demo_show.py        (auto re-arms first)")
    print("Re-arm only:      python demo_show.py --reset")

    if app_proc is not None:
        print("\n(Note: this script started the target app; close this window to stop it,")
        print(" or leave it running so the dashboard keeps showing live telemetry.)")

    return 0 if rc == 0 else rc


def main():
    if "--reset" in sys.argv:
        do_reset()
        return 0
    return do_demo()


if __name__ == "__main__":
    sys.exit(main())
