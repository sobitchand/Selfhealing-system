"""
QA driver: exercises the real healing engine and storage at three confidence
tiers (NORMAL / MEDIUM / CRITICAL), plus the infrastructure and passive
telemetry paths, and asserts each result lands in the correct bucket. Prints a
machine-readable summary the QA report is built from.

Run from the project root with the venv python:
    .venv/Scripts/python.exe qa_evidence/qa_checks.py

Two properties this driver deliberately has:

  * It is NON-DESTRUCTIVE. Every path config exposes -- buckets, data dir,
    metrics history, fingerprint baseline -- is redirected into a throwaway
    temp directory for the duration of the run. It used to clear the real
    data/buckets/, which meant running the checks before a demo silently wiped
    the demo.

  * It is SELF-CONTAINED. The fingerprint baseline is a fixture written here,
    not whichever application happens to be registered. The checks therefore
    assert fixed, meaningful values instead of tracking whatever data is lying
    around.
"""
import os
import sys
import json
import shutil
import tempfile

# project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config

# ---------------------------------------------------------------------------
# Redirect every writable path BEFORE importing anything that reads them.
# store.py resolves config.BUCKET_DIR per call, so reassigning it here is
# enough. DynamicInfrastructureHealer binds config.METRICS_HISTORY_PATH as a
# default argument at import time, so that one has to be passed explicitly.
# ---------------------------------------------------------------------------
SANDBOX = tempfile.mkdtemp(prefix="qa_selfheal_")
config.DATA_DIR = SANDBOX
config.BUCKET_DIR = os.path.join(SANDBOX, "buckets")
config.METRICS_HISTORY_PATH = os.path.join(SANDBOX, "metrics_history.json")
os.makedirs(config.BUCKET_DIR, exist_ok=True)

import store
from healing_engine import UIHeuristicEngine, DynamicInfrastructureHealer
import handlers

PASS = "PASS"
FAIL = "FAIL"
results = []

# ---------------------------------------------------------------------------
# Fingerprint fixture.
#
# 'start-btn' carries BOTH an element_id and a data-testid so the Locator
# Recovery ranking is actually exercised: id outranks data-testid, so a correct
# implementation must return the id. Asserting that is a real test of the
# ranking, rather than echoing back the only attribute present.
# ---------------------------------------------------------------------------
FIXTURE = {
    "start-btn": {
        "tag_name": "button",
        "element_id": "start-btn",
        "element_name": "start",
        "inner_text": "START",
        "css_class": "btn btn-main",
        "xpath_pattern": "/html/body/div/main/button",
        "neighbors": ["h1", "p", "span"],
        "data_attrs": {"data-testid": "start-control"},
        "locator_by": "id",
        "locator_value": "start-btn",
        "locator_key": "id::start-btn",
    },
    "btn-short": {
        "tag_name": "button",
        "element_id": "",
        "inner_text": "Send feedback",
        "css_class": "btn btn-short",
        "xpath_pattern": "/html/body/div/footer/button",
        "neighbors": ["a"],
        "data_attrs": {"data-testid": "feedback-submit"},
        "locator_by": "css selector",
        "locator_value": ".btn-short",
        "locator_key": "css selector::.btn-short",
    },
}

FINGERPRINT_PATH = os.path.join(SANDBOX, "qa_fixture_fingerprints.json")


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    print(f"[{status}] {name}  {detail}")
    return condition


def write_fixture():
    with open(FINGERPRINT_PATH, "w", encoding="utf-8") as f:
        json.dump(FIXTURE, f, indent=2)


