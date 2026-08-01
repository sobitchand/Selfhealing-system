"""
Visibility & Control layer: live view of every heal the system performs.

Reads the per-bucket store written by the healing engine (store.py) and the
metrics history written by the infrastructure monitor. Read-only -- nothing here
triggers a heal.

    python -m streamlit run dashboard.py

Set DASH_NO_REFRESH=1 to freeze the page (used when capturing screenshots).
"""

import html
import json
import os
import sys
import time

import pandas as pd
import plotly.express as px
import streamlit as st

import app_registry
import config
import config_manager
import reports
import run_context
import store
import test_registry
import theme

# Apply configuration overrides at startup
config_manager.apply_overrides()

st.set_page_config(page_title="Self-Healing Control Panel", layout="wide")
st.markdown(theme.stylesheet(), unsafe_allow_html=True)

ROW_LIMIT = 12  # most recent rows per table; keeps the chart above the fold


def load_json_file(path, default_factory):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_factory()
    return default_factory()


def newest_first(records, limit=ROW_LIMIT):
    ordered = sorted(records, key=lambda r: r.get("timestamp", ""), reverse=True)
    return ordered[:limit]


def clock(timestamp):
    """Trim an ISO timestamp to something a person can read at a glance. The
    year is dropped -- it is never the interesting part and it costs column
    width the heal table cannot spare."""
    text = str(timestamp or "")
    return text[5:19].replace("T", "  ") if len(text) >= 19 else text


def esc(value):
    return html.escape("" if value is None else str(value))


def pct(value):
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def score(value):
    """A rule component, as a bare integer. Percent signs on four numbers in one
    cell is noise -- the column header carries the unit."""
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return "—"


def _script(name, args, spinner, timeout=120):
    """Run one of the project's own scripts and surface its output verbatim.

    The dashboard is read-only about healing: these buttons are shortcuts for
    the commands in the demo guide, not a second code path. Showing raw stdout
    keeps them auditable -- what you see here is what the terminal would print.
    """
    import subprocess

    with st.spinner(spinner):
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(config.BASE_DIR, name), *args],
                cwd=config.BASE_DIR, capture_output=True, text=True, timeout=timeout,
                # Every entry point reconfigures its stdout to UTF-8 (config.py)
                # so the emoji in its progress output survive. Decoding that with
                # the Windows cp1252 default raises UnicodeDecodeError inside
                # subprocess's reader thread and silently loses the output.
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            st.error(f"{name} timed out after {timeout}s")
            return False
        except Exception as exc:
            st.error(f"{name} could not be started: {exc}")
            return False

    # Read by the auto-refresh guard at the bottom of the page: without it the
    # 3s rerun clears this output before anyone can read it.
    st.session_state["cmd_output_pending"] = True

    if result.stdout:
        st.code(result.stdout[-4000:], language="text")
    if result.returncode != 0:
        st.error(result.stderr[-2000:] or f"{name} exited with {result.returncode}")
        return False
    st.success(f"{name} finished. Press R to refresh the other tabs.")
    return True


def _cli(args, spinner, timeout=120):
    """Run a cli.py subcommand. Same contract as _script."""
    return _script("cli.py", args, spinner, timeout=timeout)


logs = store.read_all()
history = load_json_file(config.METRICS_HISTORY_PATH, list)

