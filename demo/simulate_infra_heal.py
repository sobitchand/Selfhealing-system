import random
from datetime import datetime, timezone
import time
import config
import store

# List of real-world server infrastructure problems and automated fixes
infra_scenarios = [
    {
        "trigger_metric": "Disk Capacity > 85%",
        "anomaly_found": "Log directory overflow / storage exhaustion warning (86.8%)",
        "recovery_action": "Executed logrotate utility + cleared /tmp/ cache allocations",
        "policy": "AUTO_DISK_PURGE"
    },
    {
        "trigger_metric": "RAM Overhead > 92%",
        "anomaly_found": "Memory leak detected in persistent background worker pools",
        "recovery_action": "Gracefully reloaded WSGI application worker daemon subprocesses",
        "policy": "RAM_LEAK_FLUSH"
    },
    {
        "trigger_metric": "API Gateway Health == DOWN",
        "anomaly_found": "Microservice dropped connection requests (HTTP 502)",
        "recovery_action": "Dispatched systemctl restart api_gateway_service wrapper routing",
        "policy": "CRASHED_PROCESS_REBOOT"
    }
]

print("📡 Infrastructure Monitor: Auditing server container resource health matrix...")
time.sleep(1)

# Randomly select a server error scenario so the demo changes every time you run it
selected_infra = random.choice(infra_scenarios)

print(f"🚨 ALERT TRIGGERED: {selected_infra['trigger_metric']}")
print(f"⚠️ Detail: {selected_infra['anomaly_found']}")
time.sleep(1.5)
print(f"⚙️ Running Active Mitigation Policy: [{selected_infra['policy']}]...")
time.sleep(1)
print(f"✅ Success: {selected_infra['recovery_action']}")

# Package the data up to send to the central tracking file
new_infra_heal = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "trigger_metric": selected_infra["trigger_metric"],
    "anomaly_found": selected_infra["anomaly_found"],
    "recovery_action": selected_infra["recovery_action"],
    "policy": selected_infra["policy"],
    "status": "success"
}

# Persist via the atomic, per-bucket store (cross-process safe + rolling window)
store.append("infrastructure", new_infra_heal)

print("\n📊 Backend state repaired. Metrics transmitted to control board dashboard!")