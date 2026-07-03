---
name: run-demo
description: "Use when launching, running, or resetting the self-healing demo. Provides the exact terminal commands to start all three components (dashboard, target app, Selenium test), explains what each does, and covers common startup errors."
argument-hint: "Specify what to run: full demo, dashboard only, target app only, reset, or infrastructure simulation"
---

# Run Self-Healing Demo

## When to Use
- Starting the demo for the first time
- Restarting after a reset or crash
- Running individual components independently
- Running the infrastructure healing simulation
- Resetting all demo state back to the original

## Architecture Overview

The demo requires **3 components running simultaneously** in separate terminals:

| Component | Script | Port | Purpose |
|-----------|--------|------|---------|
| Dashboard | `dashboard.py` | 8501 | Streamlit monitoring UI |
| Target App | `demo_target_app.py` | 8000 | Pomodoro app (the app under test) |
| Selenium Test | `run_selenium_heal.py` | — | Triggers healing by using broken locators |

The **Collector Server** (`collector_server.py`) is embedded in the target app — no separate launch needed.

## Full Demo Launch

Open **3 separate terminals** in the `demo/` folder:

**Terminal 1 — Dashboard:**
```bash
cd demo
python -m streamlit run dashboard.py
```
Open `http://localhost:8501` in your browser.

**Terminal 2 — Target App:**
```bash
cd demo
python demo_target_app.py
```
Verify: `http://localhost:8000` shows the Pomodoro app.

**Terminal 3 — Run the Heal:**
```bash
cd demo
python run_selenium_heal.py
```
Expected output sequence:
1. `⚠️ Element Missing: [id='old-start-btn']`
2. `🔬 Scanned N candidates`
3. `✨ Auto-Heal 100%: healed to [id='start-btn']`
4. `📝 Source healed: run_selenium_heal.py 'old-start-btn' → 'start-btn'`

Then re-run Terminal 3 — the locator is now fixed, no heal needed.

## Narrated Step-by-Step Demo

For a guided walkthrough with printed explanations:
```bash
cd demo
python demo_show.py
```

## Infrastructure Healing Simulation

Simulates high disk usage and error rate to trigger infrastructure heals:
```bash
cd demo
python simulate_infra_heal.py
```
Watch Dashboard Tab 3 for infrastructure heal actions.

## Reset Demo to Original State

Restores all `.bak` source files and clears heal state:
```bash
cd demo
python demo_show.py --reset
```
Or manually:
```bash
# Clear heal state
echo [] > demo/data/heal_state.json

# Clear telemetry buckets
echo [] > demo/data/buckets/ui_heals.json
echo [] > demo/data/buckets/source_heals.json
echo [] > demo/data/buckets/alerts.json
echo [] > demo/data/buckets/infrastructure.json
echo [] > demo/data/buckets/browser_events.json
```

## Verify Learning Mode

Delete the fingerprint file and re-run to watch Learning Mode auto-rebuild the baseline:
```bash
del demo\data\pomodoro_3d_fingerprints.json
python run_selenium_heal.py
# System enters Learning Mode, scans all elements, saves fingerprints
```

## Common Startup Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Address already in use :8000` | Target app already running | Kill the existing process or use a different port in `config.py` |
| `ChromeDriver not found` | webdriver-manager cache issue | Run `pip install --upgrade webdriver-manager` |
| `Streamlit: module not found` | Missing dependency | Run `pip install -r requirements.txt` |
| `FileNotFoundError: heal_state.json` | Data dir missing | Create `demo/data/` and add empty `{}` file |
| `KeyError: 'pomodoro_3d_fingerprints'` | Fingerprint file empty or missing | Delete the file and re-run to trigger Learning Mode |

## Ports & Configuration

All ports and thresholds are in `demo/config.py`:
- `TARGET_APP_PORT = 8000`
- `DASHBOARD_PORT = 8501`
- `CONFIDENCE_THRESHOLD_HIGH = 0.75`
- `CONFIDENCE_THRESHOLD_LOW = 0.20`
