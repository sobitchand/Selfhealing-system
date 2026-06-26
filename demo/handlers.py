"""
Request-handling seam: two explicit paths, one shared atomic store.

ACTIVE path  -> synchronous. The caller (the Selenium SelfHealingWebDriver) is
               blocked waiting for a heal decision, so handle_active_heal RETURNS
               the lifecycle + recovered locator.

PASSIVE path -> fire-and-forget. Browser-agent telemetry is ingested and routed
               to the right bucket(s); the producer does not wait and gets no
               decision back.

Both paths persist through store.append (per-bucket, atomic, cross-process safe).
"""

from datetime import datetime, timezone

import store


def _now():
    return datetime.now(timezone.utc).isoformat()


# --------------------------- ACTIVE path ---------------------------
def handle_active_heal(engine, broken_selector, candidates):
    """
    Synchronous heal. Scores live DOM candidates against the golden fingerprints,
    commits the result, and returns the decision so the caller can keep driving.

    Returns: (lifecycle, recovered_locator, confidence_score, match_id, best_candidate)
    match_id is the canonical fingerprint key (== element id) for source write-back.
    best_candidate is the winning LIVE element dict (carries its current xpath) so
    the caller can re-grab the element even when the attribute the old selector
    used was the one that changed.
    """
    match_id, score, metrics, best_candidate = engine.evaluate_live_candidates(broken_selector, candidates)
    lifecycle, recovered, match_id = engine.commit_heal_to_log(broken_selector, match_id, score, metrics)
    return lifecycle, recovered, score, match_id, best_candidate


# --------------------------- PASSIVE path ---------------------------
def handle_passive_event(event):
    """
    Ingest one browser-agent event (fire-and-forget). Routes to alerts / ui_heals
    and always keeps a raw copy in browser_events. No return value.
    """
    timestamp = _now()
    event_type = event.get("type")

    # Route 1: front-end runtime errors / failed resources -> alerts
    if event_type in ("js_error", "resource_failure"):
        store.append("alerts", {
            "timestamp": timestamp,
            "severity": "warning",
            "message": f"Browser Application Anomaly ({event_type}): {event.get('message')}",
            "source": f"JSBrowserAgent ({event.get('appName', 'Static App')})",
        })

    # Route 2: in-browser selector fallback recoveries -> ui_heals
    elif event_type == "selector_recovery":
        store.append("ui_heals", {
            "timestamp": timestamp,
            "broken_selector": event.get("brokenSelector"),
            "recovered_selector": event.get("recoveredSelector"),
            "confidence_score": event.get("confidence", 85.0),
            "policy": "AUTOMATIC RUNTIME HEAL",
            "status": "success" if event.get("resolved") else "warning",
            "details": {"context": "Triggered via Browser UI client engine abstraction agent wrapper."},
        })

    # Always keep a raw copy of every client event
    event["processed_timestamp"] = timestamp
    store.append("browser_events", event)
