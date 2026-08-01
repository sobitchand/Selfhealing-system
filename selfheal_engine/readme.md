# Self-Healing Test Automation System

An intelligent test automation framework that automatically heals broken UI locators and restarts failed infrastructure — using heuristic scoring, golden fingerprints, and live metrics monitoring.

## System Status: CLEAN & READY

All junk files removed. Core engine lives in `selfheal_engine/`. Ready for demo and defense.

---

## Quick Start

### 1. Start Dashboard

```powershell
cd selfheal_engine
python -m streamlit run dashboard.py
```

Open http://localhost:8501

### 2. Start Target App & Infra Monitor

From the dashboard sidebar:

1. Click **"Start Target App"** — serves `demo_page.html` on port 8000
2. Click **"Start Infra Monitor"** — polls target health every few seconds

The **Live Metrics** sidebar shows HTTP status, response time, CPU, and memory in real time.

### 3. Capture Fingerprints

In the **Configuration** tab:

1. Set HTML file to `demo_page.html`
2. Click **"Serve HTML File & Learn"** — captures golden fingerprints for all elements
3. Fingerprints saved to `data/fingerprints/baseline_fingerprints.json`

### 4. Run Tests

Click **"Run Test"** in the dashboard, or run manually:

```powershell
cd selfheal_engine
$env:PYTHONIOENCODING="utf-8"
python demo_test.py
```

`demo_test.py` runs 4 test cases using `By.ID`, `By.CSS_SELECTOR`, and `By.XPATH`.

### 5. Break & Heal Demo

1. Edit `demo_page.html` — change an `id`, `class`, or button text
2. Click **"Run Test"** again
3. System detects broken locator → scores candidates → heals → test passes
4. View heal details in dashboard tabs:

| Tab | Shows |
|-----|-------|
| **UI Heuristic Healing** | R1–R4 scores, confidence, reason for repair, QA recommendations |
| **Locator Self-Correction** | Old locator → new locator, patched script, backups |
| **Infrastructure** | Service restarts, log rotation, error counter resets |
| **Alerts** | System alerts and failed heal attempts |
| **Analytics** | Stability scores, cost analysis, heal history |
| **Configuration** | Thresholds, target app, source heal files, approval mode |

### 6. Infrastructure Healing Demo

1. Start target app + infra monitor from dashboard
2. Kill the target app process (or close the terminal running it)
3. Monitor detects `Down` status → triggers `DynamicInfrastructureHealer`
4. Healer kills stale port → relaunches `demo_target_app.py` → verifies response
5. Next poll shows `Up` — heal logged in **Infrastructure** tab

---

