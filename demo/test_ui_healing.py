import random
from datetime import datetime, timezone
import time
import config
import store

# List of realistic frontend DOM mutations to pick from dynamically
ui_mutation_scenarios = [
   {
        "broken_selector": "#old-start-button",
        "recovered_selector": "button.btn.btn-primary.btn-start",
        "confidence_score": 100.0,
        "strategy": "EXACT_TEXT_MATCH",
        "status": "success"
    },
    {
        "broken_selector": "div.timer-display > span",
        "recovered_selector": "div#digital-clock-v2",
        "confidence_score": 88.4,
        "strategy": "FUZZY_DOM_PROXIMITY",
        "status": "success"
    },
    {
        "broken_selector": "#submit-feedback-btn",
        "recovered_selector": "button[type='submit']",
        "confidence_score": 64.5,
        "strategy": "FALLBACK_TAG_SCAN",
        "status": "warning"
    },
    {
        "broken_selector": "//button[text()='Submit']",
        "recovered_selector": "//button[@id='save-data']",
        "confidence_score": 78.0,
        "strategy": "NEIGHBORING_ANCHOR_LOOKUP",
        "status": "success"
    },
    # 🚨 NEW LOW SCORE EDGE CASE 1: Flagged Warning
    {
        "broken_selector": "div.modal-body",
        "recovered_selector": "div.card-wrapper",
        "confidence_score": 59.8,
        "strategy": "FALLBACK_TAG_SCAN",
        "status": "warning"
    },
    # 🚨 NEW LOW SCORE EDGE CASE 2: Critical Drop / Failure
    {
        "broken_selector": "#checkout-pay-btn",
        "recovered_selector": "a.btn-cancel",
        "confidence_score": 42.1,
        "strategy": "PARENT_LEAF_TRAVERSAL",
        "status": "warning" 
    }
]

print("🔍 Initializing Self-Healing Web Driver...")
time.sleep(1)

# Pick a random scenario so the demo changes every time!
selected_scenario = random.choice(ui_mutation_scenarios)

print(f"💥 Native Selenium Error: NoSuchElementException for locator '{selected_scenario['broken_selector']}'")
print("🧠 Activating Rule-Based Heuristic Healing Engine...")
time.sleep(1.5)
print(f"🎯 Candidate found! Re-routing click path to: '{selected_scenario['recovered_selector']}'")
print(f"📊 Evaluated Confidence Matrix Score: {selected_scenario['confidence_score']}%")

# Create log payload
# Create log payload mapping 'strategy' safely to 'policy'
new_ui_heal = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "broken_selector": selected_scenario["broken_selector"],
    "recovered_selector": selected_scenario["recovered_selector"],
    "confidence_score": selected_scenario["confidence_score"],
    "policy": selected_scenario["strategy"],  # 🟢 Maps the string value perfectly
    "status": selected_scenario["status"]
}

# Persist via the atomic, per-bucket store (cross-process safe + rolling window)
store.append("ui_heals", new_ui_heal)

print("📡 Telemetry pushed successfully. Watch your dashboard update!")