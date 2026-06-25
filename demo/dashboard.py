import streamlit as tf
import json
import pandas as pd
import os
import plotly.express as px  # 🌟 Added for clean chart presentation bounds
from datetime import datetime
import config
import store
import time

# Page viewport window settings
tf.set_page_config(page_title="Self-Healing Monitoring Terminal", layout="wide")
tf.title("🛡️ Rule-Based Automated Self-Healing Control Panel")
tf.caption(
    "Active path = synchronous UI heal (Selenium blocks for a decision)  ·  "
    "Passive path = fire-and-forget telemetry (browser agent + infra metrics)"
)

def load_json_file(file_path, default_factory):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception:
            return default_factory()
    return default_factory()

# Ingest active datastores: per-bucket store for logs, file load for metrics history
logs = store.read_all()
history = load_json_file(config.METRICS_HISTORY_PATH, list)

# ----------------- SIDEBAR STATUS METRICS -----------------
# ----------------- SIDEBAR STATUS METRICS -----------------
tf.sidebar.header("📡 Live Infrastructure Pulse")
if history:
    latest = history[-1]
    
    status_color = "🟢 HEALTHY" if latest.get("service_health") == "Up" else "🔴 DOWN"
    tf.sidebar.markdown(f"**Target Application Status:** {status_color}")
    
    tf.sidebar.metric("Traffic Frequency Rate", f"{latest.get('traffic_rate', 0)} req/s")
    tf.sidebar.metric("Active Threads Pool", f"{latest.get('active_requests', 0)}")
    tf.sidebar.metric("Error Rate Percent", f"{latest.get('error_rate_percent', 0.0)}%")
    tf.sidebar.metric("Server Disk Capacity", f"{latest.get('disk_usage_percent', 0.0)}%")
else:
    tf.sidebar.warning("No time-series operational history data detected.")

# ----------------- CORE TABS MONITOR -----------------
tab_ui, tab_source, tab_infra, tab_alerts = tf.tabs(["🔗 UI Heuristic Healing", "📝 Locator Self-Correction", "⚙️ Server Infrastructure Heals", "🚨 Alert Notification Logs"])