## Complete Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  1. START DASHBOARD                                         │
│     streamlit run dashboard.py                              │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  2. START TARGET APP & INFRA MONITOR                        │
│     - demo_target_app.py serves demo_page.html on :8000     │
│     - infra_monitor.py polls health every N seconds         │
│     - Live Metrics sidebar shows status in real time        │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  3. CAPTURE FINGERPRINTS (Learning Mode)                    │
│     - System scans demo_page.html                           │
│     - Captures Golden Fingerprints for all elements         │
│     - Saves to data/fingerprints/baseline_fingerprints.json │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  4. RUN TESTS (Day 1 — baseline passes)                     │
│     - demo_test.py runs 4 test cases                        │
│     - All locators found → all tests pass                   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  5. BREAK HTML (simulate Day 2 changes)                     │
│     - Edit demo_page.html: change id, class, or text        │
│     - Old locators no longer match                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  6. SELF-HEALING INTERCEPTS                                 │
│     - automation_wrapper catches NoSuchElementException     │
│     - healing_engine scores candidates:                     │
│       * R1: Text similarity (40%)                           │
│       * R2: XPath similarity (30%)                          │
│       * R3: CSS similarity (20%)                            │
│       * R4: Neighbor similarity (10%)                       │
│     - Tag mismatch: -25% penalty                            │
│     - Margin check: best vs second-best (10% threshold)     │
│     - Weight normalization when attributes absent           │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  7. HEALING DECISION                                        │
│     - Confidence >= 75%: Auto-heal                          │
│     - 20% <= Confidence < 75%: Caution (needs review)       │
│     - Confidence < 20%: Halt (too uncertain)                │
│     - Three-strike lock: repeated low-confidence heals      │
│       blocked for same locator (feedback.py)                │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  8. SOURCE HEALING (write-back)                             │
│     - source_healer patches demo_test.py                    │
│     - Old locator -> New locator                            │
│     - Backup created in data/backups/                       │
│     - Multi-attribute repaired-locator ranking              │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  9. TEST CONTINUES & PASSES                                 │
│     - Test uses healed locator                              │
│     - Dashboard logs: reason for repair, QA recommendations │
│     - Heal history persisted for analytics                  │
└─────────────────────────────────────────────────────────────┘
```

### Infrastructure Healing Flow

```
┌─────────────────────────────────────────────────────────────┐
│  INFRA MONITOR polls target every N seconds                 │
│  Records: HTTP status, response time, CPU, memory, disk     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  ANOMALY DETECTED                                           │
│  - Service Down (HTTP 0/500) → Service Restart              │
│  - Disk > 85% + Error > 40%  → Log Rotation & Temp Purge    │
│  - Disk > 85% only            → Log Rotation & Temp Purge    │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  HEAL ACTION EXECUTED                                       │
│  - Kill stale process on port                               │
│  - Relaunch demo_target_app.py                              │
│  - Poll until responding (up to 5s)                         │
│  - Log to data/buckets/infrastructure.json                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  RECOVERY VERIFIED                                          │
│  - Next monitor poll shows Up HTTP 200                      │
│  - Dashboard Infrastructure tab shows heal action           │
└─────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
selfheal_engine/
├── .streamlit/              # Streamlit config
├── assets/                  # Dashboard fonts
├── data/
│   ├── backups/             # Test script backups (auto-created)
│   ├── buckets/             # Event logs (heals, alerts, infrastructure, etc.)
│   ├── fingerprints/        # Golden fingerprints
│   │   └── baseline_fingerprints.json
│   ├── config_override.json # Runtime config overrides
│   ├── metrics_history.json # Infra monitor snapshots
│   └── heal_state.json      # Three-strike lock state
├── analytics.py             # Stability & cost analysis
├── approval_workflow.py     # Approve/reject/rollback healed locators
├── automation_wrapper.py    # Exception interception + SelfHealingWebDriver
├── config.py                # Configuration defaults & thresholds
├── config_manager.py        # Config persistence & overrides
├── dashboard.py             # Streamlit dashboard (all tabs)
├── demo_page.html           # Target app HTML (button test page)
├── demo_target_app.py       # Serves demo_page.html via HTTP
├── demo_test.py             # 4 test cases using selfheal.install()
├── dom_features.py          # DOM feature extraction
├── feedback.py              # Three-strike lock logic
├── fingerprint_manager.py   # Fingerprint capture & storage
├── handlers.py              # Event handlers
├── healing_engine.py        # R1–R4 scoring + DynamicInfrastructureHealer
├── infra_monitor.py         # Live metrics polling + heal trigger
├── learning_mode.py         # Fingerprint capture context
├── requirements.txt         # Dependencies
├── selfheal.py              # Zero-touch integration (install/uninstall)
├── source_healer.py         # Test script patching
├── store.py                 # Persistence layer
└── theme.py                 # Dashboard styling
```

---

## Core Modules

| Module | Purpose |
|--------|---------|
| `automation_wrapper.py` | Intercepts `NoSuchElementException` and triggers healing |
| `healing_engine.py` | R1–R4 heuristic scoring + `DynamicInfrastructureHealer` |
| `infra_monitor.py` | Polls target app health, triggers infrastructure healing |
| `learning_mode.py` | Captures golden fingerprints from working HTML |
| `selfheal.py` | Zero-touch integration via `selfheal.install()` |
| `source_healer.py` | Patches test scripts with healed locators |
| `feedback.py` | Three-strike lock for repeated low-confidence heals |
| `approval_workflow.py` | Approve/reject/rollback healed locators |
| `analytics.py` | Stability scores, cost analysis, heal history |
| `config.py` | System configuration (thresholds, targets, paths) |
| `config_manager.py` | Configuration management and persistence |
| `dashboard.py` | Streamlit dashboard for monitoring all activity |
| `fingerprint_manager.py` | Fingerprint storage and retrieval |
| `dom_features.py` | Extracts DOM features for R3 scoring |

---

## Healing Algorithm

### R1: Text Similarity (40% weight)
Compares visible text content, `normalize-space()`, and `inner_text`.

### R2: XPath Similarity (30% weight)
Compares XPath expressions and structural attributes (`@id`, `@class`, `@name`).

### R3: CSS Similarity (20% weight)
Compares tag names, CSS classes, and DOM attributes.

### R4: Neighbor Similarity (10% weight)
Compares surrounding elements and DOM position context.

### Penalties & Adjustments
- **Tag mismatch:** -25% penalty
- **Weight normalization:** Recalculates weights when attributes are absent on both sides
- **Margin check:** Requires 10% gap between best and second-best candidate

### Confidence Thresholds

| Zone | Range | Behavior |
|------|-------|----------|
| **Auto-heal** | >= 75% | System automatically applies the heal |
| **Caution** | 20% – 75% | System logs warning, needs review |
| **Halt** | < 20% | System stops, too uncertain to heal |

### Three-Strike Lock
Repeated low-confidence heal attempts for the same locator are blocked after 3 strikes. State persisted in `data/heal_state.json`.

---

## Infrastructure Healing

| Trigger | Action |
|---------|--------|
| Service Down (HTTP 0/500) | Kill stale process, relaunch `demo_target_app.py`, verify response |
| Disk > 85% + Error > 40% | Purge temp files, rotate metrics history (keep last 20) |
| Disk > 85% only | Purge temp files, rotate metrics history |

All actions logged to `data/buckets/infrastructure.json` and visible in the **Infrastructure** dashboard tab.

---

## Dashboard Tabs

| Tab | Description |
|-----|-------------|
| **UI Heuristic Healing** | All heal attempts with R1–R4 breakdown, confidence, reason for repair, QA recommendations |
| **Locator Self-Correction** | Patched test scripts, old → new locator mapping, backups, approve/reject |
| **Infrastructure** | Service restarts, log rotations, error counter resets |
| **Alerts** | System alerts, failed heals, critical disk warnings |
| **Analytics** | Stability scores, cost analysis, heal history trends |
| **Configuration** | Target app settings, source heal files, confidence thresholds, approval mode |

---

## Demo Test Script

`demo_test.py` runs 4 test cases:

| # | Locator Strategy | Target |
|---|-----------------|--------|
| 1 | `By.ID` | `submit-btn` |
| 2 | `By.CSS_SELECTOR` | `#cancel-btn` |
| 3 | `By.XPATH` (`@id`) | `//button[@id='submit-btn']` |
| 4 | `By.XPATH` (`normalize-space()`) | `//button[normalize-space()='Cancel']` |

