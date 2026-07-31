"""
Report Engine — renders a completed run as something a human can hand over.

A dashboard is only useful while it is on screen. A QA engineer attaching a heal
to a ticket, or a reviewer asking why a build passed, needs the same information
as a file. Every run already writes a self-contained record (run_context), so a
report is a rendering of that record rather than a second source of truth.

Three formats, all derived from the same run:
    markdown  -- readable, pasteable into a ticket or a PR
    csv       -- one row per heal, for a spreadsheet
    json      -- the raw run record
"""

import csv
import io
import json

BY_CONSTANTS = {
    "id": "By.ID", "name": "By.NAME", "css selector": "By.CSS_SELECTOR",
    "xpath": "By.XPATH", "link text": "By.LINK_TEXT",
    "partial link text": "By.PARTIAL_LINK_TEXT", "tag name": "By.TAG_NAME",
    "class name": "By.CLASS_NAME",
}

CSV_COLUMNS = [
    "timestamp", "app_id", "test_id", "run_id", "broken_selector",
    "repaired_by", "repaired_value", "confidence_score", "margin_over_second",
    "policy", "status", "reason", "recommendation",
]


def _selenium_tuple(heal):
    by = BY_CONSTANTS.get(heal.get("repaired_by", ""), "By.CSS_SELECTOR")
    return f'({by}, "{heal.get("repaired_value", "")}")'


def to_json(run):
    return json.dumps(run, indent=2)


def to_csv(run):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    for heal in run.get("heals", []):
        writer.writerow({column: heal.get(column, "") for column in CSV_COLUMNS})
    return buffer.getvalue()


def to_markdown(run):
    """A run report: what happened, what was repaired, and what QA should do."""
    heals = run.get("heals", [])
    refusals = run.get("refusals", [])
    status = run.get("status", "unknown")
    icon = {"passed": "PASSED", "failed": "FAILED"}.get(status, status.upper())

    lines = [
        f"# Self-healing run report — {run.get('app_id', '?')} / {run.get('test_id', '?')}",
        "",
        f"- **Result:** {icon}",
        f"- **Run id:** `{run.get('run_id', '')}`",
        f"- **Script:** `{run.get('script', '') or 'n/a'}`",
        f"- **Browser:** {run.get('browser', '')}",
        f"- **Started:** {run.get('started_at', '')}",
        f"- **Duration:** {run.get('duration_seconds', '?')}s",
        f"- **Heals:** {len(heals)}   **Refusals:** {len(refusals)}",
        "",
    ]

    if not heals and not refusals:
        lines += ["No locator required repair in this run.", ""]

    if heals:
        lines += ["## Repaired locators", ""]
        for heal in heals:
            scores = heal.get("details", {}).get("component_scores", {})
            lines += [
                f"### `{heal.get('broken_selector', '')}`",
                "",
                f"- **Repaired to:** `{_selenium_tuple(heal)}`"
                f"{'  *(derived from the live element)*' if heal.get('repaired_source') == 'live' else ''}",
                f"- **Confidence:** {heal.get('confidence_score', 0)}%"
                f" — {heal.get('policy', '')}"
                f" (margin over next-best: {heal.get('margin_over_second', 0)}%)",
                f"- **Rules:** " + ", ".join(f"{name.split('_')[0]} {value}%"
                                             for name, value in scores.items()),
                f"- **Why:** {heal.get('reason', '')}",
                f"- **Recommendation:** {heal.get('recommendation', '')}",
                "",
            ]

    if refusals:
        lines += ["## Refused (manual intervention required)", ""]
        for refusal in refusals:
            lines += [
                f"- `{refusal.get('broken_selector', '')}` — best match "
                f"{refusal.get('confidence_score', 0)}%, below the safety gate. "
                f"No element was interacted with.",
            ]
        lines.append("")

    if run.get("locators_used"):
        lines += ["## Locators this test depends on", ""]
        lines += [f"- `{locator}`" for locator in run["locators_used"]]
        lines.append("")

    lines += [
        "---",
        "",
        "*The application under test was not modified. The test script was not "
        "modified; repaired locators above are recommendations for review.*",
    ]
    return "\n".join(lines)


def patch_suggestions(run):
    """The edits a QA engineer would make, as a readable diff-style block.

    Deliberately rendered rather than applied: the framework repairs the
    execution of a test, never the committed test file.
    """
    heals = [h for h in run.get("heals", []) if h.get("repaired_value")]
    if not heals:
        return ""
    script = run.get("script", "your test script")
    lines = [f"--- {script}", f"+++ {script} (suggested)", ""]
    for heal in heals:
        broken = heal.get("broken_selector", "")
        if "='" in broken:
            by_raw, value = broken.split("='", 1)
            old = f'({BY_CONSTANTS.get(by_raw.strip(), "By.CSS_SELECTOR")}, "{value.rstrip(chr(39))}")'
        else:
            old = broken
        lines += [f"- {old}", f"+ {_selenium_tuple(heal)}", ""]
    return "\n".join(lines)