def reset_buckets():
    """Clear the sandbox buckets for a clean, reproducible QA artifact."""
    os.makedirs(config.BUCKET_DIR, exist_ok=True)
    for b in config.BUCKETS:
        p = os.path.join(config.BUCKET_DIR, f"{b}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump([], f)


def main():
    print("=" * 70)
    print("QA RUN — Self-Healing Control Panel")
    print("=" * 70)
    print(f"sandbox: {SANDBOX}")
    reset_buckets()
    write_fixture()

    engine = UIHeuristicEngine(fingerprint_path=FINGERPRINT_PATH)
    metrics = {"R1_inner_text_40": 100.0, "R2_xpath_pattern_30": 100.0,
               "R3_css_class_20": 100.0, "R4_neighbors_10": 100.0}

    # ---- CASE 1: NORMAL (score >= 75 -> AUTOMATIC HEAL / success / continue) ----
    lifecycle, recovered, _mid = engine.commit_heal_to_log(
        "#old-start-btn", "start-btn", 100.0, metrics)
    check("Case NORMAL lifecycle == continue", lifecycle == "continue", f"(got {lifecycle})")
    # id outranks data-testid in _RECOVERY_RANK, so 'start-btn' must win over
    # '[data-testid=start-control]'.
    check("Case NORMAL recovered locator (id outranks data-testid)",
          recovered == "start-btn", f"(got {recovered})")

    # ---- CASE 2: MEDIUM (20 <= score < 75 -> CAUTIOUS HEAL / warning / verify) ----
    lifecycle, recovered, _mid = engine.commit_heal_to_log(
        "#submit-feedback-btn", "btn-short", 55.0, metrics)
    check("Case MEDIUM lifecycle == verify", lifecycle == "verify", f"(got {lifecycle})")

    # ---- CASE 3: CRITICAL (score < 20 -> CRITICAL FAULT / failed / halt -> alert) ----
    lifecycle, recovered, _mid = engine.commit_heal_to_log(
        "#checkout-pay-btn", "start-btn", 12.0, metrics)
    check("Case CRITICAL lifecycle == halt", lifecycle == "halt", f"(got {lifecycle})")

    # ---- Infrastructure heal (passive, background) ----
    # history_path passed explicitly: it is a default argument bound at import
    # time, so reassigning config.METRICS_HISTORY_PATH above does not reach it.
    healer = DynamicInfrastructureHealer(history_path=config.METRICS_HISTORY_PATH)
    stressed = {"http_status": 500, "error_rate_percent": 73.0,
                "disk_usage_percent": 92.4, "service_health": "Down"}
    healer.execute_infrastructure_heal(stressed, disk_stress=True, error_stress=True)

    # ---- Passive browser-agent events ----
    handlers.handle_passive_event({"type": "js_error",
                                   "message": "ReferenceError: x is not defined",
                                   "appName": "QA Fixture App"})
    handlers.handle_passive_event({"type": "selector_recovery",
                                   "brokenSelector": "#old-start",
                                   "recoveredSelector": "button[text='START']",
                                   "confidence": 88.5, "resolved": True,
                                   "appName": "QA Fixture App"})

    # ---- Bucket assertions ----
    ui = store.read("ui_heals")
    alerts = store.read("alerts")
    infra = store.read("infrastructure")
    events = store.read("browser_events")

    # `or ""` guards a row with no status: sorting None against str raises, and
    # a crash here aborts the run before the later checks are ever evaluated --
    # so a routing regression would look like a broken driver, not a failed test.
    statuses = sorted(h.get("status") or "" for h in ui)
    check("ui_heals has success + warning (+ passive success)",
          "success" in statuses and "warning" in statuses, f"statuses={statuses}")

    # Assert the ROUTING INVARIANT rather than a message substring: a refusal
    # belongs in alerts, at critical severity, and must not also appear as a
    # heal. String-matching the wording made this fail the moment the refusal
    # message was reworded, while testing nothing that actually matters.
    refused = "#checkout-pay-btn"
    in_alerts = any(a.get("broken_selector") == refused and a.get("severity") == "critical"
                    for a in alerts)
    not_in_heals = not any(h.get("broken_selector") == refused for h in ui)
    check("CRITICAL routed to alerts (not ui_heals)", in_alerts and not_in_heals,
          f"alerts={len(alerts)} in_alerts={in_alerts} absent_from_ui_heals={not_in_heals}")

    check("infrastructure row written", len(infra) >= 1, f"infra={len(infra)}")
    check("disk>90 critical alert present",
          any("critically low" in a.get("message", "") for a in alerts), "")
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
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)
    sys.exit(code)