with tab_ui:
    tf.subheader("Dynamic Web Element Recovery Track Logs")
    ui_records = logs.get("ui_heals", [])
    
    if ui_records:
        df_ui = pd.DataFrame(ui_records)

        # Flatten R1-R4 heuristic component scores (proposal Table 3.1) into columns.
        comp = df_ui.get("details")
        if comp is not None:
            scores = df_ui["details"].apply(
                lambda d: (d or {}).get("component_scores", {}) if isinstance(d, dict) else {}
            )
            for col in ["R1_text_40", "R2_xpath_30", "R3_css_20", "R4_neighbors_10"]:
                df_ui[col] = scores.apply(lambda s: s.get(col))

        # Aggregate KPI counters
        kpi_total = len(df_ui)
        kpi_success = len(df_ui[df_ui["status"] == "success"])
        kpi_warn = len(df_ui[df_ui["status"] == "warning"])

        # Failed heals come from the alerts bucket (UIHeuristicEngine source).
        ui_failed = len([
            a for a in logs.get("alerts", [])
            if a.get("source") == "UIHeuristicEngine"
        ])
        attempts = kpi_success + kpi_warn          # heals that rerouted
        interruptions = attempts + ui_failed       # all locator failures
        healing_rate = (attempts / interruptions * 100) if interruptions else 0.0
        success_rate = (kpi_success / attempts * 100) if attempts else 0.0

        col1, col2, col3, col4 = tf.columns(4)
        col1.metric("Total UI Interruptions", interruptions)
        col2.metric("Automatic Heals (≥75%)", kpi_success)
        col3.metric("Healing Rate", f"{healing_rate:.0f}%")
        col4.metric("Success Rate", f"{success_rate:.0f}%")

        # Clean data frame preview display columns (incl. healed locator + R1-R4)
        display_cols = ["timestamp", "broken_selector", "recovered_selector", "healed_locator",
                        "confidence_score", "R1_text_40", "R2_xpath_30", "R3_css_20", "R4_neighbors_10",
                        "policy", "status"]
        # reindex (not subscript) so heal entries from mixed sources missing a key render blank instead of KeyError
        tf.dataframe(df_ui.reindex(columns=display_cols).sort_values(by="timestamp", ascending=False), use_container_width=True)
        
        # ----------------- FIX: ADVANCED PLOTLY AXIS POLISHING -----------------
        tf.markdown("### Confidence Distribution Profile Analysis")
        
        # Format timestamps into clean categories to separate adjacent historical run spikes
        df_chart = df_ui.copy()
        df_chart["clean_time"] = pd.to_datetime(df_chart["timestamp"], format='ISO8601').dt.strftime('%m/%d %H:%M:%S')
        fig = px.bar(
            df_chart, 
            x="clean_time", 
            y="confidence_score", 
            color="status",
            labels={"clean_time": "Execution Timestamp Log", "confidence_score": "Confidence Score (%)"},
            color_discrete_map={"success": "#2e7d32", "failed": "#c62828", "warning": "#ef6c00"},
            template="plotly_dark"
        )
        
        # Lock vertical grid lines between 0% and 100% exactly
        fig.update_layout(
            yaxis=dict(range=[0, 100], ticksuffix="%", dtick=25),
            xaxis=dict(type='category'),
            barmode='group',
            margin=dict(l=40, r=40, t=10, b=40),
            height=350
        )
        
        tf.plotly_chart(fig, use_container_width=True)
    else:
        tf.info("No interactive UI automation element failures intercepted yet.")

with tab_source:
    tf.subheader("Persistent Source-Code Write-Back Logs")
    tf.caption("Healed locators written back into test/automation source — broken selector fixed once, stays fixed.")
    source_records = logs.get("source_heals", [])

    if source_records:
        df_src = pd.DataFrame(source_records)
        col1, col2 = tf.columns(2)
        col1.metric("Total Source Patches", len(df_src))
        col2.metric("Files Auto-Fixed", df_src["file"].nunique())

        display_cols = ["timestamp", "file", "broken_token", "healed_token", "occurrences", "status"]
        tf.dataframe(
            df_src.reindex(columns=display_cols).sort_values(by="timestamp", ascending=False),
            use_container_width=True,
        )
    else:
        tf.info("No source-code write-backs yet. Run a high-confidence Selenium heal to trigger one.")

with tab_infra:
    tf.subheader("Infrastructure Stress Resolution Logs")
    infra_records = logs.get("infrastructure", [])
    
    if infra_records:
        df_infra = pd.DataFrame(infra_records)
        tf.dataframe(df_infra.sort_values(by="timestamp", ascending=False), use_container_width=True)
    else:
        tf.info("No server container system crashes or resource exhaustion anomalies encountered.")

with tab_alerts:
    tf.subheader("Active System Alerts Store")
    alert_records = logs.get("alerts", [])
    
    if alert_records:
        for idx, alert in enumerate(reversed(alert_records)):
            severity = alert.get("severity", "warning").upper()
            box_type = tf.error if severity == "CRITICAL" else tf.warning
            box_type(f"**[{alert.get('timestamp')}] {alert.get('source')} - {severity}**\n\n{alert.get('message')}")
    else:
        tf.success("System clean. Zero active warning signals generated.")

# ----------------- 🔄 REAL-TIME AUTO-REFRESH -----------------
# Placed at the very bottom so the whole layout prints out before pausing.
# Set DASH_NO_REFRESH=1 to freeze the page (used for QA screenshots / tab capture).
if os.environ.get("DASH_NO_REFRESH") != "1":
    time.sleep(3)
    tf.rerun()