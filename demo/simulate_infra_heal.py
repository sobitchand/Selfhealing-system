"""
Simulate infrastructure stress conditions to populate the Infrastructure tab.

    python simulate_infra_heal.py

Writes synthetic metric snapshots to data/metrics_history.json, then runs the
real DynamicInfrastructureHealer over them. Nothing here is faked: the snapshots
are the only synthetic part, and every recovery row in the dashboard is produced
by the same engine the live metrics monitor drives.

  1. Disk stress (>85%)        -> temp file purge + log rotation
  2. Error rate stress (>40%)  -> error counter reset
  3. Service down (HTTP 500)   -> service restart on TARGET_APP_PORT

After running, the dashboard Infrastructure tab shows real recovery actions.

Note on scenario 3: the restart action kills whatever is listening on
config.TARGET_APP_PORT (8000 by default) and launches demo_target_app.py in its
place. Skip it with `--no-restart` if that port is in use by something you care
about.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config
import store
from healing_engine import DynamicInfrastructureHealer

ALLOW_RESTART = "--no-restart" not in sys.argv


def _now():
    return datetime.now(timezone.utc).isoformat()


def write_metrics(entries):
    """Write a list of metric snapshots to metrics_history.json."""
    path = config.METRICS_HISTORY_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    print(f"Wrote {len(entries)} metric snapshots to {path}")


def heal():
    """Run the real infrastructure healer over whatever is in metrics_history.

    This is what actually writes the `infrastructure` bucket the dashboard reads.
    Writing snapshots alone leaves the tab empty -- the engine has to see them.
    """
    DynamicInfrastructureHealer().analyze_and_heal_system()


def simulate(entries, label, expectation):
    """Write snapshots, heal against them, and report what the tab should show."""
    write_metrics(entries)
    before = len(store.read("infrastructure"))
    heal()
    after = len(store.read("infrastructure"))
    print(f"\n[{label}]")
    print(f"  -> {expectation}")
    if after == before:
        print("  -> WARNING: no recovery row was written; no threshold was breached.")


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
    simulate(entries, "Scenario 1: disk stress (60% -> 92%)",
             "Infrastructure tab: Log Rotation & Temp File Purge")


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
    simulate(entries, "Scenario 2: error rate stress (10% -> 50%)",
             "Infrastructure tab: Worker Pool Error Counter Reset")


def scenario_service_down():
    """Simulate the service going down (HTTP 500) with disk and error rate healthy.

    Both other metrics stay under their thresholds deliberately: the healer
    branches on the first condition it matches, so a down service that also has
    a high error rate is treated as an error-rate problem and never reaches the
    restart path.
    """
    entries = []
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    for i in range(5):
        down = i >= 3
        entries.append({
            "timestamp": (base + timedelta(minutes=i * 2)).isoformat(),
            "traffic_rate": 0 if down else 150,
            "active_requests": 0 if down else 20,
            "error_rate_percent": 5.0,
            "disk_usage_percent": 50.0,
            "service_health": "Down" if down else "Up",
            "http_status": 500 if down else 200,
        })

    if not ALLOW_RESTART:
        write_metrics(entries)
        print("\n[Scenario 3: service down (Up -> Down, HTTP 200 -> 500)]")
        print("  -> SKIPPED (--no-restart): the recovery action would restart "
              f"port {config.TARGET_APP_PORT}.")
        return

    simulate(entries, "Scenario 3: service down (Up -> Down, HTTP 200 -> 500)",
             f"Infrastructure tab: Service Restart Attempt on port {config.TARGET_APP_PORT}")


def scenario_combined():
    """All three stress conditions in sequence, healed at each phase.

    The healer only ever sees the newest snapshot, so the phases are fed to it
    one at a time. Writing all twelve at once and healing once would produce a
    single row for whichever condition happened to be last.
    """
    base = datetime.now(timezone.utc) - timedelta(minutes=30)
    entries = []

    def phase(count, start_minute, **metrics):
        for i in range(count):
            entries.append({
                "timestamp": (base + timedelta(minutes=(start_minute + i) * 2)).isoformat(),
                **metrics,
            })

    # Phase 1: normal — nothing should be healed.
    phase(3, 0, traffic_rate=150, active_requests=20, error_rate_percent=5.0,
          disk_usage_percent=40.0, service_health="Up", http_status=200)
    write_metrics(entries)
    heal()
    print("\n[Combined phase 1/4] Normal — no recovery expected")

    # Phase 2: disk fills up.
    phase(3, 6, traffic_rate=180, active_requests=25, error_rate_percent=15.0,
          disk_usage_percent=92.0, service_health="Up", http_status=200)
    simulate(entries, "Combined phase 2/4: disk stress",
             "Log Rotation & Temp File Purge")

    # Phase 3: error rate spikes while disk recovers, so the error branch is
    # the one that matches.
    phase(3, 12, traffic_rate=60, active_requests=7, error_rate_percent=60.0,
          disk_usage_percent=55.0, service_health="Up", http_status=200)
    simulate(entries, "Combined phase 3/4: error rate spike",
             "Worker Pool Error Counter Reset")

    # Phase 4: service falls over, with the other two metrics healthy.
    phase(3, 18, traffic_rate=0, active_requests=0, error_rate_percent=5.0,
          disk_usage_percent=50.0, service_health="Down", http_status=500)
    if ALLOW_RESTART:
        simulate(entries, "Combined phase 4/4: service down",
                 f"Service Restart Attempt on port {config.TARGET_APP_PORT}")
    else:
        write_metrics(entries)
        print("\n[Combined phase 4/4] SKIPPED (--no-restart)")

    print("\nDashboard Infrastructure tab now shows one row per heal type.")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = args[0] if args else "combined"

    scenarios = {
        "disk": scenario_disk_stress,
        "error": scenario_error_rate_stress,
        "down": scenario_service_down,
        "combined": scenario_combined,
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
        print("Usage: python simulate_infra_heal.py [disk|error|down|combined|all] [--no-restart]")
        print("  disk        - Simulate disk usage >85%")
        print("  error       - Simulate error rate >40%")
        print("  down        - Simulate service down (HTTP 500)")
        print("  combined    - All conditions in sequence (default)")
        print("  all         - Run each scenario separately")
        print("  --no-restart- Skip the scenario that restarts TARGET_APP_PORT")
        sys.exit(1)


if __name__ == "__main__":
    main()