st.markdown(
    theme.masthead(
        "Self-Healing Control Panel",
        "Rule-based recovery for web-application test automation and "
        "infrastructure. Every locator heal, source write-back and infrastructure "
        "action the system takes is recorded here.",
    ),
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Sidebar — scope: which application, which test, which run.
#
# Every heal, refusal and drift report is stamped with the run that produced it
# (run_context), so the whole page can be narrowed to one execution instead of
# showing one undifferentiated list across every application ever tested.
# --------------------------------------------------------------------------
ALL = "All"

with st.sidebar:
    st.markdown("### Scope")

    apps = app_registry.list_apps()
    app_labels = [ALL] + [a["app_id"] for a in apps]
    selected_app = st.selectbox("Application", app_labels, key="scope_app")

    tests = test_registry.list_tests(selected_app) if selected_app != ALL else []
    test_labels = [ALL] + [t["test_id"] for t in tests]
    selected_test = st.selectbox("Test", test_labels, key="scope_test",
                                 disabled=selected_app == ALL)

    runs = run_context.list_runs(
        app_id=None if selected_app == ALL else selected_app,
        test_id=None if selected_test == ALL else selected_test,
        limit=40,
    )
    run_labels = [ALL] + [
        f"{r['run_id']}  ({r.get('status', '?')}, {r.get('heal_count', 0)} heals)"
        for r in runs
    ]
    selected_run_label = st.selectbox("Run", run_labels, key="scope_run")
    selected_run_id = (
        None if selected_run_label == ALL
        else selected_run_label.split("  ")[0]
    )

    if not apps:
        st.info("No applications registered.\n\n`python cli.py register --app <id> --url <url>`")

    st.divider()
    st.markdown("### Live Metrics")
    
    # Read metrics directly with robust error handling
    metrics_data = None
    metrics_error = None
    try:
        if os.path.exists(config.METRICS_HISTORY_PATH):
            with open(config.METRICS_HISTORY_PATH, "r", encoding="utf-8") as f:
                metrics_data = json.load(f)
        else:
            metrics_error = f"File not found: {config.METRICS_HISTORY_PATH}"
    except Exception as e:
        metrics_error = str(e)
    
    if metrics_error:
        st.error(f"Metrics error: {metrics_error}")
    elif metrics_data and len(metrics_data) > 0:
        latest = metrics_data[-1]
        
        # Application status
        is_up = latest.get("service_health") == "Up"
        if is_up:
            st.success("Application Up")
        else:
            st.error("Application Down")
        
        # Metrics
        st.metric("Traffic", f"{latest.get('traffic_rate', 0)} req/s")
        st.metric("Active Requests", latest.get("active_requests", 0))
        st.metric("Error Rate", f"{latest.get('error_rate_percent', 0.0)}%")
        st.metric("Disk Usage", f"{latest.get('disk_usage_percent', 0.0)}%")
    else:
        st.info("No metrics data available yet. Start the target application.")

def in_scope(record):
    """Whether a stamped record belongs to the current selection.

    Records written before run stamping existed carry no app/test/run, so they
    are only shown when nothing is being filtered -- otherwise an unattributable
    row would appear under whichever application happened to be selected.
    """
    if selected_run_id:
        return record.get("run_id") == selected_run_id
    if selected_app != ALL and record.get("app_id") != selected_app:
        return False
    if selected_test != ALL and record.get("test_id") != selected_test:
        return False
    return True


def scoped(bucket):
    return [record for record in logs.get(bucket, []) if in_scope(record)]


scope_label = (
    selected_run_id if selected_run_id
    else f"{selected_app}"
    + (f" / {selected_test}" if selected_test != ALL else "")
)

tab_apps, tab_ui, tab_approval, tab_drift, tab_source, tab_infra, tab_alerts, tab_analytics, tab_config = st.tabs(
    ["Applications", "Locator healing", "Approval Queue", "Change impact", "Source write-back",
     "Infrastructure", "Alerts", "Analytics", "Configuration"]
)

# --------------------------------------------------------------------------
# Applications — the registry, its baselines, its tests and its runs
# --------------------------------------------------------------------------
with tab_apps:
    st.markdown(
        theme.section(
            "Registered applications",
            "Each application has its own Golden Fingerprint baseline, learned "
            "from a passing test run. Nothing here is specific to any one "
            "application: register a URL and run a Selenium script against it.",
        ),
        unsafe_allow_html=True,
    )

    if not apps:
        st.markdown(
            theme.empty("No applications registered yet. "
                        "Run: python cli.py register --app <id> --url <url>"),
            unsafe_allow_html=True,
        )
    else:
        rows = []
        for record in apps:
            fingerprints = load_json_file(record.get("fingerprint_path", ""), dict)
            app_tests = test_registry.list_tests(record["app_id"])
            rows.append({
                "app": esc(record["app_id"]),
                "name": esc(record.get("app_name", "")),
                "url": esc((record.get("base_url") or "—")[:60]),
                "baseline": (f"{len(fingerprints)} element(s)" if fingerprints
                             else theme.pill("failed")),
                "recorded": esc(clock(record.get("baseline_recorded_at")) or "never"),
                "tests": len(app_tests),
            })
        st.markdown(
            theme.table(rows, [
                ("app", "Application"), ("name", "Name"), ("url", "URL / file"),
                ("baseline", "Fingerprint status"), ("recorded", "Baseline recorded"),
                ("tests", "Tests"),
            ], aligns={"app": "mono", "url": "mono", "tests": "num"}),
            unsafe_allow_html=True,
        )

    if selected_app != ALL:
        st.markdown(theme.section(f"Tests — {selected_app}",
                                  "Registered on first run. The locators listed are the "
                                  "ones each test actually resolved during a passing run, "
                                  "not a hand-maintained list."),
                    unsafe_allow_html=True)
        app_tests = test_registry.list_tests(selected_app)
        if not app_tests:
            st.markdown(theme.empty("No test has run against this application yet."),
                        unsafe_allow_html=True)
        else:
            rows = []
            for record in app_tests:
                success = record.get("last_success") or {}
                failure = record.get("last_failure") or {}
                rows.append({
                    "test": esc(record["test_id"]),
                    "script": esc(os.path.basename(record.get("script", "")) or "—"),
                    "health": theme.pill({"passing": "success", "failing": "failed",
                                          "healing": "warning"}.get(
                                              test_registry.health(record), "warning")),
                    "locators": len(record.get("locators_used", [])),
                    "ok": esc(clock(success.get("at")) or "never"),
                    "bad": esc(clock(failure.get("at")) or "never"),
                    "runs": record.get("total_runs", 0),
                    "heals": record.get("total_heals", 0),
                })
            st.markdown(
                theme.table(rows, [
                    ("test", "Test"), ("script", "Script"), ("health", "State"),
                    ("locators", "Locators"), ("ok", "Last success"),
                    ("bad", "Last failure"), ("runs", "Runs"), ("heals", "Heals"),
                ], aligns={"test": "mono", "script": "mono", "locators": "num",
                           "runs": "num", "heals": "num"}),
                unsafe_allow_html=True,
            )

    # ---- Run history + export -------------------------------------------
    st.markdown(theme.section("Run history",
                              "One record per execution. Selecting a run in the sidebar "
                              "filters every other tab to that execution."),
                unsafe_allow_html=True)
    if not runs:
        st.markdown(theme.empty("No runs recorded for this scope yet."),
                    unsafe_allow_html=True)
    else:
        rows = [{
            "run": esc(r["run_id"]),
            "app": esc(r.get("app_id", "")),
            "test": esc(r.get("test_id", "")),
            "result": theme.pill("success" if r.get("status") == "passed" else "failed"),
            "heals": r.get("heal_count", 0),
            "refusals": r.get("refusal_count", 0),
            "duration": f"{r.get('duration_seconds', 0)}s",
            "when": esc(clock(r.get("started_at"))),
        } for r in runs[:ROW_LIMIT]]
        st.markdown(
            theme.table(rows, [
                ("run", "Run"), ("app", "Application"), ("test", "Test"),
                ("result", "Result"), ("heals", "Heals"), ("refusals", "Refusals"),
                ("duration", "Duration"), ("when", "Started"),
            ], aligns={"run": "mono", "heals": "num", "refusals": "num",
                       "duration": "num"}),
            unsafe_allow_html=True,
        )

        if selected_run_id:
            record = run_context.load(selected_run_id)
            if record:
                st.markdown(theme.section("Export report",
                                          "The selected run as a hand-over artefact."),
                            unsafe_allow_html=True)
                col1, col2, col3 = st.columns(3)
                col1.download_button("Markdown report", reports.to_markdown(record),
                                     file_name=f"{selected_run_id}.md",
                                     mime="text/markdown", width="stretch")
                col2.download_button("Heals (CSV)", reports.to_csv(record),
                                     file_name=f"{selected_run_id}.csv",
                                     mime="text/csv", width="stretch")
                col3.download_button("Raw run (JSON)", reports.to_json(record),
                                     file_name=f"{selected_run_id}.json",
                                     mime="application/json", width="stretch")

                patch = reports.patch_suggestions(record)
                if patch:
                    st.markdown("**Suggested test-script changes** — never applied "
                                "automatically; copy them if you agree.")
                    st.code(patch, language="diff")

# --------------------------------------------------------------------------
# Change impact — what the developer changed, and whether it threatens the suite
# --------------------------------------------------------------------------
with tab_drift:
    st.markdown(
        theme.section(
            "Change impact analysis",
            "Run python cli.py check --app <id> after a developer edits the "
            "markup. It compares the live page against the recorded baseline "
            "without running the suite, so a change that breaks nothing still "
            "produces an answer instead of silence.",
        ),
        unsafe_allow_html=True,
    )

    drift_records = [
        record for record in logs.get("drift", [])
        if selected_app == ALL or record.get("app_id") == selected_app
    ]
    if not drift_records:
        st.markdown(
            theme.empty("No change-impact analysis recorded yet. "
                        "Run: python cli.py check --app <id>"),
            unsafe_allow_html=True,
        )
    else:
        latest = drift_records[-1]
        verdict = latest.get("verdict", "")
        if verdict.startswith("AT RISK") or verdict.startswith("BREAKING"):
            st.error(verdict)
        elif verdict.startswith("RECOVERABLE"):
            st.warning(verdict)
        else:
            st.success(verdict)

        summary = latest.get("summary", {})
        st.markdown(
            theme.stat_row([
                ("Unchanged", summary.get("INTACT", 0)),
                ("Moved", summary.get("MOVED", 0)),
                ("Changed", summary.get("CHANGED", 0)),
                ("Ambiguous", summary.get("AMBIGUOUS", 0)),
                ("Missing", summary.get("MISSING", 0)),
                ("Added", summary.get("NEW", 0)),
            ]),
            unsafe_allow_html=True,
        )

        rows = [{
            "time": esc(clock(record.get("timestamp"))),
            "app": esc(record.get("app_id", "")),
            "url": esc((record.get("url") or "")[:50]),
            "affected": record.get("affected", 0),
            "verdict": esc(record.get("verdict", "")[:70]),
        } for record in newest_first(drift_records)]
        st.markdown(
            theme.table(rows, [
                ("time", "Time"), ("app", "Application"), ("url", "Page"),
                ("affected", "Affected locators"), ("verdict", "Verdict"),
            ], aligns={"url": "mono", "affected": "num"}),
            unsafe_allow_html=True,
        )

# --------------------------------------------------------------------------
# Locator healing
# --------------------------------------------------------------------------
with tab_ui:
    records = scoped("ui_heals")
    st.caption(f"Showing: {scope_label}")
    st.markdown(
        theme.section(
            "Locator heals",
            "When a test's locator no longer matches anything, the engine scores "
            "every live element against the golden fingerprint. R1 is visible "
            "text (40%), R2 tree position (30%), R3 CSS class (20%), R4 "
            "neighbouring elements (10%).",
        ),
        unsafe_allow_html=True,
    )

    if not records:
        st.markdown(
            theme.empty("No locator failures recorded yet. Run python demo.py."),
            unsafe_allow_html=True,
        )
    else:
        df = pd.DataFrame(records)
        # A heal queued for approval was still applied at runtime; classify it
        # by the policy the engine assigned, not the review-queue status.
        successes = len([r for r in records if r.get("status") == "success"
                         or (r.get("status") == "pending_approval"
                             and r.get("policy") == "AUTOMATIC HEAL")])
        warnings = len([r for r in records if r.get("status") == "warning"
                        or (r.get("status") == "pending_approval"
                            and r.get("policy") != "AUTOMATIC HEAL")])
        failures = len([
            a for a in scoped("alerts") if a.get("source") == "UIHeuristicEngine"
        ])
        rerouted = successes + warnings
        interruptions = rerouted + failures

        st.markdown(
            theme.stat_row([
                ("Locator failures", interruptions),
                ("Automatic heals", successes),
                ("Healing rate", f"{(rerouted / interruptions * 100) if interruptions else 0:.0f}%"),
                ("Success rate", f"{(successes / rerouted * 100) if rerouted else 0:.0f}%"),
            ]),
            unsafe_allow_html=True,
        )

        rows = []
        for record in newest_first(records):
            components = (record.get("details") or {}).get("component_scores", {}) \
                if isinstance(record.get("details"), dict) else {}
            # The engine renamed its score keys; accept both spellings so heals
            # recorded before the rename still show their breakdown instead of
            # four em-dashes.
            breakdown = " · ".join(
                score(components.get(new, components.get(old)))
                for new, old in (
                    ("R1_inner_text_40", "R1_text_40"),
                    ("R2_xpath_pattern_30", "R2_xpath_30"),
                    ("R3_css_class_20", "R3_css_20"),
                    ("R4_neighbors_10", "R4_neighbors_10"),
                )
            )
            repaired = record.get("repaired_value") or record.get("recovered_selector") or "—"
            if record.get("repaired_by"):
                repaired = f"{record['repaired_by']}={repaired}"
            rows.append({
                "time": esc(clock(record.get("timestamp"))),
                "test": esc(record.get("test_id") or "—"),
                "broken": esc(record.get("broken_selector")),
                "repaired": esc(repaired),
                "confidence": pct(record.get("confidence_score")),
                "components": breakdown,
                "status": theme.pill(record.get("status")),
            })

        st.markdown(
            theme.table(
                rows,
                [("time", "Time"), ("test", "Test"), ("broken", "Broken locator"),
                 ("repaired", "New runtime locator"), ("confidence", "Confidence"),
                 ("components", "R1 · R2 · R3 · R4"), ("status", "Outcome")],
                aligns={"broken": "mono", "repaired": "mono", "confidence": "num",
                        "components": "num"},
            ) + theme.table_note(min(ROW_LIMIT, len(records)), len(records), "heals"),
            unsafe_allow_html=True,
        )

        st.markdown(theme.section("Why each locator was repaired",
                                  "The rules that decided the match, and the change "
                                  "recommended to the QA engineer."),
                    unsafe_allow_html=True)
        for record in newest_first(records)[:6]:
            with st.expander(
                f"{record.get('broken_selector', '?')}  →  "
                f"{record.get('repaired_value', '?')}   "
                f"({record.get('confidence_score', 0)}%)"
            ):
                st.markdown(f"**Reason:** {record.get('reason') or '—'}")
                st.markdown(f"**Recommendation:** {record.get('recommendation') or '—'}")
                margin = record.get("margin_over_second")
                if margin is not None:
                    st.markdown(f"**Margin over next-best candidate:** {margin}%")
                if record.get("repaired_source"):
                    st.caption(
                        "Locator derived from the live element."
                        if record["repaired_source"] == "live"
                        else "Live element carries no identifying attribute; locator "
                             "derived from the recorded baseline."
                    )

        # ---- Per-heal detail: Reason for repair + QA recommendation (report §3.7) ----
        st.markdown(
            theme.section(
                "Heal details",
                "Every heal includes a human-readable reason explaining which "
                "attributes matched and which changed, plus a recommendation "
                "for the QA team.",
            ),
            unsafe_allow_html=True,
        )
        for record in newest_first(records, limit=ROW_LIMIT):
            reason = record.get("reason") or "No reason recorded."
            recommendation = record.get("recommendation") or "No recommendation recorded."
            margin = record.get("margin_over_second")
            broken = esc(record.get("broken_selector"))
            recovered = esc(record.get("recovered_selector"))
            conf = pct(record.get("confidence_score"))
            components = (record.get("details") or {}).get("component_scores", {}) \
                if isinstance(record.get("details"), dict) else {}

            with st.expander(
                f"{broken} → {recovered} ({conf})",
                expanded=False,
            ):
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    st.markdown("**Reason for repair**")
                    st.info(reason)
                    if margin is not None:
                        st.caption(f"Margin over second-best candidate: {margin}%")
                with col_b:
                    st.markdown("**Recommendation for QA**")
                    st.warning(recommendation)

                st.markdown("**Rule breakdown**")
                r1 = components.get("R1_inner_text_40", components.get("R1_text_40", 0))
                r2 = components.get("R2_xpath_pattern_30", components.get("R2_xpath_30", 0))
                r3 = components.get("R3_css_class_20", components.get("R3_css_20", 0))
                r4 = components.get("R4_neighbors_10", 0)
                st.markdown(
                    f"- R1 (visible text, 40%): **{r1:.0f}%**\n"
                    f"- R2 (XPath structure, 30%): **{r2:.0f}%**\n"
                    f"- R3 (CSS class, 20%): **{r3:.0f}%**\n"
                    f"- R4 (neighbouring elements, 10%): **{r4:.0f}%**"
                )

        st.markdown(theme.section("Confidence over time"), unsafe_allow_html=True)
        chart_df = df.copy()
        chart_df["when"] = pd.to_datetime(
            chart_df["timestamp"], format="ISO8601"
        ).dt.strftime("%d %b %H:%M:%S")
        figure = px.bar(
            chart_df,
            x="when",
            y="confidence_score",
            color="status",
            labels={"when": "", "confidence_score": "Confidence"},
            color_discrete_map=theme.STATUS_COLORS,
            template="plotly_white",
        )
        figure.update_layout(
            font=dict(family=theme.FONT_STACK, size=13, color=theme.INK),
            yaxis=dict(range=[0, 100], ticksuffix="%", dtick=25,
                       gridcolor=theme.RULE, zeroline=False),
            xaxis=dict(type="category", showgrid=False),
            barmode="group",
            bargap=0.45,
            margin=dict(l=10, r=10, t=10, b=10),
            height=330,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="left", x=0, title=""),
        )
        st.plotly_chart(figure, width="stretch",
                        config={"displayModeBar": False})

        # ---- Log history per locator (report §3.7) ----
        st.markdown(
            theme.section(
                "Log history by locator",
                "Every heal event for a given broken locator, chronologically, "
                "so recurring breakage on the same element is visible at a glance.",
            ),
            unsafe_allow_html=True,
        )
        by_locator = {}
        for r in sorted(records, key=lambda x: x.get("timestamp", "")):
            loc = r.get("broken_selector", "unknown")
            by_locator.setdefault(loc, []).append(r)
        for loc, events in by_locator.items():
            if len(events) >= 1:
                with st.expander(
                    f"{esc(loc)} — {len(events)} heal(s)",
                    expanded=False,
                ):
                    hist_rows = []
                    for e in events:
                        hist_rows.append({
                            "time": esc(clock(e.get("timestamp"))),
                            "confidence": pct(e.get("confidence_score")),
                            "recovered": esc(e.get("recovered_selector")),
                            "status": theme.pill(e.get("status")),
                        })
                    st.markdown(
                        theme.table(
                            hist_rows,
                            [("time", "Time"), ("confidence", "Confidence"),
                             ("recovered", "Recovered"), ("status", "Outcome")],
                            aligns={"confidence": "num"},
                        ),
                        unsafe_allow_html=True,
                    )