Uses `selfheal.install()` for zero-touch healing integration.

---

## Configuration

Edit `data/config_override.json`:

```json
{
  "target_app_port": 8000,
  "target_html_file": "demo_page.html",
  "active_fingerprint_path": "data/fingerprints/baseline_fingerprints.json",
  "confidence_threshold_high": 75.0,
  "confidence_threshold_low": 20.0,
  "source_heal_enabled": true,
  "source_heal_targets": ["demo_test.py"],
  "approval_mode_enabled": false
}
```

Or use the **Configuration** tab in the dashboard.

---

## Common Issues

### Issue: "File not found" when learning
**Solution:** Ensure `demo_page.html` exists in `selfheal_engine/` and path is correct in config.

### Issue: Tests fail even with healing
**Solution:** Check confidence in dashboard. If < 20%, system halts. Check three-strike lock in `data/heal_state.json`.

### Issue: Dashboard not showing heals
**Solution:** Ensure source healing is enabled in Configuration tab and `baseline_fingerprints.json` exists.

### Issue: Chrome driver errors
**Solution:** System auto-downloads ChromeDriver via `webdriver_manager`. Check internet connection.

### Issue: Port 8000 already in use
**Solution:** Kill existing process:
```powershell
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process
```

### Issue: Infra monitor not healing
**Solution:** Ensure both target app and infra monitor are running. Check `data/metrics_history.json` for snapshots. Healer triggers on `Down` status or disk > 85%.

---

## Requirements

```powershell
pip install -r requirements.txt
```

Key dependencies:
- `selenium`
- `streamlit`
- `webdriver-manager`
- `psutil`

---

## Testing Checklist

Before running your demo:

- [ ] Dashboard running on port 8501
- [ ] Target app started (port 8000)
- [ ] Infra monitor started
- [ ] `baseline_fingerprints.json` captured
- [ ] Source healing enabled in Configuration
- [ ] `demo_test.py` passes on clean HTML
- [ ] Edit `demo_page.html` to break a locator
- [ ] Run test again — verify heal in dashboard
- [ ] Kill target app — verify infra heal in Infrastructure tab

---

## License

This is a demonstration system for educational purposes.

---

## Credits

Built with:
- Selenium WebDriver
- Streamlit
- Python 3.x
- ChromeDriver
- psutil
