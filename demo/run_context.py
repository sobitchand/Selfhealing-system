"""
Run Context — the execution identity every recorded event is stamped with.

Before this existed, a heal was written to the log with no record of which
application produced it, which test was running, or which execution it belonged
to. Two applications sharing a locator name were indistinguishable in the
dashboard, and there was no way to say "show me what happened in the run that
just failed".

One RunContext is active per process for the duration of a test run
(ER diagram §3.2.1, Test_Run: run_id, started_at, browser, mode, result). It
carries the identity, accumulates what the run did, and writes a self-contained
record to data/runs/<run_id>.json when the run ends -- which is also the source
document for the exported report.
"""

import json
import os
import threading
from datetime import datetime, timezone

import config

RUNS_DIR = os.path.join(config.DATA_DIR, "runs")

_lock = threading.Lock()
_active = None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _run_id(app_id, test_id):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = f"_{test_id}" if test_id else ""
    return f"r_{stamp}_{app_id}{suffix}"


def start(app_id, test_id=None, script=None, browser="chrome", mode="healing"):
    """Begin a run. Returns the run record."""
    global _active
    with _lock:
        _active = {
            "run_id": _run_id(app_id, test_id or "run"),
            "app_id": app_id,
            "test_id": test_id or "",
            "script": script or "",
            "browser": browser,
            "mode": mode,
            "started_at": _now(),
            "ended_at": None,
            "status": "running",
            "heals": [],
            "refusals": [],
            "locators_used": [],
        }
        return dict(_active)


def current():
    """The active run, or None outside a run. Callers use this to stamp events,
    so it must never raise and must be cheap."""
    return _active


def stamp():
    """Identity fields to attach to a logged event. Empty strings outside a run
    so a record written by a standalone script still has the keys."""
    run = _active
    if not run:
        return {"run_id": "", "app_id": getattr(config, "ACTIVE_APP_ID", ""), "test_id": ""}
    return {"run_id": run["run_id"], "app_id": run["app_id"], "test_id": run["test_id"]}


def note_heal(entry):
    """Record a heal against the active run (no-op outside a run)."""
    if _active is not None:
        _active["heals"].append(entry)


def note_refusal(entry):
    """Record a below-threshold refusal against the active run."""
    if _active is not None:
        _active["refusals"].append(entry)


def note_locator(locator_key):
    """Record that the test depended on this locator (deduplicated).

    Accumulated in memory and flushed once at finish(); writing the test record
    on every lookup would put a file write inside find_element.
    """
    if _active is not None and locator_key not in _active["locators_used"]:
        _active["locators_used"].append(locator_key)


def finish(status="passed"):
    """End the run, persist it, and update the test registry. Returns the record."""
    global _active
    with _lock:
        run = _active
        _active = None

    if run is None:
        return None

    run["ended_at"] = _now()
    run["status"] = status
    run["heal_count"] = len(run["heals"])
    run["refusal_count"] = len(run["refusals"])
    try:
        started = datetime.fromisoformat(run["started_at"])
        ended = datetime.fromisoformat(run["ended_at"])
        run["duration_seconds"] = round((ended - started).total_seconds(), 2)
    except Exception:
        run["duration_seconds"] = None

    try:
        os.makedirs(RUNS_DIR, exist_ok=True)
        path = os.path.join(RUNS_DIR, run["run_id"] + ".json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(run, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f"⚠️ run record not saved: {e}")

    try:
        import test_registry
        test_registry.record_run(run)
    except Exception as e:
        print(f"⚠️ test registry not updated: {e}")

    return run


def load(run_id):
    try:
        with open(os.path.join(RUNS_DIR, f"{run_id}.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_runs(app_id=None, test_id=None, limit=100):
    """Stored runs, newest first, optionally filtered."""
    if not os.path.isdir(RUNS_DIR):
        return []
    runs = []
    for entry in sorted(os.listdir(RUNS_DIR), reverse=True):
        if not entry.endswith(".json"):
            continue
        record = load(entry[:-5])
        if not record:
            continue
        if app_id and record.get("app_id") != app_id:
            continue
        if test_id and record.get("test_id") != test_id:
            continue
        runs.append(record)
        if len(runs) >= limit:
            break
    return runs
