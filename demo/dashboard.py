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
            with open(path, "r") as f:
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
                                     mime="text/markdown", use_container_width=True)
                col2.download_button("Heals (CSV)", reports.to_csv(record),
                                     file_name=f"{selected_run_id}.csv",
                                     mime="text/csv", use_container_width=True)
                col3.download_button("Raw run (JSON)", reports.to_json(record),
                                     file_name=f"{selected_run_id}.json",
                                     mime="application/json", use_container_width=True)

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
        successes = len(df[df["status"] == "success"])
        warnings = len(df[df["status"] == "warning"])
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
        st.plotly_chart(figure, use_container_width=True,
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
                    st.markdown(
                        f"- R1 (Text): {metrics.get('R1_text_40', 0):.0f}%\n"
                        f"- R2 (XPath): {metrics.get('R2_xpath_30', 0):.0f}%\n"
                        f"- R3 (CSS): {metrics.get('R3_css_20', 0):.0f}%\n"
                        f"- R4 (Neighbors): {metrics.get('R4_neighbors_10', 0):.0f}%"
                    )
                    
                    st.markdown("**Diff:**")
                    st.code(heal.get('diff', 'No diff available'), language='diff')
                
                with col2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    if st.button("✅ Approve", key=f"approve_{heal['heal_id']}", use_container_width=True):
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
                    
                    if st.button("❌ Reject", key=f"reject_{heal['heal_id']}", use_container_width=True):
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
            successful_heals = len([h for h in ui_heals if h.get("status") == "success"])
            cautious_heals = len([h for h in ui_heals if h.get("status") == "warning"])
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
                st.plotly_chart(fig, use_container_width=True)
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
            "Configure the self-healing system without editing code. Changes are saved to "
            "<code>data/config_override.json</code> and applied to all future healing operations.",
        ),
        unsafe_allow_html=True,
    )

    current_config = config_manager.get_config()

    # ------------------------------------------------------------------
    # Target Application Configuration
    # ------------------------------------------------------------------
    st.markdown(
        theme.section(
            "Target Application",
            "Point the healing system at any HTML file or web application. "
            "Configure the URL, HTML file, and fingerprint profile here.",
        ),
        unsafe_allow_html=True,
    )

    col_url, col_port = st.columns([3, 1])

    with col_port:
        target_port = st.number_input(
            "Port",
            min_value=1024,
            max_value=65535,
            value=int(current_config.get("target_app_port", 8000)),
            step=1,
            key="cfg_target_port",
        )
        if target_port != current_config.get("target_app_port", 8000):
            config_manager.set_target_app_port(target_port)
            st.success(f"Port set to {target_port}")

    with col_url:
        current_url = current_config.get("target_url", f"http://127.0.0.1:{current_config.get('target_app_port', 8000)}")
        target_url = st.text_input(
            "Target URL",
            value=current_url,
            key="cfg_target_url",
            help="Full URL to the application under test",
        )
        if target_url != current_url:
            config_manager.set_target_url(target_url)
            st.success(f"Target URL set to {target_url}")

    col_html, col_fp = st.columns(2)

    with col_html:
        current_html = current_config.get("target_html_file", "")
        target_html = st.text_input(
            "HTML File (optional)",
            value=current_html,
            key="cfg_target_html",
            placeholder="e.g., web.html, my_app/index.html",
            help="Path to the HTML file relative to the demo directory",
        )
        if target_html != current_html:
            config_manager.set_target_html_file(target_html)
            st.success(f"HTML file set to {target_html}")

    with col_fp:
        active_fp = config_manager.get_active_fingerprint()
        fp_display = os.path.basename(active_fp) if active_fp else "None"
        st.markdown(
            f"**Active Fingerprint:** `{fp_display}`<br>"
            f"<small>Switch profiles in Fingerprint Profiles section below.</small>",
            unsafe_allow_html=True,
        )

    # Scan & Learn button
    st.markdown("---")
    col_btn1, col_btn2 = st.columns([2, 3])

    with col_btn1:
        if st.button("Serve HTML File & Learn", use_container_width=True):
            if not target_html:
                st.warning("Enter an HTML file name first (e.g., web.html)")
            else:
                html_path = os.path.join(config.BASE_DIR, target_html)
                if not os.path.exists(html_path):
                    st.error(f"File not found: {html_path}")
                else:
                    with st.spinner("Starting server and learning fingerprints..."):
                        try:
                            import subprocess
                            import time

                            # Start HTTP server in background
                            proc = subprocess.Popen(
                                [sys.executable, "-m", "http.server", str(target_port)],
                                cwd=config.BASE_DIR,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            time.sleep(2)  # Wait for server to start

                            from selenium import webdriver
                            from selenium.webdriver.chrome.service import Service
                            from webdriver_manager.chrome import ChromeDriverManager
                            import glob
                            import learning_mode
                            import automation_wrapper

                            # Find ChromeDriver
                            driver_paths = glob.glob(os.path.expanduser(
                                "~/.wdm/drivers/chromedriver/*/*/chromedriver-win64/chromedriver.exe"
                            ))
                            if driver_paths:
                                driver_path = driver_paths[-1]
                            else:
                                driver_path = ChromeDriverManager().install()

                            options = webdriver.ChromeOptions()
                            options.add_argument("--headless=new")
                            options.add_argument("--no-sandbox")
                            options.add_argument("--disable-dev-shm-usage")
                            driver = webdriver.Chrome(service=Service(driver_path), options=options)

                            try:
                                learn_url = f"http://127.0.0.1:{target_port}/{target_html}"
                                driver.get(learn_url)
                                with automation_wrapper.suppressed():
                                    count = learning_mode.ensure_fingerprints(driver, active_fp, force=True)
                                st.success(f"✓ Captured {count} fingerprints from {target_html}")
                            finally:
                                driver.quit()
                                proc.terminate()
                                proc.wait()
                        except Exception as e:
                            st.error(f"Failed to learn fingerprints: {e}")
                            import traceback
                            st.code(traceback.format_exc())

    with col_btn2:
        st.markdown(
            "<small>Starts a local server, opens the HTML file in Chrome, "
            "and captures Golden Fingerprints for all interactive elements.</small>",
            unsafe_allow_html=True,
        )

    # Quick action buttons
    st.markdown("---")
    st.markdown(
        theme.section(
            "Quick Actions",
            "Run the full demo or simulate infrastructure stress to populate all dashboard tabs.",
        ),
        unsafe_allow_html=True,
    )

    col_q1, col_q2, col_q3 = st.columns(3)

    with col_q1:
        if st.button("Run Full Demo", type="primary", use_container_width=True):
            with st.spinner("Running full demo (learning + healing)..."):
                try:
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, os.path.join(config.BASE_DIR, "demo.py")],
                        cwd=config.BASE_DIR,
                        capture_output=True, text=True, timeout=300,
                    )
                    if result.stdout:
                        st.code(result.stdout[-3000:], language="text")
                    if result.returncode == 0:
                        st.success("Demo completed successfully!")
                    else:
                        if result.stderr:
                            st.error(result.stderr[-1000:])
                except subprocess.TimeoutExpired:
                    st.error("Demo timed out after 300 seconds")
                except Exception as e:
                    st.error(f"Demo failed: {e}")

    with col_q2:
        if st.button("Simulate Infra Stress", use_container_width=True):
            with st.spinner("Simulating infrastructure stress conditions..."):
                try:
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, os.path.join(config.BASE_DIR, "simulate_infra_heal.py"), "all"],
                        cwd=config.BASE_DIR,
                        capture_output=True, text=True, timeout=30,
                    )
                    if result.stdout:
                        st.code(result.stdout, language="text")
                    st.success("Infrastructure stress simulated! Check Infrastructure tab.")
                except Exception as e:
                    st.error(f"Failed: {e}")

    with col_q3:
        if st.button("Reset All Data", use_container_width=True):
            with st.spinner("Resetting all data..."):
                try:
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, os.path.join(config.BASE_DIR, "reset_demo.py")],
                        cwd=config.BASE_DIR,
                        capture_output=True, text=True, timeout=10,
                    )
                    st.success("All data reset. Dashboard will refresh empty.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Reset failed: {e}")

    # Current target summary
    st.markdown("---")
    summary_items = []
    if target_url:
        summary_items.append(f"URL: **{target_url}**")
    if target_html:
        summary_items.append(f"HTML: **{target_html}**")
    summary_items.append(f"Port: **{target_port}**")
    summary_items.append(f"Fingerprint: **{fp_display}**")
    st.markdown(" | ".join(summary_items))
    st.markdown("---")

    # Run Tests Section
    st.markdown(
        theme.section(
            "Run Tests",
            "Execute your test scripts directly from the dashboard. The system will auto-heal broken locators.",
        ),
        unsafe_allow_html=True,
    )

    current_targets = current_config["source_heal_targets"]
    if not current_targets:
        st.warning("No test scripts configured. Add test files in 'Source Heal Target Files' section below.")
    else:
        test_options = {os.path.basename(t): t for t in current_targets}
        selected_test = st.selectbox(
            "Select test script to run",
            options=list(test_options.keys()),
            key="run_test_select",
        )

        if st.button("Run Test", use_container_width=True, type="primary"):
            if selected_test:
                test_path = test_options[selected_test]
                with st.spinner(f"Running {selected_test}..."):
                    try:
                        import subprocess
                        env = os.environ.copy()
                        env["MY_APP_URL"] = target_url or f"http://127.0.0.1:{target_port}"
                        if target_html:
                            env["MY_APP_HTML"] = target_html

                        result = subprocess.run(
                            [sys.executable, test_path],
                            cwd=config.BASE_DIR,
                            env=env,
                            capture_output=True,
                            text=True,
                            timeout=120,
                        )

                        st.markdown("**Test Output:**")
                        if result.stdout:
                            st.code(result.stdout, language="text")
                        if result.stderr:
                            st.error(result.stderr)

                        if result.returncode == 0:
                            st.success("Test completed successfully!")
                        else:
                            st.error(f"Test failed with exit code {result.returncode}")

                    except subprocess.TimeoutExpired:
                        st.error("Test timed out after 120 seconds")
                    except Exception as e:
                        st.error(f"Failed to run test: {e}")
                        import traceback
                        st.code(traceback.format_exc())

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
    if st.button("🔍 Scan for test files", use_container_width=True):
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
            if selected_file and st.button("➕ Add selected file", use_container_width=True):
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
    if manual_path and st.button("➕ Add manual path", use_container_width=True):
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
            "Fingerprint Profiles",
            "Each application gets its own fingerprint baseline. Switch between apps, "
            "create new profiles, or delete unused ones. The active profile is used for "
            "all healing operations.",
        ),
        unsafe_allow_html=True,
    )

    active_fp = config_manager.get_active_fingerprint()
    all_fps = config_manager.get_fingerprint_files()

    if active_fp:
        active_name = os.path.basename(active_fp).replace('_fingerprints.json', '').replace('_fp.json', '')
        st.markdown(f"**Active profile:** `{active_name}`")
        st.code(active_fp, language="text")

    if all_fps:
        st.markdown("**Available profiles:**")
        for fp in all_fps:
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                name_display = f"**{fp['name']}**" if fp['is_active'] else fp['name']
                st.markdown(name_display)
            with col2:
                count_text = f"{fp['element_count']} elements" if fp['element_count'] >= 0 else "error"
                st.markdown(f"<small>{count_text}</small>", unsafe_allow_html=True)
            with col3:
                if fp['is_active']:
                    st.markdown(theme.pill("active"))
                else:
                    if st.button("Switch", key=f"switch_fp_{fp['filename']}"):
                        if config_manager.set_active_fingerprint(fp['path']):
                            st.success(f"Switched to {fp['name']}")
                            st.rerun()
                        else:
                            st.error("Failed to switch fingerprint file")
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
        st.info("No fingerprint files found. Create one below or run Learning Mode on an app.")

    # Create new fingerprint file
    st.markdown("**Create new profile for a different app:**")
    new_app_name = st.text_input(
        "App name",
        placeholder="e.g., ecommerce, banking, social_media",
        key="new_fp_name",
    )
    if new_app_name and st.button("Create profile", key="create_fp_btn"):
        new_path = config_manager.create_fingerprint_file(new_app_name)
        if new_path:
            st.success(f"Created profile: {os.path.basename(new_path)}")
            st.info("Run Learning Mode on the app to populate fingerprints.")
            st.rerun()
        else:
            st.error("Failed to create profile. Check the app name.")

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
        if st.button("Reset to Defaults", type="secondary", use_container_width=True):
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

# Auto-refresh last, so the whole page paints before we pause.
if os.environ.get("DASH_NO_REFRESH") != "1":
    time.sleep(3)
    st.rerun()
