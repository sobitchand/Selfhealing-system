"""
Per-bucket atomic JSON storage with cross-process locking and rolling windows.

Each telemetry bucket (ui_heals, infrastructure, alerts, browser_events) lives in
its own file under config.BUCKET_DIR. Writes go through a per-bucket file lock so
that the many independent processes that emit telemetry -- the Selenium heal
wrapper, the metrics-monitor thread, the collector HTTP server, and the canned
demo scripts -- can no longer clobber each other's appends or read a half-written
file.

This generalizes the safe write pattern already used by
selfhealing/metrics_monitor._write_snapshot (lock + temp file + os.replace +
size cap), but adds CROSS-PROCESS safety via filelock (the old in-process
threading.Lock did nothing across separate processes).
"""

import json
import os

from filelock import FileLock, Timeout

import config

LOCK_TIMEOUT = 10  # seconds to wait for a contended bucket before giving up


def _bucket_path(bucket):
    return os.path.join(config.BUCKET_DIR, f"{bucket}.json")


def _lock_path(bucket):
    return _bucket_path(bucket) + ".lock"


def _limit(bucket):
    return config.BUCKET_LIMITS.get(bucket, config.BUCKET_DEFAULT_LIMIT)


def read(bucket):
    """Return the bucket's list of entries ([] if missing or corrupt)."""
    path = _bucket_path(bucket)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def append(bucket, entry):
    """
    Atomically append one entry to a bucket under a cross-process lock, trimming
    the bucket to its rolling-window cap. Best-effort: never raises into a
    passive caller (telemetry must not crash the producer).
    Returns True on success, False otherwise.
    """
    os.makedirs(config.BUCKET_DIR, exist_ok=True)
    try:
        with FileLock(_lock_path(bucket), timeout=LOCK_TIMEOUT):
            data = read(bucket)
            data.append(entry)

            limit = _limit(bucket)
            if len(data) > limit:
                data = data[-limit:]

            # Write to a temp file first, then atomically swap into place so a
            # concurrent reader never observes a partially written file.
            path = _bucket_path(bucket)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
        return True
    except Timeout:
        print(f"⚠️ store.append: timed out acquiring lock for bucket '{bucket}'")
        return False
    except Exception as e:
        print(f"❌ store.append failed for bucket '{bucket}': {e}")
        return False


def read_all():
    """Return {bucket: [entries]} across all configured buckets (for the dashboard)."""
    return {bucket: read(bucket) for bucket in config.BUCKETS}