# --------------------------------------------------------------------------
# Approval Queue
# --------------------------------------------------------------------------
with tab_approval:
    from approval_workflow import workflow
    
    st.markdown(
        theme.section(
            "Approval Queue",
            "Healed locators awaiting human review. Approve to update the test script, "
            "reject to leave it unchanged, or rollback to undo an approved change. "
            "This is the industry best practice for safe script updates.",
        ),
        unsafe_allow_html=True,
    )
    
    pending = workflow.get_pending_heals()
    approval_history = workflow.get_history(limit=20)
    
    approved_count = len([h for h in approval_history if h["status"] == "approved"])
    rejected_count = len([h for h in approval_history if h["status"] == "rejected"])
    rolled_back_count = len([h for h in approval_history if h["status"] == "rolled_back"])
    
    st.markdown(
        theme.stat_row([
            ("Pending Review", len(pending)),
            ("Approved", approved_count),
            ("Rejected", rejected_count),
            ("Rolled Back", rolled_back_count),
        ]),
        unsafe_allow_html=True,
    )
    
    if pending:
        st.markdown(
            theme.section("Pending Approvals", f"{len(pending)} heal(s) waiting for review"),
            unsafe_allow_html=True,
        )
        
        for heal in pending:
            with st.expander(
                f"**{os.path.basename(heal['script_path'])}** — "
                f"Confidence: {heal['confidence']}% — {heal['heal_id']}",
                expanded=True
            ):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**Script:** `{heal['script_path']}`")
                    st.markdown(f"**Timestamp:** {clock(heal['timestamp'])}")
                    if heal.get('line_number'):
                        st.markdown(f"**Line:** {heal['line_number']}")
                    
                    st.markdown("**Change:**")
                    st.markdown(f"- **Old:** `{esc(heal['old_locator'])}`")
                    st.markdown(f"- **New:** `{esc(heal['new_locator'])}`")
                    
                    st.markdown("**Confidence Breakdown:**")
                    metrics = heal.get('metrics', {})

                    def rule_score(*names):
                        """The engine writes R1_inner_text_40 / R2_xpath_pattern_30 /
                        R3_css_class_20; accept the shorter historical spellings too so
                        entries queued by an older build still render."""
                        for name in names:
                            if name in metrics:
                                return float(metrics[name] or 0)
                        return 0.0

                    st.markdown(
                        f"- R1 (Text): {rule_score('R1_inner_text_40', 'R1_text_40'):.0f}%\n"
                        f"- R2 (XPath): {rule_score('R2_xpath_pattern_30', 'R2_xpath_30'):.0f}%\n"
                        f"- R3 (CSS): {rule_score('R3_css_class_20', 'R3_css_20'):.0f}%\n"
                        f"- R4 (Neighbors): {rule_score('R4_neighbors_10'):.0f}%"
                    )
                    
                    st.markdown("**Diff:**")
                    st.code(heal.get('diff', 'No diff available'), language='diff')
                
                with col2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    if st.button("✅ Approve", key=f"approve_{heal['heal_id']}", width="stretch"):
                        success, msg = workflow.approve_heal(heal['heal_id'], create_pr=False)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                    
                    reason = st.text_input(
                        "Rejection reason (optional)",
                        key=f"reason_{heal['heal_id']}",
                        placeholder="e.g., Wrong element matched"
                    )
                    
                    if st.button("❌ Reject", key=f"reject_{heal['heal_id']}", width="stretch"):
                        success, msg = workflow.reject_heal(heal['heal_id'], reason or None)
                        if success:
                            st.warning(msg)
                            st.rerun()
                        else:
                            st.error(msg)
    else:
        st.markdown(
            theme.empty("No pending approvals. All heals have been reviewed."),
            unsafe_allow_html=True,
        )
    
    if approval_history:
        st.markdown(
            theme.section("Approval History", "Recent approval decisions"),
            unsafe_allow_html=True,
        )
        
        rows = []
        for heal in approval_history[:10]:
            status_pill = theme.pill(heal['status'])
            rows.append({
                "time": esc(clock(heal['timestamp'])),
                "script": esc(os.path.basename(heal['script_path'])),
                "confidence": pct(heal['confidence']),
                "change": esc(f"{heal['old_locator'][:30]} → {heal['new_locator'][:30]}"),
                "status": status_pill,
                "action": "",
            })
        
        st.markdown(
            theme.table(
                rows,
                [("time", "Time"), ("script", "Script"), ("confidence", "Confidence"),
                 ("change", "Change"), ("status", "Status"), ("action", "Action")],
                aligns={"confidence": "num", "change": "mono"},
            ),
            unsafe_allow_html=True,
        )
        
        st.markdown("**Rollback approved heals:**")
        approved_heals = [h for h in approval_history if h['status'] == 'approved']
        if approved_heals:
            for heal in approved_heals[:5]:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(
                        f"`{os.path.basename(heal['script_path'])}` — "
                        f"{heal['heal_id']} — {clock(heal['timestamp'])}"
                    )
                with col2:
                    if st.button("↩️ Rollback", key=f"rollback_{heal['heal_id']}"):
                        success, msg = workflow.rollback_heal(heal['heal_id'])
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
        else:
            st.info("No approved heals to rollback")
        
        if st.button("🗑️ Clear completed", type="secondary"):
            removed = workflow.clear_completed()
            st.success(f"Cleared {removed} completed entries")
            st.rerun()

