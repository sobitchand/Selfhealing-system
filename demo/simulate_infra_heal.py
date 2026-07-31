"""
Simulate infrastructure stress conditions to populate the Infrastructure tab.

    python simulate_infra_heal.py

Writes synthetic metric snapshots to data/metrics_history.json that trigger
each infrastructure heal scenario:
  1. Disk stress (>85%) -> temp file purge + log rotation
  2. Error rate stress (>40%) -> error counter reset
  3. Service down (HTTP 500) -> service restart

After running, the dashboard Infrastructure tab shows real recovery actions.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config
import store


def _now():
    return datetime.now(timezone.utc).isoformat()


def write_metrics(entries):
    """Write a list of metric snapshots to metrics_history.json."""
    path = config.METRICS_HISTORY_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    print(f"Wrote {len(entries)} metric snapshots to {path}")


def scenario_disk_stress():
    """Simulate disk usage climbing above 85%."""
    entries = []
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    for i in range(5):
        disk = 60 + i * 8  # 60, 68, 76, 84, 92
        entries.append({
            "timestamp": (base + timedelta(minutes=i * 2)).isoformat(),
            "traffic_rate": 120 + i * 10,
            "active_requests": 15 + i * 3,
            "error_rate_percent": 5.0 + i * 2,
            "disk_usage_percent": min(disk, 95.0),
            "service_health": "Up",
            "http_status": 200,
        })
    write_metrics(entries)
    print("\n[Scenario 1] Disk stress simulated (disk: 60% -> 92%)")
    print("  -> Run dashboard to see: Log Rotation & Temp File Purge")


def scenario_error_rate_stress():
    """Simulate error rate climbing above 40%."""
    entries = []
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    for i in range(5):
        err = 10 + i * 10  # 10, 20, 30, 40, 50
        entries.append({
            "timestamp": (base + timedelta(minutes=i * 2)).isoformat(),
            "traffic_rate": 200 - i * 20,
            "active_requests": 30 - i * 5,
            "error_rate_percent": min(err, 55.0),
            "disk_usage_percent": 45.0,
            "service_health": "Up",
            "http_status": 200,
        })
    write_metrics(entries)
    print("\n[Scenario 2] Error rate stress simulated (error: 10% -> 50%)")
    print("  -> Run dashboard to see: Worker Pool Error Counter Reset")


def scenario_service_down():
    """Simulate service going down (HTTP 500)."""
    entries = []
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    for i in range(5):
        if i < 3:
            health = "Up"
            status = 200
            err = 5.0
        else:
            health = "Down"
            status = 500
            err = 85.0
        entries.append({
            "timestamp": (base + timedelta(minutes=i * 2)).isoformat(),
            "traffic_rate": 150 if i < 3 else 0,
            "active_requests": 20 if i < 3 else 0,
            "error_rate_percent": err,
            "disk_usage_percent": 50.0,
            "service_health": health,
            "http_status": status,
        })
    write_metrics(entries)
    print("\n[Scenario 3] Service down simulated (Up -> Down, HTTP 200 -> 500)")
    print("  -> Run dashboard to see: Service Restart Attempt")


def scenario_combined():
    """Simulate all three stress conditions in sequence."""
    entries = []
    base = datetime.now(timezone.utc) - timedelta(minutes=30)

    # Phase 1: Normal
    for i in range(3):
        entries.append({
            "timestamp": (base + timedelta(minutes=i * 2)).isoformat(),
            "traffic_rate": 150,
            "active_requests": 20,
            "error_rate_percent": 5.0,
            "disk_usage_percent": 40.0,
            "service_health": "Up",
            "http_status": 200,
        })

    # Phase 2: Disk stress
    for i in range(3):
        entries.append({
            "timestamp": (base + timedelta(minutes=(6 + i) * 2)).isoformat(),
            "traffic_rate": 180,
            "active_requests": 25,
            "error_rate_percent": 15.0,
            "disk_usage_percent": 75.0 + i * 10,
            "service_health": "Up",
            "http_status": 200,
        })

    # Phase 3: Error rate spike
    for i in range(3):
        entries.append({
            "timestamp": (base + timedelta(minutes=(12 + i) * 2)).isoformat(),
            "traffic_rate": 100 - i * 20,
            "active_requests": 10 - i * 3,
            "error_rate_percent": 30.0 + i * 15,
            "disk_usage_percent": 92.0,
            "service_health": "Up",
            "http_status": 200,
        })

    # Phase 4: Service down
    for i in range(3):
        entries.append({
            "timestamp": (base + timedelta(minutes=(18 + i) * 2)).isoformat(),
            "traffic_rate": 0,
            "active_requests": 0,
            "error_rate_percent": 90.0,
            "disk_usage_percent": 95.0,
            "service_health": "Down",
            "http_status": 500,
        })

    write_metrics(entries)
    print("\n[Scenario 4] Combined stress simulated (Normal -> Disk -> Error -> Down)")
    print("  -> Dashboard will show all three infrastructure heal types")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "combined"

    scenarios = {
        "disk": scenario_disk_stress,
        "error": scenario_error_rate_stress,
        "down": scenario_service_down,
        "combined": scenario_combined,
        "all": None,
    }

    if mode == "all":
        scenario_disk_stress()
        scenario_error_rate_stress()
        scenario_service_down()
        print("\n" + "=" * 60)
        print("All scenarios simulated. Open dashboard to see results.")
        print("=" * 60)
    elif mode in scenarios:
        scenarios[mode]()
    else:
        print(f"Usage: python simulate_infra_heal.py [disk|error|down|combined|all]")
        print(f"  disk     - Simulate disk usage >85%")
        print(f"  error    - Simulate error rate >40%")
        print(f"  down     - Simulate service down (HTTP 500)")
        print(f"  combined - All conditions in sequence")
        print(f"  all      - Run all scenarios separately")
        sys.exit(1)


if __name__ == "__main__":
    main()
