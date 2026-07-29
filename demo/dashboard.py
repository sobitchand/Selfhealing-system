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
import time

import pandas as pd
import plotly.express as px
import streamlit as st

import config
import config_manager
import store
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
# Sidebar — live metrics from the target application
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="sb-title">Live metrics</div>', unsafe_allow_html=True)
    if history:
        latest = history[-1]
        st.markdown(
            theme.sidebar_status(latest.get("service_health") == "Up"),
            unsafe_allow_html=True,
        )
        for label, value in [
            ("Traffic", f"{latest.get('traffic_rate', 0)} req/s"),
            ("Active requests", latest.get("active_requests", 0)),
            ("Error rate", f"{latest.get('error_rate_percent', 0.0)}%"),
            ("Disk usage", f"{latest.get('disk_usage_percent', 0.0)}%"),
        ]:
            st.markdown(theme.sidebar_item(label, value), unsafe_allow_html=True)
    else:
        st.markdown(
            '<p class="section-note">No metrics yet. Start the target '
            "application to begin collecting.</p>",
            unsafe_allow_html=True,
        )

tab_ui, tab_source, tab_infra, tab_alerts, tab_analytics, tab_config = st.tabs(
    ["Locator healing", "Source write-back", "Infrastructure", "Alerts", "Analytics", "Configuration"]
)

# --------------------------------------------------------------------------
# Locator healing
# --------------------------------------------------------------------------
with tab_ui:
    records = logs.get("ui_heals", [])
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
            a for a in logs.get("alerts", []) if a.get("source") == "UIHeuristicEngine"
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
            # Four separate score columns pushed the table past the page width
            # and told the reader less than the four numbers side by side.
            breakdown = " · ".join(
                score(components.get(key)) for key in
                ("R1_text_40", "R2_xpath_30", "R3_css_20", "R4_neighbors_10")
            )
            rows.append({
                "time": esc(clock(record.get("timestamp"))),
                "broken": esc(record.get("broken_selector")),
                "recovered": esc(record.get("recovered_selector")),
                "confidence": pct(record.get("confidence_score")),
                "components": breakdown,
                "status": theme.pill(record.get("status")),
            })

        st.markdown(
            theme.table(
                rows,
                [("time", "Time"), ("broken", "Broken locator"),
                 ("recovered", "Recovered element"), ("confidence", "Confidence"),
                 ("components", "R1 · R2 · R3 · R4"), ("status", "Outcome")],
                aligns={"broken": "mono", "confidence": "num", "components": "num"},
            ) + theme.table_note(min(ROW_LIMIT, len(records)), len(records), "heals"),
            unsafe_allow_html=True,
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
    records = logs.get("alerts", [])
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
                st.code(target, language="text")
            with col2:
                if st.button("Remove", key=f"remove_{target}"):
                    config_manager.remove_source_heal_target(target)
                    st.rerun()
    else:
        st.info("No target files configured. Add files below.")

    # Add new target
    st.markdown("**Add target file:**")
    
    # File scanner
    if st.button("Scan for test files"):
        st.session_state["scanned_files"] = config_manager.scan_test_files()

    if "scanned_files" in st.session_state:
        scanned = st.session_state["scanned_files"]
        if scanned:
            selected_file = st.selectbox(
                "Select a test file",
                options=[""] + scanned,
                format_func=lambda x: "Choose a file..." if x == "" else x,
            )
            if selected_file and st.button("Add selected file"):
                full_path = os.path.join(config.BASE_DIR, selected_file)
                if config_manager.add_source_heal_target(full_path):
                    st.success(f"Added: {selected_file}")
                    st.rerun()
                else:
                    st.warning("File already in target list")
        else:
            st.warning("No test files found in project directory")

    # Manual entry
    manual_path = st.text_input(
        "Or enter file path manually",
        placeholder="tests/test_login.py",
    )
    if manual_path and st.button("Add manual path"):
        full_path = os.path.join(config.BASE_DIR, manual_path)
        if config_manager.add_source_heal_target(full_path):
            st.success(f"Added: {manual_path}")
            st.rerun()
        else:
            st.warning("File already in target list")

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

    # Reset to defaults
    st.markdown("---")
    if st.button("Reset to defaults", type="secondary"):
        config_manager.reset_to_defaults()
        st.success("Configuration reset to defaults")
        st.rerun()

# Auto-refresh last, so the whole page paints before we pause.
if os.environ.get("DASH_NO_REFRESH") != "1":
    time.sleep(3)
    st.rerun()