# --------------------------------------------------------------------------
# Source write-back
# --------------------------------------------------------------------------
with tab_source:
    records = logs.get("source_heals", [])
    st.markdown(
        theme.section(
            "Source write-back",
            "After a high-confidence heal the corrected locator is written back "
            "into the automation source, so the next run needs no heal at all. "
            "Each file keeps a .bak before its first edit.",
        ),
        unsafe_allow_html=True,
    )

    if not records:
        st.markdown(
            theme.empty("No write-backs yet. They follow a heal above 75% confidence."),
            unsafe_allow_html=True,
        )
    else:
        files = len({r.get("file") for r in records})
        st.markdown(
            theme.stat_row([("Patches applied", len(records)), ("Files touched", files)]),
            unsafe_allow_html=True,
        )
        rows = [{
            "time": esc(clock(r.get("timestamp"))),
            "file": esc(r.get("file")),
            "before": esc(r.get("broken_token")),
            "after": esc(r.get("healed_token")),
            "count": esc(r.get("occurrences")),
            "status": theme.pill("success" if r.get("status") == "patched" else r.get("status")),
        } for r in newest_first(records)]
        st.markdown(
            theme.table(
                rows,
                [("time", "Time"), ("file", "File"), ("before", "Before"),
                 ("after", "After"), ("count", "Occurrences"), ("status", "Outcome")],
                aligns={"before": "mono", "after": "mono", "count": "num"},
            ) + theme.table_note(min(ROW_LIMIT, len(records)), len(records), "patches"),
            unsafe_allow_html=True,
        )

