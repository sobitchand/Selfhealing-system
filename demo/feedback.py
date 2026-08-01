"""
Feedback & Update Cycle (proposal §3.4.4, Fig 3.6: Heal -> Verify -> Log ->
Monitor -> Continue).

After a heal is rerouted, we VERIFY the recovered element is real, LOG the
outcome, and MONITOR consecutive failures per locator. If the same locator fails
to heal FAIL_THRESHOLD times in a row, we escalate and stop auto-intervention so
the system never spins in an infinite recovery loop.

State persists in data/heal_state.json (atomic temp->replace) so the loop guard
survives across separate process runs.
"""

import os
import json
from datetime import datetime

import config
import run_context
import store

FAIL_THRESHOLD = 3  # consecutive failed heals on one locator before escalation
_STATE_PATH = os.path.join(config.DATA_DIR, "heal_state.json")


def _now():
    return datetime.utcnow().isoformat() + "+00:00"


def _key(locator):
    """Namespace the counter by application.

    The state file is shared by every app the framework has ever run. Keyed by
    the bare locator, a '#submit' that failed three times in one application
    would lock '#submit' in every other application -- including one where it
    works perfectly.
    """
    app_id = run_context.stamp().get("app_id") or "default"
    return f"{app_id}::{locator}"


def _load():
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(state):
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        tmp = _STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        store.replace_atomic(tmp, _STATE_PATH)
    except Exception as e:
        print(f"⚠️ feedback state write failed: {e}")


def record_success(locator):
    """Heal verified -> reset the consecutive-failure counter for this locator."""
    key = _key(locator)
    state = _load()
    if key in state:
        state.pop(key, None)
        _save(state)


def record_failure(locator):
    """Heal failed -> increment counter; escalate when it crosses the threshold.

    Returns (count, escalated)."""
    key = _key(locator)
    state = _load()
    count = int(state.get(key, 0)) + 1
    state[key] = count
    _save(state)

    escalated = count >= FAIL_THRESHOLD
    if escalated:
        store.append("alerts", {
            "timestamp": _now(),
            **run_context.stamp(),
            "severity": "critical",
            "message": (
                f"Locator '{locator}' failed to heal {count} times in a row. "
                f"Auto-healing is now disabled for it so the run cannot loop; "
                f"it needs a look by hand."
            ),
            "source": "FeedbackLoop",
        })
    return count, escalated


def is_locked(locator):
    """True if this locator already hit the escalation threshold (stop retrying)."""
    return int(_load().get(_key(locator), 0)) >= FAIL_THRESHOLD


def verify_and_record(locator, element):
    """Post-heal validation: confirm the rerouted element is real/interactable.

    Resets the failure counter on success, increments it on failure. Returns the
    bool verification result."""
    ok = False
    try:
        ok = element is not None and element.is_displayed()
    except Exception:
        ok = element is not None  # displayed() can throw on odd elements; presence is enough
    if ok:
        record_success(locator)
    else:
        record_failure(locator)
    return ok
