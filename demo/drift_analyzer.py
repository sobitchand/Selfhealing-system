"""
Baseline Drift Analyzer — change impact analysis for the registered application.

The healing engine only speaks when a locator fails. That leaves the most common
question a developer asks unanswered: "I changed the markup — did I break the test
suite?" A framework that answers only by falling over is indistinguishable from a
framework that is not running at all.

This module compares the live DOM against the Golden Fingerprint baseline WITHOUT
running the test suite, and classifies every tracked element:

    INTACT     unchanged
    MOVED      same element, different position (a container was inserted)
    CHANGED    still identifiable, but an attribute the locator relies on differs
    AMBIGUOUS  the recorded locator now matches MORE than one live element
    MISSING    no live element resembles it any more

plus NEW elements that exist live and were never in the baseline.

AMBIGUOUS is the finding that matters most and the one no exception would ever
surface: adding a second element that a recorded locator also matches makes
find_element silently return the first one. The test keeps passing while
asserting against the wrong element -- a false pass, which is the most expensive
outcome a suite can produce.

Nothing here modifies the application: the page is read, never written.
"""

import json
import os
from datetime import datetime, timezone

import automation_wrapper
import config
import dom_features
import store
from healing_engine import UIHeuristicEngine

# A tracked element scoring at or above this against its best live candidate is
# considered still present; below it, the element is treated as gone.
PRESENT_THRESHOLD = 55.0
# Above this, and with an unchanged position, nothing has happened to it.
INTACT_THRESHOLD = 95.0


def _now():
    return datetime.now(timezone.utc).isoformat()


def _locator_of(golden):
    return str(golden.get("locator_by") or ""), str(golden.get("locator_value") or "")


def _resolve_count(driver, by, value):
    """How many live elements the recorded locator matches: 0, 1 or more.

    Runs with healing suppressed -- this is a measurement of the page as it
    actually is, and a heal here would report the page we wish we had.
    """
    if not by or not value:
        return None
    try:
        with automation_wrapper.suppressed():
            return len(driver.find_elements(by, value))
    except Exception:
        return None


def analyze(driver, fingerprint_path=None, limit=400):
    """Compare the live page against the baseline. Returns a report dict.

    The report is also appended to the 'drift' telemetry bucket so the dashboard
    can show it without re-running the analysis.
    """
    fingerprint_path = fingerprint_path or config.ACTIVE_FINGERPRINT_PATH
    engine = UIHeuristicEngine(fingerprint_path=fingerprint_path)
    fingerprints = engine.fingerprints or {}

    try:
        candidates = dom_features.collect_candidates(driver, limit=limit)
    except Exception as e:
        return {"error": f"DOM unreadable: {e}", "timestamp": _now()}

    findings = []

    for key, golden in fingerprints.items():
        by, value = _locator_of(golden)
        broken_identity = f"{by}='{value}'"
        _, score, metrics, best, reason, _second = engine.evaluate_live_candidates(
            broken_identity, candidates
        )
        matches = _resolve_count(driver, by, value)

        golden_rel = dom_features.relative_xpath(golden.get("xpath_pattern", ""))
        live_rel = dom_features.relative_xpath((best or {}).get("xpath", ""))
        moved = bool(best) and golden_rel != live_rel

        # Whether the recorded locator still RESOLVES is the primary evidence and
        # outranks the similarity score. A tracked element whose visible text
        # changed between runs (a counter, a total, a timestamp) scores poorly
        # against its fingerprint while remaining perfectly findable -- calling
        # that "missing" would report a break that does not exist. The score is
        # only consulted for locators that no longer resolve at all.
        if matches is not None and matches > 1:
            status, detail = "AMBIGUOUS", (
                f"'{value}' now matches {matches} elements. find_element will return the "
                f"first one silently, so this test can pass while asserting against the "
                f"wrong element."
            )
        elif matches == 1:
            if moved:
                status, detail = "MOVED", (
                    f"Still resolves, but its position changed "
                    f"({golden_rel or '?'} → {live_rel or '?'}). XPath-based locators for "
                    f"this element are now stale."
                )
            else:
                status, detail = "INTACT", "Still resolves to exactly one element."
        elif matches == 0 and score >= PRESENT_THRESHOLD:
            status, detail = "CHANGED", (
                f"'{value}' no longer resolves, but the element is still on the page "
                f"({score:.1f}% match). It will be healed on the next run. {reason}"
            )
        elif matches == 0:
            status, detail = "MISSING", (
                f"'{value}' no longer resolves and no live element resembles it "
                f"(best match {score:.1f}%). A test using it will fail, and should."
            )
        elif score >= INTACT_THRESHOLD:
            status, detail = "INTACT", "Unchanged."
        else:
            status, detail = "CHANGED", f"Attributes differ ({score:.1f}% match). {reason}"

        findings.append({
            "key": key,
            "locator": f"{by}='{value}'",
            "status": status,
            "detail": detail,
            "match_score": round(float(score), 2),
            "live_matches": matches,
            "tag_name": golden.get("tag_name", ""),
            "inner_text": (golden.get("inner_text") or "")[:60],
        })

    new_elements, removed_elements, snapshot_available = _compare_snapshot(
        candidates, fingerprint_path
    )

    summary = {}
    for finding in findings:
        summary[finding["status"]] = summary.get(finding["status"], 0) + 1
    summary["NEW"] = len(new_elements)
    summary["REMOVED"] = len(removed_elements)

    affected = [f for f in findings if f["status"] in ("MISSING", "AMBIGUOUS", "CHANGED", "MOVED")]

    report = {
        "timestamp": _now(),
        "app_id": getattr(config, "ACTIVE_APP_ID", ""),
        "url": _current_url(driver),
        "baseline_elements": len(fingerprints),
        "live_elements": len(candidates),
        "summary": summary,
        "findings": findings,
        "new_elements": new_elements,
        "removed_elements": removed_elements,
        "snapshot_available": snapshot_available,
        "verdict": _verdict(summary, len(affected), snapshot_available),
    }

    store.append("drift", {
        "timestamp": report["timestamp"],
        "app_id": report["app_id"],
        "url": report["url"],
        "summary": summary,
        "verdict": report["verdict"],
        "affected": len(affected),
    })
    return report


