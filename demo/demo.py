"""
The whole demonstration, in one command.

    python demo.py

Starts the application under test, then runs the SAME unmodified QA suite twice
against the SAME refactored build:

    1. baseline  -- stock Selenium. The locators have rotted; the suite fails.
    2. healed    -- identical suite, with the rule-based self-healing layer
                    installed via `selfheal.install()`. It recovers.

The test files, the page objects and the application are byte-identical between
the two runs. The only variable is whether the healing layer is installed, which
is what makes the result evidence rather than a demo.

Options:
    --headed      watch Chrome do it
    --dashboard   also launch the Streamlit dashboard
    --break MODE  fault to inject (default: refactor)
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import config  # noqa: F401  (forces UTF-8 stdout on Windows consoles)

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DEMO_DIR, "tests", "runner.py")
APP = os.path.join(DEMO_DIR, "demo_target_app.py")
RESULT_MARKER = "##SELFHEAL_RESULT##"

# A marker only our page carries, used to tell our application apart from
# whatever else might be listening on the port.
APP_FINGERPRINT = "Pomodoro 3D Focus Timer"
PORT_CANDIDATES = [8000, 8010, 8020, 8030]

RULE = "─" * 78


def port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def is_our_app(port):
    """True only if the thing on `port` is the Pomodoro application. Checking
    that the port is merely OPEN is not enough -- an unrelated dev server
    squatting on 8000 would silently become the application under test, and the
    suite would fail for reasons that have nothing to do with healing."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
            return APP_FINGERPRINT in response.read(8192).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_for_app(port, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_our_app(port):
            return True
        time.sleep(0.3)
    return False


def run_suite(label, extra_args, headed):
    """Run the QA suite in a clean subprocess and return its result payload."""
    cmd = [sys.executable, RUNNER, "--quiet"] + extra_args
    if headed:
        cmd.append("--headed")
    print(f"   running {label} suite...", flush=True)
    proc = subprocess.run(cmd, cwd=DEMO_DIR, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_MARKER):
            return json.loads(line[len(RESULT_MARKER):])
    print(f"❌ {label} run produced no result.\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    sys.exit(1)


def render(title, payload, show_heals):
    print(f"\n{RULE}\n  {title}\n{RULE}")
    for test in payload["tests"]:
        mark = "✅ PASS" if test["passed"] else "❌ FAIL"
        print(f"  {mark}  {test['name']:<45} {test['seconds']:>5.2f}s")
        if not test["passed"]:
            print(f"           └─ {test['error']}")
        if show_heals:
            if test["heals"]:
                for heal in test["heals"]:
                    target = f"<{heal['resolved_tag']}> \"{heal['resolved_text']}\"" \
                        if heal.get("resolved_tag") else heal["resolved_to"]
                    print(f"           └─ healed {heal['locator']} → {target}"
                          f"   {heal['confidence']}% · {heal['policy']} · {heal['ms']}ms")
            elif test["passed"]:
                print("           └─ no heal needed")
    passed, total = payload["passed"], payload["total"]
    print(f"{RULE}\n  RESULT: {passed}/{total} passed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="run Chrome visibly")
    ap.add_argument("--dashboard", action="store_true", help="launch the Streamlit dashboard too")
    ap.add_argument("--break", dest="break_mode", default="refactor",
                    help="fault to inject: refactor (default) | css | id | attr | all")
    args = ap.parse_args()

    spawned = []

    print(f"\n{RULE}\n  SELF-HEALING QA LAYER — baseline vs healed\n{RULE}")

    # The three-strike loop guard persists to disk on purpose, so it survives
    # across runs. That means a previous BAD run (wrong app on the port, target
    # down) can leave a locator locked and silently sabotage the demo. Clear it.
    heal_state = os.path.join(DEMO_DIR, "data", "heal_state.json")
    if os.path.exists(heal_state):
        os.remove(heal_state)
        print("   cleared the loop-guard state from previous runs")

    # ---- application under test -------------------------------------------
    port = next((p for p in PORT_CANDIDATES if is_our_app(p)), None)
    if port:
        print(f"   application under test: already running on :{port}")
    else:
        free = next((p for p in PORT_CANDIDATES if not port_open(p)), None)
        if free is None:
            print(f"❌ every candidate port is taken by something else: {PORT_CANDIDATES}")
            sys.exit(1)
        if free != PORT_CANDIDATES[0]:
            print(f"   :{PORT_CANDIDATES[0]} is in use by another application; "
                  f"using :{free} instead")
        print(f"   starting application under test on :{free} ...")
        spawned.append(subprocess.Popen(
            [sys.executable, APP, str(free)], cwd=DEMO_DIR,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        if not wait_for_app(free):
            print(f"❌ target application did not come up on :{free}")
            sys.exit(1)
        port = free

    base_url = f"http://127.0.0.1:{port}"
    broken_url = f"{base_url}/?break={args.break_mode}"

    if args.dashboard and not port_open(8501):
        print("   starting dashboard on :8501 ...")
        spawned.append(subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "dashboard.py",
             "--server.headless", "true"],
            cwd=DEMO_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))

    try:
        print(f"\n   A developer refactored the app (mode: {args.break_mode}).")
        print("   Ids, classes and data attributes were renamed CONSISTENTLY, so the")
        print("   application still works perfectly for a human user. Only the QA")
        print("   suite's recorded locators have rotted.")
        print(f"   Application under test: {broken_url}\n")

        baseline = run_suite("baseline", ["--url", broken_url], args.headed)
        healed = run_suite("healed", [
            "--heal", "--url", broken_url,
            "--baseline-url", base_url, "--relearn",
        ], args.headed)

        render("1. BASELINE — stock Selenium, no healing", baseline, show_heals=False)
        render("2. HEALED — identical suite, `selfheal.install()` added", healed, show_heals=True)

        all_heals = [h for t in healed["tests"] for h in t["heals"]]
        heal_count = len(all_heals)
        recovered = healed["passed"] - baseline["passed"]
        avg_ms = round(sum(h["ms"] for h in all_heals) / heal_count, 1) if heal_count else 0.0
        baseline_secs = sum(t["seconds"] for t in baseline["tests"])
        healed_secs = sum(t["seconds"] for t in healed["tests"])
        print(f"\n{RULE}\n  SUMMARY\n{RULE}")
        print(f"  Baseline .................. {baseline['passed']}/{baseline['total']} passed")
        print(f"  With self-healing layer ... {healed['passed']}/{healed['total']} passed")
        print(f"  Tests recovered ........... {recovered}")
        print(f"  Locator heals performed ... {heal_count}  (mean {avg_ms}ms each)")
        print(f"  Suite wall-clock .......... {baseline_secs:.1f}s → {healed_secs:.1f}s "
              f"(broken locators stop burning the wait timeout)")
        print(f"  Test code changed ......... 0 lines")
        print(f"{RULE}")
        print("  Every heal above is logged to the dashboard "
              "(UI Heuristic Healing tab).")
        if not args.dashboard:
            print("  Re-run with --dashboard to bring it up alongside.")
        print()
    finally:
        for proc in spawned:
            proc.terminate()


if __name__ == "__main__":
    main()
