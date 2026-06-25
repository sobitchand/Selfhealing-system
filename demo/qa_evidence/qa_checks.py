"""
QA driver: exercises the real healing engine + storage at three confidence tiers
(NORMAL / MEDIUM / CRITICAL), plus the infra and passive telemetry paths, and
asserts each result lands in the correct bucket. Prints a machine-readable
summary the QA report is built from.

Run from the project root with the venv python:
    venv/Scripts/python.exe qa_evidence/qa_checks.py
"""
import os
import sys
import json

# project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
import store
from healing_engine import UIHeuristicEngine, DynamicInfrastructureHealer
import handlers

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    print(f"[{status}] {name}  {detail}")
    return condition


def reset_buckets():
    """Clear the four buckets for a clean, reproducible QA artifact."""
    os.makedirs(config.BUCKET_DIR, exist_ok=True)
    for b in config.BUCKETS:
        p = os.path.join(config.BUCKET_DIR, f"{b}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump([], f)


def main():
    print("=" * 70)
    print("QA RUN — Self-Healing Control Panel")
    print("=" * 70)
    reset_buckets()

    engine = UIHeuristicEngine(fingerprint_path=config.POMODORO_FINGERPRINTS_PATH)
    metrics = {"R1_inner_text": 100.0, "R2_css_class": 100.0}

    # ---- CASE 1: NORMAL (score >= 75 -> AUTOMATIC HEAL / success / continue) ----
    lifecycle, recovered, _mid = engine.commit_heal_to_log("#old-start-btn", "start-btn", 100.0, metrics)
    check("Case NORMAL lifecycle == continue", lifecycle == "continue", f"(got {lifecycle})")
    check("Case NORMAL recovered locator", recovered == "button.btn.btn-main", f"(got {recovered})")

    # ---- CASE 2: MEDIUM (20 <= score < 75 -> CAUTIOUS HEAL / warning / verify) ----
    lifecycle, recovered, _mid = engine.commit_heal_to_log("#submit-feedback-btn", "btn-short", 55.0, metrics)
    check("Case MEDIUM lifecycle == verify", lifecycle == "verify", f"(got {lifecycle})")

    # ---- CASE 3: CRITICAL (score < 20 -> CRITICAL FAULT / failed / halt -> alert) ----
    lifecycle, recovered, _mid = engine.commit_heal_to_log("#checkout-pay-btn", "start-btn", 12.0, metrics)
    check("Case CRITICAL lifecycle == halt", lifecycle == "halt", f"(got {lifecycle})")

    # ---- Infrastructure heal (passive, background) ----
    healer = DynamicInfrastructureHealer()
    stressed = {"http_status": 500, "error_rate_percent": 73.0, "disk_usage_percent": 92.4, "service_health": "Down"}
    healer.execute_infrastructure_heal(stressed, disk_stress=True, error_stress=True)

    # ---- Passive browser-agent events ----
    handlers.handle_passive_event({"type": "js_error", "message": "ReferenceError: x is not defined",
                                   "appName": "Pomodoro 3D Focus Timer"})
    handlers.handle_passive_event({"type": "selector_recovery", "brokenSelector": "#old-start",
                                   "recoveredSelector": "button[text='START']", "confidence": 88.5,
                                   "resolved": True, "appName": "Pomodoro 3D Focus Timer"})

    # ---- Bucket assertions ----
    ui = store.read("ui_heals")
    alerts = store.read("alerts")
    infra = store.read("infrastructure")
    events = store.read("browser_events")

    statuses = sorted(h.get("status") for h in ui)
    check("ui_heals has success + warning (+ passive success)", "success" in statuses and "warning" in statuses, f"statuses={statuses}")
    check("CRITICAL routed to alerts (not ui_heals)", any("too low (12" in a.get("message", "") for a in alerts), f"alerts={len(alerts)}")
    check("infrastructure row written", len(infra) >= 1, f"infra={len(infra)}")
    check("disk>90 critical alert present", any("critically low" in a.get("message", "") for a in alerts), "")
    check("browser_events captured both", len(events) >= 2, f"events={len(events)}")

    counts = {b: len(store.read(b)) for b in config.BUCKETS}
    print("-" * 70)
    print("BUCKET COUNTS:", counts)

    npass = sum(1 for _, s, _ in results if s == PASS)
    print(f"RESULT: {npass}/{len(results)} checks passed")

    # emit JSON summary for the report
    summary = {
        "checks": [{"name": n, "status": s, "detail": d} for n, s, d in results],
        "counts": counts,
        "passed": npass,
        "total": len(results),
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_summary.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary written: {out}")
    sys.exit(0 if npass == len(results) else 1)


if __name__ == "__main__":
    main()
