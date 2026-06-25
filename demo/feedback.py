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
import store

FAIL_THRESHOLD = 3  # consecutive failed heals on one locator before escalation
_STATE_PATH = os.path.join(config.DATA_DIR, "heal_state.json")


def _now():
    return datetime.utcnow().isoformat() + "+00:00"


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
        os.replace(tmp, _STATE_PATH)
    except Exception as e:
        print(f"⚠️ feedback state write failed: {e}")


def record_success(locator):
    """Heal verified -> reset the consecutive-failure counter for this locator."""
    state = _load()
    if locator in state:
        state.pop(locator, None)
        _save(state)


def record_failure(locator):
    """Heal failed -> increment counter; escalate when it crosses the threshold.

    Returns (count, escalated)."""
    state = _load()
    count = int(state.get(locator, 0)) + 1
    state[locator] = count
    _save(state)

    escalated = count >= FAIL_THRESHOLD
    if escalated:
        store.append("alerts", {
            "timestamp": _now(),
            "severity": "critical",
            "message": (
                f"Repeated heal failure ({count}x) for locator {locator}. "
                f"Auto-intervention halted to prevent infinite recovery loop. "
                f"Manual administrator review required."
            ),
            "source": "FeedbackLoop",
        })
    return count, escalated


def is_locked(locator):
    """True if this locator already hit the escalation threshold (stop retrying)."""
    return int(_load().get(locator, 0)) >= FAIL_THRESHOLD


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
