"""
Test Registry — the Selenium tests the framework knows about, per application.

Mirrors the Test_Script entity of the report's ER diagram (§3.2.1): script_id,
file_path, test_name, and the N:M `uses` relationship to the elements it depends
on. That relationship is not declared by hand -- it is derived from what the
test actually resolved during a passing run, which is the whole point of binding
Learning Mode to a green execution.

A test is registered the first time it runs. Nothing needs configuring.

Stored at data/tests/<app_id>/<test_id>.json.
"""

import json
import os
from datetime import datetime, timezone

import app_registry
import config
import store

TESTS_DIR = os.path.join(config.DATA_DIR, "tests")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _dir_for(app_id):
    return os.path.join(TESTS_DIR, app_registry.normalize_id(app_id))


def _path(app_id, test_id):
    return os.path.join(_dir_for(app_id), f"{app_registry.normalize_id(test_id)}.json")


def load(app_id, test_id):
    try:
        with open(_path(app_id, test_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write(record):
    directory = _dir_for(record["app_id"])
    os.makedirs(directory, exist_ok=True)
    path = _path(record["app_id"], record["test_id"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    store.replace_atomic(tmp, path)
    return record


def register(app_id, test_id, script=None):
    """Create or update a test record. Idempotent."""
    record = load(app_id, test_id) or {
        "app_id": app_id,
        "test_id": test_id,
        "created_at": _now(),
        "locators_used": [],
        "last_success": None,
        "last_failure": None,
        "total_runs": 0,
        "total_heals": 0,
        "total_refusals": 0,
    }
    if script:
        record["script"] = script
    record["updated_at"] = _now()
    return _write(record)


def record_run(run):
    """Fold a completed run into its test's record.

    `locators_used` is replaced (not merged) on a passing run, so a locator the
    test no longer uses stops being listed as a dependency. On a failing run it
    is left alone: a run that died halfway through resolved only some of the
    locators it depends on, and treating that partial list as the truth would
    quietly shrink the test's recorded footprint.
    """
    app_id, test_id = run.get("app_id"), run.get("test_id")
    if not app_id or not test_id:
        return None

    record = load(app_id, test_id) or register(app_id, test_id, run.get("script"))
    if run.get("script"):
        record["script"] = run["script"]

    passed = run.get("status") == "passed"
    summary = {
        "run_id": run.get("run_id"),
        "at": run.get("ended_at"),
        "heals": run.get("heal_count", 0),
        "refusals": run.get("refusal_count", 0),
        "duration_seconds": run.get("duration_seconds"),
    }
    if passed:
        record["last_success"] = summary
        if run.get("locators_used"):
            record["locators_used"] = list(run["locators_used"])
    else:
        record["last_failure"] = summary

    record["total_runs"] = int(record.get("total_runs", 0)) + 1
    record["total_heals"] = int(record.get("total_heals", 0)) + run.get("heal_count", 0)
    record["total_refusals"] = int(record.get("total_refusals", 0)) + run.get("refusal_count", 0)
    record["browser"] = run.get("browser", "")
    record["updated_at"] = _now()
    return _write(record)


def list_tests(app_id):
    """Every test registered for an application, most recently updated first."""
    directory = _dir_for(app_id)
    if not os.path.isdir(directory):
        return []
    tests = []
    for entry in os.listdir(directory):
        if entry.endswith(".json"):
            record = load(app_id, entry[:-5])
            if record:
                tests.append(record)
    return sorted(tests, key=lambda r: r.get("updated_at", ""), reverse=True)


def health(record):
    """One-word state for the dashboard: passing, failing, healing, or unknown."""
    if not record:
        return "unknown"
    success = (record.get("last_success") or {}).get("at")
    failure = (record.get("last_failure") or {}).get("at")
    if success and failure:
        latest_passed = success > failure
    elif success:
        latest_passed = True
    elif failure:
        latest_passed = False
    else:
        return "unknown"
    if not latest_passed:
        return "failing"
    return "healing" if (record.get("last_success") or {}).get("heals") else "passing"