# --------------------------------------------------------------------------
# Infrastructure
# --------------------------------------------------------------------------
with tab_infra:
    records = logs.get("infrastructure", [])
    st.markdown(
        theme.section(
            "Infrastructure recoveries",
            "The monitor watches disk, error rate and service health, and fires "
            "a rule-based recovery action when a threshold is crossed.",
        ),
        unsafe_allow_html=True,
    )

    if not records:
        st.markdown(
            theme.empty("No infrastructure anomalies recorded yet."),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            theme.stat_row([("Recovery actions", len(records))]),
            unsafe_allow_html=True,
        )
        rows = [{
            "time": esc(clock(r.get("timestamp"))),
            "trigger": esc(r.get("trigger_metric")),
            "action": esc(r.get("action_executed")),
            "status": theme.pill("success" if r.get("status") == "resolved" else r.get("status")),
        } for r in newest_first(records)]
        st.markdown(
            theme.table(
                rows,
                [("time", "Time"), ("trigger", "Trigger"),
                 ("action", "Action taken"), ("status", "Outcome")],
            ) + theme.table_note(min(ROW_LIMIT, len(records)), len(records), "actions"),
            unsafe_allow_html=True,
        )

# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------
with tab_alerts:
    records = scoped("alerts")
    st.caption(f"Showing: {scope_label}")
    st.markdown(
        theme.section(
            "Alerts",
            "Raised when the system deliberately declines to act: a match below "
            "the 20% safety gate, a locator that failed to heal three times in a "
            "row, or a fault reported by the in-browser agent.",
        ),
        unsafe_allow_html=True,
    )

    if not records:
        st.markdown(theme.empty("No active alerts."), unsafe_allow_html=True)
    else:
        critical = len([r for r in records if r.get("severity") == "critical"])
        st.markdown(
            theme.stat_row([("Total alerts", len(records)), ("Critical", critical)]),
            unsafe_allow_html=True,
        )
        st.markdown(
            "".join(
                theme.alert(clock(r.get("timestamp")), r.get("source"),
                            r.get("severity"), r.get("message"))
                for r in newest_first(records)
            ) + theme.table_note(min(ROW_LIMIT, len(records)), len(records), "alerts"),
            unsafe_allow_html=True,
        )

