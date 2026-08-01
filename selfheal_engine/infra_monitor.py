"""
Infrastructure Monitor — periodic health checks of the target application.

    python infra_monitor.py [interval_seconds]

Polls the target URL every N seconds, records a metrics snapshot to
data/metrics_history.json, and triggers the infrastructure healer when
anomaly thresholds are crossed.

The dashboard's Live Metrics sidebar reads the same file, so metrics
appear automatically once this monitor is running.
"""

import json
import os
import sys
import time
import psutil
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config
import config_manager
from healing_engine import DynamicInfrastructureHealer

config_manager.apply_overrides()


def collect_snapshot(target_url):
    """Single metrics snapshot: HTTP health, response time, system resource."""
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service_health": "Down",
        "http_status": 0,
        "response_time_ms": 0,
        "traffic_rate": 0,
        "active_requests": 0,
        "error_rate_percent": 0.0,
        "disk_usage_percent": 0.0,
        "cpu_usage_percent": 0.0,
        "memory_usage_percent": 0.0,
    }

    # HTTP health check
    try:
        req = urllib.request.Request(target_url, method="GET")
        t0 = time.perf_counter()
        resp = urllib.request.urlopen(req, timeout=5)
        elapsed = (time.perf_counter() - t0) * 1000

        snapshot["http_status"] = resp.status
        snapshot["response_time_ms"] = round(elapsed, 1)
        snapshot["service_health"] = "Up" if resp.status < 500 else "Down"
        snapshot["traffic_rate"] = max(1, int(1000 / max(elapsed, 1)))
    except urllib.error.HTTPError as e:
        snapshot["http_status"] = e.code
        snapshot["error_rate_percent"] = 100.0 if e.code >= 500 else 0.0
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        snapshot["service_health"] = "Down"
        snapshot["error_rate_percent"] = 100.0

    # System resources
    try:
        snapshot["disk_usage_percent"] = round(
            psutil.disk_usage("/").percent if os.name != "nt"
            else psutil.disk_usage("C:\\").percent, 1
        )
        snapshot["cpu_usage_percent"] = round(psutil.cpu_percent(interval=0.5), 1)
        snapshot["memory_usage_percent"] = round(psutil.virtual_memory().percent, 1)
    except Exception:
        pass

    return snapshot


def append_snapshot(snapshot, path=config.METRICS_HISTORY_PATH, keep=50):
    """Append a snapshot and rotate to the last N entries."""
    history = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append(snapshot)
    if len(history) > keep:
        history = history[-keep:]

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    os.replace(tmp, path)


def main():
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    target_url = config_manager.get_config().get(
        "target_url", f"http://127.0.0.1:{config.TARGET_APP_PORT}"
    )

    print(f"Infrastructure monitor started")
    print(f"  Target:  {target_url}")
    print(f"  Interval: {interval}s")
    print(f"  Output:  {config.METRICS_HISTORY_PATH}")
    print()

    healer = DynamicInfrastructureHealer()

    try:
        while True:
            snap = collect_snapshot(target_url)
            append_snapshot(snap)
            status = snap["service_health"]
            rtime = snap["response_time_ms"]
            disk = snap["disk_usage_percent"]
            cpu = snap["cpu_usage_percent"]
            print(
                f"[{snap['timestamp'][11:19]}] "
                f"Health={status}  HTTP={snap['http_status']}  "
                f"RT={rtime}ms  Disk={disk}%  CPU={cpu}%"
            )

            # Trigger infrastructure healing on anomaly
            if status == "Down" or disk > 85.0 or snap.get("error_rate_percent", 0) > 40.0:
                print("  [ALERT] Anomaly detected — triggering infrastructure healer...")
                healer.analyze_and_heal_system()

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")


if __name__ == "__main__":
    main()
