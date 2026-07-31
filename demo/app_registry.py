"""
Application Registry — the framework's list of applications under test.

Nothing in the framework names an application. An app is registered once, gets
its own namespaced Golden Fingerprint baseline, and every later operation
(learning, healing, drift analysis, dashboard filtering) is scoped to whichever
app is active. Registering a second app cannot disturb the first: two pages that
both contain "#submit" keep separate baselines because the baseline path is
derived from the app id.

Backed by data/apps/<app_id>.json — one small document per app, matching the
Application entity of the report's ER diagram (§3.2.1):
    app_id, app_name, base_url, build_version, baseline_recorded_at

Usage:
    app_registry.register("todo", name="Todo App", url="http://127.0.0.1:8000/index.html")
    app_registry.activate("todo")        # points config.ACTIVE_FINGERPRINT_PATH at it
"""

import json
import os
import re
from datetime import datetime, timezone

import config

APPS_DIR = os.path.join(config.DATA_DIR, "apps")
ACTIVE_MARKER = os.path.join(APPS_DIR, "ACTIVE")

_ID_RE = re.compile(r"[^a-z0-9_-]+")


def _now():
    return datetime.now(timezone.utc).isoformat()


def normalize_id(app_id):
    """Filesystem-safe app id, so an app name can be passed straight through."""
    return _ID_RE.sub("-", str(app_id).strip().lower()).strip("-") or "default"


def _app_path(app_id):
    return os.path.join(APPS_DIR, f"{normalize_id(app_id)}.json")


def fingerprint_path(app_id):
    """Where this app's Golden Fingerprint baseline lives."""
    return os.path.join(config.FINGERPRINT_DIR, f"{normalize_id(app_id)}_fingerprints.json")


def register(app_id, name=None, url=None, source=None, build_version=None):
    """Create or update an application record. Returns the stored record.

    source: optional path to the HTML file backing the app. Read-only — it lets
    the dashboard show what the developer changed between builds. The framework
    never writes to it.
    """
    app_id = normalize_id(app_id)
    os.makedirs(APPS_DIR, exist_ok=True)

    record = load(app_id) or {
        "app_id": app_id,
        "created_at": _now(),
        "baseline_recorded_at": None,
    }
    record.update({
        "app_name": name or record.get("app_name") or app_id,
        "base_url": url or record.get("base_url") or "",
        "source_path": source or record.get("source_path") or "",
        "build_version": build_version or record.get("build_version") or "",
        "fingerprint_path": fingerprint_path(app_id),
        "updated_at": _now(),
    })

    tmp = _app_path(app_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    os.replace(tmp, _app_path(app_id))
    return record


def load(app_id):
    """The stored record for an app, or None if it was never registered."""
    try:
        with open(_app_path(app_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_apps():
    """Every registered app, newest first."""
    if not os.path.isdir(APPS_DIR):
        return []
    apps = []
    for entry in os.listdir(APPS_DIR):
        if entry.endswith(".json"):
            record = load(entry[:-5])
            if record:
                apps.append(record)
    return sorted(apps, key=lambda r: r.get("updated_at", ""), reverse=True)


def activate(app_id):
    """Make `app_id` the app the healing engine reads and writes.

    Points config.ACTIVE_FINGERPRINT_PATH at this app's baseline and records the
    choice on disk so a separately-launched dashboard process shows the same app.
    Returns the app record, or None when it was never registered.
    """
    record = load(app_id)
    if not record:
        return None

    config.ACTIVE_FINGERPRINT_PATH = record["fingerprint_path"]
    config.ACTIVE_APP_ID = record["app_id"]
    if record.get("base_url"):
        config.TARGET_URL = record["base_url"]

    os.makedirs(APPS_DIR, exist_ok=True)
    try:
        with open(ACTIVE_MARKER, "w", encoding="utf-8") as f:
            f.write(record["app_id"])
    except OSError:
        pass
    return record


def active_app():
    """The app record activated in this process, or the one last activated on
    this machine. None when nothing has been registered yet."""
    app_id = getattr(config, "ACTIVE_APP_ID", "")
    if not app_id:
        try:
            with open(ACTIVE_MARKER, "r", encoding="utf-8") as f:
                app_id = f.read().strip()
        except OSError:
            return None
    return load(app_id) if app_id else None


def mark_baseline_recorded(app_id, count=None):
    """Stamp when this app's baseline was captured (ER: baseline_recorded_at)."""
    record = load(app_id)
    if not record:
        return None
    record["baseline_recorded_at"] = _now()
    if count is not None:
        record["baseline_element_count"] = int(count)
    tmp = _app_path(app_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    os.replace(tmp, _app_path(app_id))
    return record