def _current_url(driver):
    try:
        return driver.current_url
    except Exception:
        return ""


def _compare_snapshot(candidates, fingerprint_path):
    """Elements added and removed since the baseline run.

    Compared against the whole-page snapshot taken on the day the baseline was
    learned, NOT against the fingerprint set. The fingerprints cover only the
    locators the test uses, so comparing against them would report every
    untouched heading and paragraph on the page as newly added.

    Returns (added, removed, snapshot_available).
    """
    try:
        with open(automation_wrapper.snapshot_path(fingerprint_path), "r", encoding="utf-8") as f:
            previous = json.load(f)
    except Exception:
        return [], [], False

    live = [{
        "tag_name": c.get("tag_name", ""),
        "rel_xpath": dom_features.relative_xpath(c.get("xpath", "")),
        "inner_text": (c.get("inner_text") or "")[:60],
        "element_id": c.get("element_id", ""),
        "css_class": c.get("css_class", ""),
    } for c in candidates if c.get("tag_name") not in dom_features.SNAPSHOT_EXCLUDED_TAGS]

    before = {dom_features.signature_key(e) for e in previous}
    after = {dom_features.signature_key(e) for e in live}

    added = [e for e in live if dom_features.signature_key(e) not in before]
    removed = [e for e in previous if dom_features.signature_key(e) not in after]
    return added, removed, True


def _verdict(summary, affected, snapshot_available=True):
    """One sentence a human can act on."""
    if summary.get("AMBIGUOUS"):
        return (f"AT RISK — {summary['AMBIGUOUS']} recorded locator(s) now match more than "
                f"one element. A test could pass against the wrong element.")
    if summary.get("MISSING"):
        return (f"BREAKING — {summary['MISSING']} tracked element(s) are gone. "
                f"Tests using them will fail and cannot be healed.")
    if affected:
        return (f"RECOVERABLE — {affected} tracked element(s) changed. The affected "
                f"lookups will be healed at runtime.")
    changed = summary.get("NEW", 0) + summary.get("REMOVED", 0)
    if changed:
        return (f"SAFE — the page changed ({summary.get('NEW', 0)} element(s) added, "
                f"{summary.get('REMOVED', 0)} removed) but no recorded locator is "
                f"affected. The test suite is unaffected by this change.")
    if not snapshot_available:
        return ("SAFE — no recorded locator is affected. (No page snapshot from the "
                "baseline run, so added elements cannot be listed; re-run the test to "
                "record one.)")
    return "SAFE — no change detected against the recorded baseline."


def format_report(report):
    """Render a report for the terminal."""
    if report.get("error"):
        return f"Drift analysis failed: {report['error']}"

    lines = [
        "",
        "=" * 68,
        f"  DRIFT ANALYSIS — {report.get('app_id') or 'unregistered app'}",
        f"  {report.get('url', '')}",
        "=" * 68,
        f"  baseline: {report['baseline_elements']} tracked element(s)   "
        f"live page: {report['live_elements']} element(s)",
        "",
    ]
    order = ["INTACT", "MOVED", "CHANGED", "AMBIGUOUS", "MISSING", "NEW", "REMOVED"]
    counts = "   ".join(
        f"{name}: {report['summary'].get(name, 0)}" for name in order
    )
    lines.append(f"  {counts}")
    lines.append("")

    for finding in report["findings"]:
        if finding["status"] == "INTACT":
            continue
        lines.append(f"  [{finding['status']}] {finding['locator']}")
        lines.append(f"      {finding['detail']}")

    for label, elements in (("ADDED", report.get("new_elements") or []),
                            ("REMOVED", report.get("removed_elements") or [])):
        if not elements:
            continue
        lines.append("")
        lines.append(f"  {label} SINCE THE BASELINE RUN ({len(elements)}):")
        for element in elements[:10]:
            text = (element.get("inner_text") or "").replace("\n", " ")[:50]
            if element.get("element_id"):
                ident = " #" + element["element_id"]
            elif element.get("css_class"):
                ident = " ." + ".".join(element["css_class"].split())
            else:
                ident = ""
            lines.append(f"      <{element.get('tag_name', '?')}>{ident} {text}".rstrip())
        if len(elements) > 10:
            lines.append(f"      ... and {len(elements) - 10} more")

    lines += ["", f"  VERDICT: {report['verdict']}", "=" * 68, ""]
    return "\n".join(lines)