# --------------------------------------------------------------------------
# Analytics (Advanced Features)
# --------------------------------------------------------------------------
with tab_analytics:
    try:
        import analytics
        analytics_data = analytics.run_analytics()
    except Exception as e:
        analytics_data = None
        st.markdown(
            theme.empty(f"Analytics unavailable: {e}"),
            unsafe_allow_html=True,
        )

    if analytics_data:
        st.markdown(
            theme.section(
                "Advanced Analytics",
                "Locator stability scoring, flaky test detection, and cost analysis. "
                "Features that Healenium and Testim do not provide.",
            ),
            unsafe_allow_html=True,
        )

        # Cost analysis summary
        cost = analytics_data["cost_analysis"]["summary"]
        st.markdown(
            theme.stat_row([
                ("Total heals", cost["total_heals"]),
                ("Time saved", f"{cost['time_saved_hours']:.1f}h"),
                ("Cost saved", f"${cost['cost_saved_usd']:.0f}"),
                ("ROI", f"{cost['roi_percentage']:.0f}%"),
            ]),
            unsafe_allow_html=True,
        )

        # Healing Accuracy Metrics
        st.markdown(
            theme.section(
                "Healing Accuracy Metrics",
                "Real-time performance metrics showing healing success rate, "
                "confidence distribution, and system reliability.",
            ),
            unsafe_allow_html=True,
        )

        ui_heals = logs.get("ui_heals", [])
        if ui_heals:
            total_heals = len(ui_heals)
            # pending_approval heals were applied at runtime; classify by policy.
            successful_heals = len([h for h in ui_heals if h.get("status") == "success"
                                    or (h.get("status") == "pending_approval"
                                        and h.get("policy") == "AUTOMATIC HEAL")])
            cautious_heals = len([h for h in ui_heals if h.get("status") == "warning"
                                  or (h.get("status") == "pending_approval"
                                      and h.get("policy") != "AUTOMATIC HEAL")])
            failed_heals = len([h for h in ui_heals if h.get("status") == "failed"])
            
            success_rate = (successful_heals / total_heals * 100) if total_heals > 0 else 0
            
            confidence_scores = [h.get("confidence_score", 0) for h in ui_heals if h.get("confidence_score")]
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
            
            high_conf = len([s for s in confidence_scores if s >= 75])
            medium_conf = len([s for s in confidence_scores if 20 <= s < 75])
            low_conf = len([s for s in confidence_scores if s < 20])
            
            st.markdown(
                theme.stat_row([
                    ("Success Rate", f"{success_rate:.1f}%"),
                    ("Avg Confidence", f"{avg_confidence:.1f}%"),
                    ("High (≥75%)", f"{high_conf}"),
                    ("Medium (20-75%)", f"{medium_conf}"),
                ]),
                unsafe_allow_html=True,
            )
            
            # Confidence distribution chart
            if confidence_scores:
                import pandas as pd
                import plotly.express as px
                
                df_conf = pd.DataFrame({
                    "Heal": range(1, len(confidence_scores) + 1),
                    "Confidence": confidence_scores
                })
                
                fig = px.scatter(
                    df_conf,
                    x="Heal",
                    y="Confidence",
                    title="Confidence Score Distribution",
                    labels={"Heal": "Heal #", "Confidence": "Confidence (%)"},
                )
                fig.add_hline(y=75, line_dash="dash", line_color="green", 
                             annotation_text="Auto-heal threshold")
                fig.add_hline(y=20, line_dash="dash", line_color="orange", 
                             annotation_text="Safety gate")
                fig.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig, width="stretch")
        else:
            st.info("No healing data available yet. Run tests to generate metrics.")

        # Locator stability
        st.markdown(
            theme.section(
                "Locator Stability",
                "Predicts which locators are likely to break. Score 0-100, "
                "higher is more stable. Based on ID specificity, semantic meaning, "
                "uniqueness, DOM depth, and text content.",
            ),
            unsafe_allow_html=True,
        )

        stability = analytics_data["locator_stability"]
        if stability:
            rows = []
            for s in sorted(stability, key=lambda x: x["stability_score"])[:10]:
                rows.append({
                    "locator": esc(s["locator"]),
                    "score": f"{s['stability_score']}/100",
                    "level": theme.pill(s["stability_level"]),
                    "risk": theme.pill(s["breakage_risk"]),
                    "recommendation": esc(s["recommendation"][:80]),
                })
            st.markdown(
                theme.table(
                    rows,
                    [("locator", "Locator"), ("score", "Score"), ("level", "Level"),
                     ("risk", "Risk"), ("recommendation", "Recommendation")],
                    aligns={"locator": "mono", "score": "num"},
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                theme.empty("No fingerprints to analyze. Run Learning Mode first."),
                unsafe_allow_html=True,
            )

        # Flaky locator detection
        st.markdown(
            theme.section(
                "Flaky Locator Detection",
                "Locators that have healed 3+ times. Frequent healing indicates "
                "the locator is unstable and should be refactored.",
            ),
            unsafe_allow_html=True,
        )

        flaky = analytics_data["flaky_locators"]
        if flaky:
            rows = []
            for f in flaky[:10]:
                rows.append({
                    "locator": esc(f["locator"]),
                    "heals": str(f["heal_count"]),
                    "confidence": pct(f["avg_confidence"]),
                    "severity": theme.pill(f["severity"]),
                    "recommendation": esc(f["recommendation"][:80]),
                })
            st.markdown(
                theme.table(
                    rows,
                    [("locator", "Locator"), ("heals", "Heal Count"),
                     ("confidence", "Avg Confidence"), ("severity", "Severity"),
                     ("recommendation", "Recommendation")],
                    aligns={"locator": "mono", "heals": "num", "confidence": "num"},
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                theme.empty("No flaky locators detected (threshold: 3 heals)."),
                unsafe_allow_html=True,
            )

        # Cost analysis details
        st.markdown(
            theme.section(
                "Cost Analysis",
                "Time and cost savings compared to manual fixing. "
                "Assumes 10 minutes per manual locator fix at $50/hour.",
            ),
            unsafe_allow_html=True,
        )

        efficiency = analytics_data["cost_analysis"]["efficiency"]
        comparison = analytics_data["cost_analysis"]["comparison"]

        st.markdown(
            theme.stat_row([
                ("Avg heal time", f"{efficiency['avg_heal_time_ms']}ms"),
                ("Heals/hour", f"{efficiency['heals_per_hour']:.0f}"),
                ("Manual fixes/hour", str(efficiency["manual_fixes_per_hour"])),
            ]),
            unsafe_allow_html=True,
        )

        st.markdown(
            theme.table(
                [
                    {"method": "Self-Healing", "time_per_fix": f"{comparison['self_healing']['time_per_fix_ms']}ms",
                     "requires_human": "No", "scales": "Yes"},
                    {"method": "Manual Fix", "time_per_fix": f"{comparison['manual']['time_per_fix_minutes']}min",
                     "requires_human": "Yes", "scales": "No"},
                ],
                [("method", "Method"), ("time_per_fix", "Time per Fix"),
                 ("requires_human", "Requires Human"), ("scales", "Scales Linearly")],
            ),
            unsafe_allow_html=True,
        )

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
with tab_config:
    st.markdown(
        theme.section(
            "System Configuration",
            "Configure the self-healing system without editing code. Changes are "
            "saved to data/config_override.json and applied to all future healing "
            "operations.",
        ),
        unsafe_allow_html=True,
    )

    current_config = config_manager.get_config()

    # ------------------------------------------------------------------
    # Target application
    #
    # Which application the engine heals is decided by the registry
    # (data/apps/), so this section reads and writes that. It used to offer a
    # standalone target URL, port and HTML file: those drove the retired
    # http.server demo and had no effect on selfheal.run(app=...), which is
    # worse than not offering them at all.
    # ------------------------------------------------------------------
    st.markdown(
        theme.section(
            "Target application",
            "The application every heal is scored against. Register one with "
            "python cli.py register --app <id> --url <url>; the active app "
            "decides which Golden Fingerprint baseline the engine reads and writes.",
        ),
        unsafe_allow_html=True,
    )

    active_record = app_registry.active_app()
    active_id = active_record["app_id"] if active_record else None
    cfg_app_id = None

    if not apps:
        st.markdown(
            theme.empty("No applications registered. Run: "
                        "python cli.py register --app <id> --url <url>"),
            unsafe_allow_html=True,
        )
    else:
        app_ids = [a["app_id"] for a in apps]
        cfg_app_id = st.selectbox(
            "Application",
            app_ids,
            index=app_ids.index(active_id) if active_id in app_ids else 0,
            key="cfg_app",
            help="Registered under data/apps/. Independent of the sidebar scope, "
                 "which only filters what the other tabs display.",
        )
        record = app_registry.load(cfg_app_id) or {}
        fingerprints = load_json_file(record.get("fingerprint_path", ""), dict)
        is_active = cfg_app_id == active_id

        st.markdown(
            theme.table(
                [
                    {"k": "Name", "v": esc(record.get("app_name") or "—")},
                    {"k": "URL / file", "v": esc(record.get("base_url") or "—")},
                    {"k": "Source file", "v": esc(record.get("source_path") or "— (not tracked)")},
                    {"k": "Baseline", "v": (
                        f"{len(fingerprints)} element(s), recorded "
                        f"{esc(clock(record.get('baseline_recorded_at')) or 'never')}"
                        if fingerprints else "not yet recorded")},
                    {"k": "Fingerprint file", "v": esc(
                        os.path.basename(record.get("fingerprint_path", "")) or "—")},
                    {"k": "State", "v": theme.pill("active") if is_active
                                        else theme.pill("warning")},
                ],
                [("k", "Setting"), ("v", "Value")],
                aligns={"v": "mono"},
            ),
            unsafe_allow_html=True,
        )

        if not is_active:
            st.warning(
                f"'{cfg_app_id}' is registered but not active — the engine is "
                f"currently pointed at '{active_id or 'nothing'}'. Activate it "
                f"below, or just run a test with selfheal.run(app=\"{cfg_app_id}\"), "
                f"which activates it automatically."
            )

        col_a1, col_a2, col_a3 = st.columns(3)

        with col_a1:
            if st.button("Set as active app", width="stretch",
                         disabled=is_active):
                if app_registry.activate(cfg_app_id):
                    config_manager.sync_active_app()
                    st.success(f"'{cfg_app_id}' is now the active application")
                    st.rerun()
                else:
                    st.error(f"Could not activate '{cfg_app_id}'")

        with col_a2:
            if st.button("Re-learn baseline", width="stretch",
                         help="Rescans the live page and rebuilds this app's "
                              "baseline from scratch. Only ever do this against a "
                              "known-good build."):
                _cli(["learn", "--app", cfg_app_id, "--force"],
                     "Rescanning the page and rebuilding the baseline...", timeout=180)

        with col_a3:
            if st.button("Run change-impact check", width="stretch",
                         help="Compares the live page against the baseline without "
                              "running the suite. Fills the Change impact tab."):
                _cli(["check", "--app", cfg_app_id],
                     "Comparing the live page against the baseline...", timeout=180)

    # ------------------------------------------------------------------
    # Quick actions
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown(
        theme.section(
            "Quick actions",
            "Populate or clear the dashboard without leaving it. Each button runs "
            "the same script the demo guide runs from the terminal.",
        ),
        unsafe_allow_html=True,
    )

    col_q1, col_q2 = st.columns(2)

    with col_q1:
        if st.button("Simulate infrastructure stress", width="stretch",
                     help="Writes synthetic metric snapshots and runs the real "
                          "infrastructure healer over them. Fills the "
                          "Infrastructure tab."):
            _script("simulate_infra_heal.py", ["combined", "--no-restart"],
                    "Simulating disk, error-rate and service-health stress...",
                    timeout=60)

    with col_q2:
        if st.button("Reset all data", width="stretch",
                     help="Clears every bucket, run, test, app and baseline. "
                          "Your HTML and test scripts are untouched."):
            _script("reset_all.py", [], "Clearing telemetry, runs and baselines...",
                    timeout=30)

    st.markdown("---")

    # ------------------------------------------------------------------
    # Run tests
    #
    # The candidates come from the test registry, which records the script
    # behind every test that has actually run, plus any source-heal targets you
    # added by hand. The previous version listed only the latter and injected
    # MY_APP_URL / MY_APP_HTML, which no test script has ever read -- a test
    # gets its URL from the app it names in selfheal.run(app=...).
    # ------------------------------------------------------------------
    st.markdown(
        theme.section(
            "Run tests",
            "Execute a registered test script. It heals exactly as it would from "
            "the terminal — the dashboard adds nothing to the run.",
        ),
        unsafe_allow_html=True,
    )

    test_options = {}
    for record in test_registry.list_tests(cfg_app_id) if cfg_app_id else []:
        script_path = record.get("script")
        if script_path and os.path.exists(script_path):
            test_options[f"{record['test_id']}  ({os.path.basename(script_path)})"] = script_path
    for target in current_config["source_heal_targets"]:
        if os.path.exists(target) and target not in test_options.values():
            test_options[f"{os.path.basename(target)}  (source-heal target)"] = target

    if not test_options:
        st.markdown(
            theme.empty("No runnable test script known for this application. A test "
                        "registers itself the first time it runs from the terminal."),
            unsafe_allow_html=True,
        )
    else:
        chosen = st.selectbox("Test script", list(test_options.keys()), key="run_test_select")
        if st.button("Run test", width="stretch", type="primary"):
            path = test_options[chosen]
            _script(os.path.relpath(path, config.BASE_DIR), [],
                    f"Running {os.path.basename(path)}...", timeout=180)

    st.markdown("---")

    # Source Healing Toggle
    st.markdown(
        theme.section(
            "Source Code Healing",
            "When enabled, healed locators are written back to test source files, making fixes permanent.",
        ),
        unsafe_allow_html=True,
    )

    source_heal_enabled = st.toggle(
        "Enable source code healing",
        value=current_config["source_heal_enabled"],
        help="When enabled, the system will patch test files with healed locators",
    )

    if source_heal_enabled != current_config["source_heal_enabled"]:
        config_manager.set_source_heal_enabled(source_heal_enabled)
        st.success(f"Source healing {'enabled' if source_heal_enabled else 'disabled'}")

    # Approval Mode Toggle
    st.markdown(
        theme.section(
            "Approval Mode",
            "When enabled, healed locators are queued for human review instead of auto-applying. "
            "This is the industry best practice for safe script updates (Testim, Mabl, Healenium pattern).",
        ),
        unsafe_allow_html=True,
    )

    approval_mode_enabled = st.toggle(
        "Enable approval mode",
        value=current_config["approval_mode_enabled"],
        help="When enabled, script updates require explicit approval in the Approval Queue tab",
    )

    if approval_mode_enabled != current_config["approval_mode_enabled"]:
        config_manager.set_approval_mode_enabled(approval_mode_enabled)
        st.success(f"Approval mode {'enabled' if approval_mode_enabled else 'disabled'}")

    # Git Integration Toggle
    st.markdown(
        theme.section(
            "Git Integration",
            "When enabled, approved heals can automatically create git branches and Pull Requests. "
            "This demonstrates DevOps integration and modern CI/CD workflow understanding.",
        ),
        unsafe_allow_html=True,
    )

    git_integration_enabled = st.toggle(
        "Enable git integration",
        value=current_config["git_integration_enabled"],
        help="When enabled, approved heals can create PRs automatically",
    )

    if git_integration_enabled != current_config["git_integration_enabled"]:
        config_manager.set_git_integration_enabled(git_integration_enabled)
        st.success(f"Git integration {'enabled' if git_integration_enabled else 'disabled'}")

    if git_integration_enabled:
        st.info(
            "**Requirements:**\n"
            "- Git repository initialized\n"
            "- Git remote configured (e.g., GitHub)\n"
            "- GitHub CLI (`gh`) installed and authenticated\n\n"
            "**Workflow:**\n"
            "1. Approve a heal with 'Create PR' checkbox\n"
            "2. System creates branch `auto-heal-{heal_id}`\n"
            "3. Commits healed locators\n"
            "4. Pushes to remote\n"
            "5. Creates Pull Request with detailed description"
        )

    # Source Heal Targets
    st.markdown(
        theme.section(
            "Source Heal Target Files",
            "Test files that will be patched when locators are healed. Add your test files here.",
        ),
        unsafe_allow_html=True,
    )

    # Current targets
    current_targets = current_config["source_heal_targets"]
    if current_targets:
        st.markdown("**Current targets:**")
        for target in current_targets:
            col1, col2 = st.columns([4, 1])
            with col1:
                display_name = os.path.basename(target) if os.path.isabs(target) else target
                st.code(f"{display_name}  →  {target}", language="text")
            with col2:
                if st.button("Remove", key=f"remove_{target}"):
                    config_manager.remove_source_heal_target(target)
                    st.rerun()
    else:
        st.info("No target files configured. Add files below.")

    # Add new target
    st.markdown("---")
    st.markdown("**Add target file:**")

    # File scanner - scan for all .py files in demo directory
    if st.button("🔍 Scan for test files", width="stretch"):
        scanned = config_manager.scan_test_files()
        if scanned:
            st.session_state["scanned_files"] = scanned
            st.success(f"Found {len(scanned)} Python file(s)")
        else:
            st.warning("No .py files found in project directory")

    if "scanned_files" in st.session_state:
        scanned = st.session_state["scanned_files"]
        # Filter out already-added targets
        available = [f for f in scanned if os.path.join(config.BASE_DIR, f) not in current_targets]
        
        if available:
            selected_file = st.selectbox(
                "Select a test file",
                options=[""] + available,
                format_func=lambda x: "Choose a file..." if x == "" else x,
                key="select_test_file",
            )
            if selected_file and st.button("➕ Add selected file", width="stretch"):
                full_path = os.path.join(config.BASE_DIR, selected_file)
                if config_manager.add_source_heal_target(full_path):
                    st.success(f"✓ Added: {selected_file}")
                    if "scanned_files" in st.session_state:
                        del st.session_state["scanned_files"]
                    st.rerun()
                else:
                    st.warning("File already in target list")
        else:
            st.info("All discovered test files are already in the target list.")

    # Manual entry
    st.markdown("---")
    manual_path = st.text_input(
        "Or enter file path manually",
        placeholder="test_my_app.py",
        help="Relative to demo directory, or absolute path",
        key="manual_test_path",
    )
    if manual_path and st.button("➕ Add manual path", width="stretch"):
        # Check if it's an absolute path or relative
        if os.path.isabs(manual_path):
            full_path = manual_path
        else:
            full_path = os.path.join(config.BASE_DIR, manual_path)
        
        if os.path.exists(full_path):
            if config_manager.add_source_heal_target(full_path):
                st.success(f"✓ Added: {manual_path}")
                st.rerun()
            else:
                st.warning("File already in target list")
        else:
            st.error(f"File not found: {full_path}")

    # Confidence Thresholds
    st.markdown(
        theme.section(
            "Confidence Thresholds",
            "Control when the system auto-heals, cautions, or halts. Higher thresholds = more conservative.",
        ),
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    
    with col1:
        high_threshold = st.slider(
            "Auto-heal threshold (%)",
            min_value=50,
            max_value=95,
            value=int(current_config["confidence_threshold_high"]),
            help="Heals above this confidence are applied automatically",
        )

    with col2:
        low_threshold = st.slider(
            "Safety gate threshold (%)",
            min_value=5,
            max_value=50,
            value=int(current_config["confidence_threshold_low"]),
            help="Heals below this confidence are rejected (manual intervention required)",
        )

    if (high_threshold != current_config["confidence_threshold_high"] or
        low_threshold != current_config["confidence_threshold_low"]):
        config_manager.set_confidence_thresholds(high_threshold, low_threshold)
        st.success(f"Thresholds updated: auto-heal ≥{high_threshold}%, safety gate <{low_threshold}%")

    # Threshold explanation
    st.markdown(
        f"""
        **Current behavior:**
        - **≥ {high_threshold}%**: Automatic heal (applied immediately)
        - **{low_threshold}%-{high_threshold}%**: Cautious heal (applied but flagged for review)
        - **< {low_threshold}%**: Halt (manual intervention required)
        """
    )

    # Fingerprint File Management
    st.markdown(
        theme.section(
            "Fingerprint profiles",
            "One baseline per application, named after its app id. Which one is "
            "active follows the registry above — a profile is not something you "
            "point the engine at independently of the app it belongs to.",
        ),
        unsafe_allow_html=True,
    )

    active_fp = config_manager.get_active_fingerprint()
    all_fps = config_manager.get_fingerprint_files()
    registered_ids = {a["app_id"] for a in apps}

    if active_fp:
        active_name = os.path.basename(active_fp).replace('_fingerprints.json', '').replace('_fp.json', '')
        st.markdown(f"**Active profile:** `{active_name}`")
        st.code(active_fp, language="text")

    if all_fps:
        st.markdown("**Available profiles:**")
        for fp in all_fps:
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            # A profile file is named <app_id>_fingerprints.json, so the app it
            # belongs to is recoverable. One with no registered app is an orphan
            # left by a deleted registration -- deletable, but not activatable.
            owner = fp['name'] if fp['name'] in registered_ids else None
            with col1:
                name_display = f"**{fp['name']}**" if fp['is_active'] else fp['name']
                if not owner:
                    name_display += "  <small>(orphaned — no registered app)</small>"
                st.markdown(name_display, unsafe_allow_html=True)
            with col2:
                count_text = f"{fp['element_count']} elements" if fp['element_count'] >= 0 else "error"
                st.markdown(f"<small>{count_text}</small>", unsafe_allow_html=True)
            with col3:
                if fp['is_active']:
                    st.markdown(theme.pill("active"))
                elif owner:
                    if st.button("Activate app", key=f"switch_fp_{fp['filename']}",
                                 help=f"Makes '{owner}' the active application"):
                        if app_registry.activate(owner):
                            config_manager.sync_active_app()
                            st.success(f"'{owner}' is now the active application")
                            st.rerun()
                        else:
                            st.error(f"Could not activate '{owner}'")
            with col4:
                if not fp['is_active']:
                    if st.button("Delete", key=f"delete_fp_{fp['filename']}"):
                        if config_manager.delete_fingerprint_file(fp['path']):
                            st.success(f"Deleted {fp['name']}")
                            st.rerun()
                        else:
                            st.error("Cannot delete active profile")

        if st.button("Show preview of active profile"):
            preview = config_manager.get_fingerprint_preview(active_fp, max_elements=10)
            if preview:
                st.markdown(f"**Total elements:** {preview['total_elements']}")
                if preview['elements']:
                    rows = [{
                        "key": esc(e['key']),
                        "tag": esc(e['tag']),
                        "text": esc(e['text']),
                        "locator": esc(f"{e['locator_by']}='{e['locator_value']}'"),
                    } for e in preview['elements']]
                    st.markdown(
                        theme.table(
                            rows,
                            [("key", "Element Key"), ("tag", "Tag"),
                             ("text", "Visible Text"), ("locator", "Locator")],
                            aligns={"key": "mono", "locator": "mono"},
                        ),
                        unsafe_allow_html=True,
                    )
            else:
                st.warning("Could not load fingerprint preview")
    else:
        st.info("No baselines recorded yet. Register an app, then run its test "
                "once against a working page — a passing run records the baseline.")

    # A profile is created by registering an app, not on its own: an empty file
    # with no app behind it is an orphan the engine can never activate.
    st.markdown(
        "<small>New profiles are created by registering an application — "
        "<code>python cli.py register --app &lt;id&gt; --url &lt;url&gt;</code> — and "
        "populated by the first passing run, or by "
        "<code>python cli.py learn --app &lt;id&gt;</code>.</small>",
        unsafe_allow_html=True,
    )

    # Reset to defaults
    st.markdown("---")
    st.markdown(
        theme.section(
            "Reset Configuration",
            "Restore all settings to their original defaults. This removes all custom overrides.",
        ),
        unsafe_allow_html=True,
    )

    col_reset1, col_reset2 = st.columns([1, 3])
    with col_reset1:
        if st.button("Reset to Defaults", type="secondary", width="stretch"):
            config_manager.reset_to_defaults()
            config_manager.apply_overrides()
            st.success("Configuration restored to defaults")
            st.rerun()
    with col_reset2:
        st.markdown(
            "<small>Removes <code>data/config_override.json</code> and restores "
            "all settings to their built-in defaults. Requires page refresh.</small>",
            unsafe_allow_html=True,
        )

# A command's output has to survive long enough to be read. The 3s auto-refresh
# below would otherwise wipe it before the page finished painting, which made
# the Quick action buttons look like they had done nothing. Freeze this cycle
# instead; the next widget interaction resumes normal refreshing.
if st.session_state.pop("cmd_output_pending", False):
    st.caption("Auto-refresh paused so the output above stays readable. "
               "Press R, or use any control, to resume.")
    st.stop()

# Auto-refresh last, so the whole page paints before we pause.
if os.environ.get("DASH_NO_REFRESH") != "1":
    time.sleep(3)
    st.rerun()
