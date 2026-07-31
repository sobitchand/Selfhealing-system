"""
Framework command line.

    python cli.py register  --app todo --url http://127.0.0.1:8000/index.html
    python cli.py apps
    python cli.py learn     --app todo
    python cli.py check     --app todo
    python cli.py baseline  --app todo

`check` is the one to reach for after a developer edits the markup: it compares
the live page against the recorded baseline and reports the impact WITHOUT
running the test suite, including the case where nothing broke.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app_registry
import config


def _driver(headed=False):
    """A Chrome driver, reusing the cached chromedriver when one is present."""
    import glob
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    if not headed:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    cached = sorted(glob.glob(os.path.expanduser(
        "~/.wdm/drivers/chromedriver/*/*/chromedriver-win64/chromedriver.exe"
    )))
    if cached:
        return webdriver.Chrome(service=Service(cached[-1]), options=options)

    from webdriver_manager.chrome import ChromeDriverManager
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def _resolve_url(app, explicit=None):
    if explicit:
        return explicit
    record = app_registry.load(app)
    if record and record.get("base_url"):
        return record["base_url"]
    sys.exit(f"No URL for app '{app}'. Register one with:\n"
             f"  python cli.py register --app {app} --url <url>")


def cmd_register(args):
    record = app_registry.register(
        args.app, name=args.name, url=args.url, source=args.source, build_version=args.build
    )
    app_registry.activate(args.app)
    print(f"Registered '{record['app_id']}' ({record['app_name']})")
    print(f"  url:       {record['base_url'] or '(none)'}")
    print(f"  baseline:  {record['fingerprint_path']}")
    if record.get("source_path"):
        print(f"  source:    {record['source_path']}")
    print(f"\nNext: run your Selenium test with\n"
          f"    with selfheal.run(app=\"{record['app_id']}\"):")


def cmd_apps(args):
    apps = app_registry.list_apps()
    if not apps:
        print("No applications registered yet. Use: python cli.py register --app <id> --url <url>")
        return
    active = app_registry.active_app()
    active_id = active["app_id"] if active else ""
    for record in apps:
        marker = "*" if record["app_id"] == active_id else " "
        captured = record.get("baseline_element_count")
        baseline = (f"{captured} element(s), recorded {record['baseline_recorded_at']}"
                    if record.get("baseline_recorded_at") else "not yet recorded")
        print(f" {marker} {record['app_id']:<20} {record.get('base_url', ''):<40} baseline: {baseline}")


def cmd_learn(args):
    """Capture a baseline by scanning the page directly.

    Prefer learning from a passing test run (selfheal.run), which records only
    the locators the suite actually depends on. This page scan is the fallback
    for an app that has no test yet.
    """
    import learning_mode

    app_registry.activate(args.app) or sys.exit(f"App '{args.app}' is not registered.")
    url = _resolve_url(args.app, args.url)

    driver = _driver(headed=args.headed)
    try:
        driver.get(url)
        count = learning_mode.ensure_fingerprints(
            driver, config.ACTIVE_FINGERPRINT_PATH, force=args.force
        )
        from fingerprint_manager import FingerprintManager
        total = len(FingerprintManager(driver, config.ACTIVE_FINGERPRINT_PATH).registry)
        app_registry.mark_baseline_recorded(args.app, total)
        print(f"Baseline for '{args.app}': {total} element(s) -> {config.ACTIVE_FINGERPRINT_PATH}")
        if count is False:
            print("(existing baseline kept — pass --force to rebuild it)")
    finally:
        driver.quit()


def cmd_check(args):
    import drift_analyzer

    app_registry.activate(args.app) or sys.exit(f"App '{args.app}' is not registered.")
    url = _resolve_url(args.app, args.url)

    if not os.path.exists(config.ACTIVE_FINGERPRINT_PATH):
        sys.exit(f"No baseline for '{args.app}' yet. Run the test once, or: "
                 f"python cli.py learn --app {args.app}")

    driver = _driver(headed=args.headed)
    try:
        driver.get(url)
        report = drift_analyzer.analyze(driver)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(drift_analyzer.format_report(report))
    finally:
        driver.quit()


def cmd_baseline(args):
    app_registry.activate(args.app) or sys.exit(f"App '{args.app}' is not registered.")
    try:
        with open(config.ACTIVE_FINGERPRINT_PATH, "r", encoding="utf-8") as f:
            fingerprints = json.load(f)
    except Exception:
        sys.exit(f"No baseline recorded for '{args.app}' yet.")

    print(f"{len(fingerprints)} tracked element(s) for '{args.app}':\n")
    for key, golden in fingerprints.items():
        locator = f"{golden.get('locator_by', '?')}='{golden.get('locator_value', '?')}'"
        text = (golden.get("inner_text") or "")[:40]
        print(f"  <{golden.get('tag_name', '?')}> {locator}")
        if text:
            print(f"      text: {text}")


def cmd_tests(args):
    import test_registry

    records = test_registry.list_tests(args.app)
    if not records:
        print(f"No test has run against '{args.app}' yet.")
        return
    for record in records:
        success = (record.get("last_success") or {}).get("at") or "never"
        failure = (record.get("last_failure") or {}).get("at") or "never"
        print(f"  {record['test_id']:<24} {test_registry.health(record):<9} "
              f"runs={record.get('total_runs', 0)} heals={record.get('total_heals', 0)} "
              f"locators={len(record.get('locators_used', []))}")
        print(f"      script       : {record.get('script', '-')}")
        print(f"      last success : {success}")
        print(f"      last failure : {failure}")


def cmd_runs(args):
    import run_context

    records = run_context.list_runs(app_id=args.app, test_id=args.test, limit=args.limit)
    if not records:
        print("No runs recorded yet.")
        return
    for record in records:
        print(f"  {record['run_id']:<44} {record.get('status', '?'):<7} "
              f"heals={record.get('heal_count', 0)} refusals={record.get('refusal_count', 0)} "
              f"{record.get('duration_seconds', '?')}s")


def cmd_report(args):
    import reports
    import run_context

    if args.run in (None, "latest"):
        candidates = run_context.list_runs(app_id=args.app, test_id=args.test, limit=1)
        if not candidates:
            sys.exit("No runs recorded yet.")
        record = candidates[0]
    else:
        record = run_context.load(args.run)
        if not record:
            sys.exit(f"No run '{args.run}'.")

    rendered = {"md": reports.to_markdown, "csv": reports.to_csv,
                "json": reports.to_json, "patch": reports.patch_suggestions}[args.format](record)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"Wrote {args.out}")
    else:
        print(rendered)


def main():
    parser = argparse.ArgumentParser(prog="cli.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("register", help="register an application under test")
    p.add_argument("--app", required=True)
    p.add_argument("--name")
    p.add_argument("--url")
    p.add_argument("--source", help="path to the HTML file (read-only, for the diff view)")
    p.add_argument("--build")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("apps", help="list registered applications")
    p.set_defaults(func=cmd_apps)

    p = sub.add_parser("learn", help="capture a baseline by scanning the page")
    p.add_argument("--app", required=True)
    p.add_argument("--url")
    p.add_argument("--force", action="store_true", help="rebuild an existing baseline")
    p.add_argument("--headed", action="store_true")
    p.set_defaults(func=cmd_learn)

    p = sub.add_parser("check", help="drift / change-impact analysis against the baseline")
    p.add_argument("--app", required=True)
    p.add_argument("--url")
    p.add_argument("--json", action="store_true")
    p.add_argument("--headed", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("baseline", help="show the recorded Golden Fingerprints")
    p.add_argument("--app", required=True)
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("tests", help="list the tests registered for an application")
    p.add_argument("--app", required=True)
    p.set_defaults(func=cmd_tests)

    p = sub.add_parser("runs", help="list recorded test runs")
    p.add_argument("--app")
    p.add_argument("--test")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("report", help="render a run as markdown / csv / json / patch")
    p.add_argument("--run", default="latest", help="run id, or 'latest'")
    p.add_argument("--app")
    p.add_argument("--test")
    p.add_argument("--format", choices=["md", "csv", "json", "patch"], default="md")
    p.add_argument("--out", help="write to a file instead of stdout")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
