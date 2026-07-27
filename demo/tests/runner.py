"""
Minimal test runner for tests/test_pomodoro.py.

pytest is not in requirements.txt, and the demo must work on a clean machine, so
this reproduces the only pytest feature the suite uses: collect test_* functions
and inject the `driver` fixture. The test file is untouched either way -- run it
with pytest instead if you have it (see conftest.py).

    python tests/runner.py                 # baseline: stock Selenium
    python tests/runner.py --heal          # with the self-healing layer
    python tests/runner.py --heal --headed # ...and watch it happen
"""

import argparse
import json
import os
import sys
import time
import traceback

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DEMO_DIR = os.path.dirname(_TESTS_DIR)
for _p in (_DEMO_DIR, _TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from driver_factory import make_driver  # noqa: E402

RESULT_MARKER = "##SELFHEAL_RESULT##"


def collect(module):
    """test_* functions in source order, so the run reads like the file."""
    tests = [
        (name, getattr(module, name))
        for name in dir(module)
        if name.startswith("test_") and callable(getattr(module, name))
    ]
    return sorted(tests, key=lambda t: t[1].__code__.co_firstlineno)


def describe(exc):
    """A readable one-liner. Selenium's TimeoutException carries an empty
    message, which tells a reader nothing about what actually went wrong."""
    detail = str(exc).splitlines()[0].strip() if str(exc).strip() else ""
    if type(exc).__name__ == "TimeoutException" and not detail.replace("Message:", "").strip():
        detail = "element never appeared before the wait expired"
    return f"{type(exc).__name__}: {detail[:160]}" if detail else type(exc).__name__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--heal", action="store_true", help="install the self-healing layer")
    ap.add_argument("--headed", action="store_true", help="run Chrome visibly")
    ap.add_argument("--url", default=None, help="application under test")
    ap.add_argument("--baseline-url", default=None, help="known-good build to learn from")
    ap.add_argument("--relearn", action="store_true", help="force a fresh golden baseline")
    ap.add_argument("--quiet", action="store_true", help="suppress heal chatter")
    args = ap.parse_args()

    if args.url:
        os.environ["APP_URL"] = args.url

    selfheal = None
    if args.heal:
        import selfheal as _selfheal
        selfheal = _selfheal
        selfheal.install()

    if args.quiet:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")

    # Imported AFTER the patch so the run is representative either way. (The
    # patch is on Selenium's classes, so import order does not actually matter --
    # this just keeps the two runs symmetrical.)
    import test_pomodoro

    driver = make_driver(headed=args.headed)
    results = []

    try:
        if selfheal:
            selfheal.learn_baseline(
                driver,
                url=args.baseline_url or "http://127.0.0.1:8000",
                force=args.relearn,
            )

        for name, fn in collect(test_pomodoro):
            if selfheal:
                selfheal.reset_session()
            started = time.perf_counter()
            record = {"name": name, "passed": False, "error": "", "heals": [],
                      "seconds": 0.0}
            try:
                fn(driver)
                record["passed"] = True
            except Exception as e:
                record["error"] = describe(e)
                if not args.quiet:
                    traceback.print_exc()
            record["seconds"] = round(time.perf_counter() - started, 2)
            if selfheal:
                record["heals"] = selfheal.session_heals()
            results.append(record)
    finally:
        driver.quit()
        if selfheal:
            selfheal.uninstall()
        if args.quiet:
            sys.stdout.close()
            sys.stdout = sys.__stdout__

    payload = {
        "mode": "healed" if args.heal else "baseline",
        "url": os.environ.get("APP_URL", "http://127.0.0.1:8000"),
        "passed": sum(1 for r in results if r["passed"]),
        "total": len(results),
        "tests": results,
    }
    print(RESULT_MARKER + json.dumps(payload))
    sys.exit(0 if payload["passed"] == payload["total"] else 1)


if __name__ == "__main__":
    main()
