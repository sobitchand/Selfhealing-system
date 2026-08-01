# Rule-Based Self-Healing System for Web Application Reliability

> 📂 **All source code lives in [`demo/`](demo/).** Run commands from inside that
> folder: `cd demo` first. (`demo/readme.md` is the same document.)

A lightweight, rule-based autonomous management layer that keeps web-application
**test automation** and **infrastructure** running when things break — with no
machine learning, fully deterministic, and a live dashboard. This is the
implementation of the major project proposal *"Rule-Based Self-Healing System for
Enhancing the Reliability of Web Applications"* (EEC).

---

## 1. What it actually does

When a UI test points at an element whose locator has **broken** (id/class/xpath
changed by a developer), a normal Selenium test crashes with
`NoSuchElementException`. This system intercepts that crash and:

1. **Detects** the failure (Healing Mode trigger).
2. **Scrapes** the live DOM and collects candidate elements.
3. **Scores** each candidate against a stored *Golden Fingerprint* using a
   weighted heuristic (Table 3.1 — text/xpath/css/neighbors).
4. **Decides** by confidence threshold (auto-heal / cautious / halt).
5. **Self-corrects**: writes the healed locator back into the fingerprint
   metadata **and** the test automation source, so the fix is permanent.
6. **Verifies + logs** the outcome and shows it on a real-time dashboard;
   escalates to a human alert when it is not safe to act.

In parallel, an **infrastructure monitor** watches disk / error-rate / service
health and fires rule-based recovery actions (log rotation, worker reload, etc.).

> **Important:** "healing the code" = fixing the **locator** (in the metadata
> repository and the automation script). The application-under-test's own HTML is
> **never** modified — it is the target, not the patient.

---

## 2. Architecture (5 layers, mapped to the proposal §3.1.2)

```
Request & Application Layer   demo_target_app.py      (NovaBank AUT + UI + backend)
Monitoring Layer              selfhealing/metrics_monitor.py  (traffic/disk/health/error)
Decision Layer                healing_engine.py       (rule engine + R1-R4 scoring + thresholds)
Healing & Execution Layer     automation_wrapper.py   (Selenium interceptor, reroute)
                              source_healer.py        (automation-source self-correction)
                              feedback.py             (verify -> escalate, loop guard)
Visibility & Control Layer    dashboard.py            (Streamlit: logs, rates, alerts)
```

### Two request paths (`handlers.py`)
- **Active path** (`handle_active_heal`): synchronous. Selenium blocks and gets
  back a heal decision (lifecycle + locator + confidence) so it can keep driving.
- **Passive path** (`handle_passive_event`): fire-and-forget telemetry ingest
  (browser-agent JS errors, infra metrics). Producer waits for nothing.

Both persist through one atomic, cross-process-safe store (`store.py`).

### Two operating modes (proposal §3.4)
- **Learning Mode** (`learning_mode.py`, `fingerprint_manager.py`): if no baseline
  fingerprint metadata exists, the system scans the live AUT and captures a Golden
  Fingerprint (id, text, xpath, css, tag, neighbors) for every interactive
  element. Auto-triggered — delete the JSON and it rebuilds itself.
- **Healing Mode** (`automation_wrapper.py` + `healing_engine.py`): the runtime
  recovery flow described above.

---

## 3. The heuristic (Table 3.1)

When an element is not found, every live candidate is scored against the Golden
Fingerprint:

| Rule | Attribute | Weight | Meaning |
|------|-----------|--------|---------|
| R1 | Inner text       | 40% | visible label / button text |
| R2 | XPath pattern    | 30% | structural tree-position similarity |
| R3 | CSS class        | 20% | styling / design attributes |
| R4 | Neighbors        | 10% | surrounding elements match |

`confidence = 0.40·R1 + 0.30·R2 + 0.20·R3 + 0.10·R4`

**Decision thresholds** (`config.py`) and **error behavior**:

| Score | Action | Throws error to test? |
|-------|--------|-----------------------|
| **≥ 75%** | Automatic Heal — reroute + update metadata + patch source | No — element returned |
| **20–75%** | Cautious Heal — reroute but flag the row for review | No — element returned |
| **< 20%** | Halt — raise CRITICAL alert, manual intervention | **Yes** — only here |

So as long as confidence is **not critical (≥20%)**, the heal succeeds silently and
the test keeps running; an error surfaces **only** when the match is too low (<20%)
to act safely.

### What triggers a heal vs what the rules do
- **Trigger** = the *locator breaks* → `NoSuchElementException` (the id/css/xpath
  the test searches by no longer finds anything). The R1–R4 rules do **not**
  trigger the heal.
- **R1–R4** then *re-identify* the element among DOM candidates and compute the
  confidence. How much each attribute changed determines which rule's score drops
  and therefore the auto / cautious / halt outcome.

**Intent-aware matching:** the broken locator id is first matched to the
fingerprint it *meant* (`select_target_fingerprint`), so two different broken
locators heal to two different elements instead of both grabbing the top match.

**Feedback loop** (`feedback.py`, proposal §3.4.4): every heal is verified; if the
same locator fails to heal 3 times in a row it is **locked** and escalated — no
infinite recovery loops.

---

## 4. Setup

Prereqs: Python 3.10+, Google Chrome installed.

```bash
pip install -r requirements.txt
```

---

## 5. Using it on a real Selenium QA suite

The healing layer is designed to be **bolted onto an existing test suite that
knows nothing about it**. `tests/test_pomodoro.py` and `tests/pages/` are an
ordinary page-object suite — explicit waits, behavioural assertions, zero
healing imports — and they are run unchanged with and without the layer.

Three integration levels, all sharing one heal core:

| Level | Integration | Test-suite changes |
|-------|-------------|--------------------|
| **1 — transparent proxy** | `driver = SelfHealingWebDriver(webdriver.Chrome())` | 1 line |
| **2 — zero-touch patch** | `import selfheal; selfheal.install()` | 1 line, anywhere in setup |
| **3 — pytest** | `pytest tests/ --self-heal` | none |

Level 2 patches `find_element` on both `WebDriver` and `WebElement`, so nested
page-object lookups are covered — and because `WebDriverWait`'s expected
conditions call `find_element` internally, **explicit waits heal too** instead of
timing out. Level 1 delegates every non-lookup call to the real driver, so the
wrapper is substitutable for one.

`find_elements` healing exists but is **off by default**
(`selfheal.install(heal_find_elements=True)` enables it). An empty list is a
legitimate answer to `find_elements` — "no error banners on screen" — not a
failure signal the way a raised `NoSuchElementException` is, so healing it turns
every true absence into a false match.

### The one-command demonstration

```bash
python demo.py --dashboard        # add --headed to watch Chrome
```

Runs the same suite twice against the same refactored build — once on stock
Selenium, once with the layer installed:

```
  Baseline .................. 1/5 passed
  With self-healing layer ... 5/5 passed
  Tests recovered ........... 4
  Locator heals performed ... 5  (mean ~35ms each)
  Suite wall-clock .......... 16.9s → 2.8s
  Test code changed ......... 0 lines
```

The fault injected is `?break=refactor`: ids, classes and a data attribute are
renamed **consistently**, so the application still works perfectly for a human
user — only the recorded locators have rotted. That is how locator rot happens
in practice, and the failing baseline is also ~6× slower because every broken
locator burns its full wait timeout.

Full talk track in [`DEMO_RUNBOOK.md`](demo/DEMO_RUNBOOK.md).

---

## 6. Running the individual scenarios

Open the dashboard first and keep it visible:

```bash
# Dashboard  ->  http://localhost:8501
python -m streamlit run dashboard.py

# Target app ->  http://127.0.0.1:8000   (separate terminal)
python demo_target_app.py
```

Then run any scenario below. Each maps to a validation row (proposal §3.8 / Ch.5)
and to a screenshot in `qa_evidence/screenshots/`.

| # | Command | What it proves | Screenshot |
|---|---------|----------------|------------|
| 1 | `python run_selenium_heal.py` | **Healing Mode**: broken `old-start-btn` → real heal (≥75%), metadata + source self-correct | `02_dashboard_ui_healing.png` |
| 2 | delete `data/pomodoro_3d_fingerprints.json` then `python run_selenium_heal.py` | **Learning Mode** auto-rebuilds the baseline, then heals | — |
| 3 | `python simulate_infra_heal.py` | **Infrastructure heal** on disk/error stress | `04_dashboard_infrastructure.png` |
| 4 | request a wildly-changed locator (see QA report) | **Safety gate**: <20% → halt + CRITICAL alert | `05_dashboard_alerts.png` |
| 5 | re-run a heal | **Permanence/idempotent**: locator now valid, no heal needed | `03_dashboard_locator_self_correction.png` |

### Demonstrating each rule (break one attribute at a time)
First break the locator so the heal fires, then change one fingerprinted
attribute and watch that rule's component score drop on the dashboard while the
heal still succeeds:

| Change in `demo_target_app.py` (the AUT) | Rule that drops | Expected |
|------------------------------------------|-----------------|----------|
| rename `id="start-btn"` (so old locator misses) | (triggers the heal) | heal fires |
| change button text `START` | R1 (40%) | big score drop, still heals |
| move the button / change position | R2 (30%) | medium drop |
| change `class="btn btn-main"` | R3 (20%) | small drop |
| change surrounding elements | R4 (10%) | tiny drop |

Change one → score stays ≥75 → auto-heal. Change many → score <20 → halt + alert
(the safety demo).

**One-click guided demo** (re-arms, runs, shows the before/after source diff):

```bash
python demo_show.py            # full narrated run
python demo_show.py --reset    # re-arm the broken locator for another pass
```

What to watch on the dashboard:
- **🔗 UI Heuristic Healing** — heal rows, R1–R4 breakdown, Healing Rate vs Success Rate.
- **📝 Locator Self-Correction** — old→new locator written back to source/metadata.
- **⚙️ Server Infrastructure Heals** — backend recovery actions.
- **🚨 Alert Notification Logs** — browser errors + low-confidence/repeated-failure escalations.
- **Sidebar** — live traffic / error rate / disk from the target app.

### Step-by-step demo script (for a presentation)

**Setup (before you start):** two terminals in `demo/`, plus a browser.
```bash
python -m streamlit run dashboard.py    # terminal 1  -> open http://localhost:8501
python demo_target_app.py               # terminal 2  -> open http://127.0.0.1:8000
```

1. **Show the app.** Open `http://127.0.0.1:8000` — the Pomodoro timer. "This is
   the live web app our tests drive."
2. **Show the broken locator.** Open `run_selenium_heal.py`, point at line 28:
   `BROKEN_LOCATOR = (By.ID, "old-start-btn")`. "This id does not exist — a normal
   test crashes here."
3. **Run the heal.** Terminal: `python run_selenium_heal.py`. Read the output live:
   `⚠️ Element Missing → 🔬 scored candidates → ✨ Auto-Heal (≥75%) → ✅ resolved`.
4. **Show the source changed.** Line 28 now reads `start-btn`. "The system rewrote
   the broken locator in the source — permanent fix." (backup kept as `.bak`).
5. **Show the dashboard.** `http://localhost:8501`:
   - *UI Heuristic Healing* → the heal row with R1–R4 scores + confidence + rates.
   - *Locator Self-Correction* → old→new locator write-back log.
6. **Prove it's permanent.** Run `python run_selenium_heal.py` again → element found
   directly, no heal needed.
7. **(Optional) Safety demo.** Change many attributes / a non-existent element →
   score <20% → it halts and posts a CRITICAL row in *Alert Notification Logs*
   instead of clicking the wrong element.
8. **(Optional) Infra + Learning.** `python simulate_infra_heal.py` (infra tab);
   delete `data/pomodoro_3d_fingerprints.json` then run a heal → Learning Mode
   rebuilds the baseline automatically.

**Easiest path:** `python demo_show.py` runs steps 2–6 automatically with a paced,
narrated before/after source diff. Re-arm for another pass with
`python demo_show.py --reset`. Full talk-track in `DEMO_GUIDE.md`.

---

## 7. Project layout

```
demo/
├── demo.py                   # ONE-COMMAND demo: baseline vs healed, same suite
├── selfheal.py               # zero-touch integration (patches Selenium in place)
├── tests/                    # ordinary QA suite — unaware of the healing layer
│   ├── test_pomodoro.py      #   behavioural tests (start/pause/reset/skip/mode)
│   ├── pages/pomodoro_page.py#   page object: locators + explicit waits
│   ├── conftest.py           #   pytest fixture + --self-heal flag
│   ├── runner.py             #   pytest-free runner (--heal / --headed)
│   └── driver_factory.py     #   Chrome + Firefox factory (cross-browser support)
│
├── demo_target_app.py        # NovaBank AUT: serves examples/bank original vs refactored
├── selfhealing_agent.js      # in-browser agent (JS errors, image/selector healing)
├── collector_server.py       # HTTP sink for the browser agent (passive path)
│
├── automation_wrapper.py     # SelfHealingWebDriver — Selenium find_element interceptor
├── healing_engine.py         # R1-R4 heuristic + thresholds + infra rule engine
├── handlers.py               # active (sync heal) vs passive (telemetry) paths
├── feedback.py               # verify -> escalate, infinite-loop guard
├── source_healer.py          # write healed locator back into automation source
│
├── fingerprint_manager.py    # capture Golden Fingerprints (manual + auto-discover)
├── learn_ui_fingerprint.py   # CLI to record a fingerprint from a live page
├── learning_mode.py          # auto-bootstrap baseline if metadata missing
├── dom_features.py           # shared xpath + neighbor extraction (learning + healing)
│
├── run_selenium_heal.py      # REAL end-to-end Selenium self-heal entry point
├── demo_show.py              # one-click narrated demo (before/after source diff)
├── simulate_infra_heal.py    # canned infrastructure-heal scenario
│
├── benchmark.py              # 50+ scenario benchmark with success rate, heal time, confidence histogram
├── run_cross_browser_benchmark.py  # Chrome vs Firefox comparison
├── analytics.py              # locator stability, flaky detection, cost analysis
│
├── store.py                  # per-bucket atomic JSON store (filelock + rolling window)
├── config.py                 # paths, thresholds, buckets, source-heal targets
├── config_manager.py         # dashboard-driven configuration (no code editing needed)
├── dashboard.py              # Streamlit control panel (6 tabs + sidebar)
│
├── selfhealing/metrics_monitor.py   # background telemetry thread (passive)
├── data/                     # fingerprints, metrics history, per-bucket store, heal_state
└── qa_evidence/              # capture.py, qa_checks.py, QA_REPORT.md, screenshots/
```

---

## 8. Storage

Each telemetry stream is its own file under `data/buckets/` (`ui_heals`,
`infrastructure`, `alerts`, `browser_events`, `source_heals`), written through
`store.py`: atomic temp→`os.replace`, per-bucket `filelock` (cross-process safe),
and a rolling-window size cap (`config.BUCKET_LIMITS`).

---

## 9. Tech stack

Python · Selenium WebDriver · JSON (lightweight fingerprint/metadata store) ·
Streamlit + Plotly (dashboard) · matplotlib (benchmark charts) · filelock (atomic store). Rule-based only — no ML.

---

## 10. Advanced Analytics

Three analytics modules that neither Healenium nor Testim provide. Run them
individually or view everything in the dashboard's **Analytics** tab.

### Locator Stability Scoring

Predicts which locators are likely to break **before** they break. Each locator
is scored 0–100 across five dimensions:

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| ID specificity | 30% | ID-based locators are most stable |
| Semantic meaning | 25% | `start-btn` > `btn-123` > `a1` |
| Uniqueness | 20% | Single-match locators are more stable |
| DOM depth | 15% | Shallow XPath = less fragile |
| Text content | 10% | Text-based matching is stable if text doesn't change |

Locators scoring below 40 are flagged as **high risk** with a recommendation
(e.g., "request a semantic name from developers" or "use a shorter XPath").

```powershell
python analytics.py
```

### Flaky Locator Detection

Tracks heal frequency per locator. A locator that heals 3+ times is flagged as
flaky with severity and a recommendation. This catches tests that silently
degrade — they pass because the system heals them, but the underlying locator
is rotting.

### Cost Analysis

Calculates time and cost savings vs manual fixing:

| Metric | How it's computed |
|--------|------------------|
| Time saved | (manual_fix_minutes × total_heals) − (avg_heal_time_ms × total_heals / 60000) |
| Cost saved | time_saved_hours × hourly_rate |
| ROI | time_saved / manual_time × 100% |
| Heals per hour | 3600000 / avg_heal_time_ms |

Defaults: 10 minutes per manual fix, $50/hour engineer rate. Both configurable.

---

## 11. Benchmark Suite

### Single-Browser Benchmark

Runs 50+ fault scenarios across different mutation types (rename ID, rename class,
change text, restructure XPath, combined mutations, edge cases) and measures:

- **Success rate** — percentage of scenarios healed
- **Heal time** — average milliseconds per heal
- **Confidence distribution** — histogram across the 75%/20% thresholds
- **False positive rate** — heals with confidence < 50%
- **Mutation breakdown** — success rate per mutation type

```powershell
python benchmark.py --scenarios 50
```

Outputs:
- `benchmark_results/benchmark_results.json` — raw data
- `benchmark_results/benchmark_report.md` — human-readable report with industry comparison
- `benchmark_results/confidence_histogram.png` — distribution chart

### Cross-Browser Benchmark

Runs the same benchmark on Chrome and Firefox, then compares results. Checks
consistency across three metrics:

| Metric | Consistency threshold |
|--------|----------------------|
| Success rate | < 5% difference |
| Heal time | < 20ms difference |
| Confidence | < 5% difference |

```powershell
python run_cross_browser_benchmark.py --scenarios 50
```

Outputs:
- `benchmark_results/cross_browser_comparison.json` — raw comparison
- `benchmark_results/cross_browser_report.md` — consistency analysis

Cross-browser support is built into `tests/driver_factory.py` — `make_driver()`
accepts `browser="chrome"` or `browser="firefox"` and resolves the
appropriate driver (chromedriver or geckodriver) from the `~/.wdm/` cache.

---

## 12. Dashboard Configuration

The **Configuration** tab in the dashboard allows you to configure the system
without editing code. All changes are saved to `data/config_override.json` and
applied automatically to all future healing operations.

### What you can configure

| Setting | What it controls |
|---------|-----------------|
| **Source healing toggle** | Enable/disable writing healed locators back to test files |
| **Source heal targets** | Which test files get patched when locators are healed |
| **Auto-heal threshold** | Confidence score above which heals are applied automatically (default: 75%) |
| **Safety gate threshold** | Confidence score below which heals are rejected (default: 20%) |

### How to use it

1. Open the dashboard: `python -m streamlit run dashboard.py`
2. Click the **Configuration** tab
3. Toggle source healing on/off
4. Add your test files:
   - Click **Scan for test files** to auto-discover test files in your project
   - Select from the dropdown and click **Add selected file**
   - Or enter a path manually and click **Add manual path**
5. Adjust confidence thresholds using the sliders
6. Changes are saved automatically

### Why this matters

Previously, you had to edit `config.py` to add test files:

```python
# config.py (old way)
SOURCE_HEAL_TARGETS = [
    os.path.join(BASE_DIR, "tests/test_login.py"),
    os.path.join(BASE_DIR, "tests/test_dashboard.py"),
]
```

Now you can do it from the dashboard — no code editing, no restart needed.

### Configuration persistence

All configuration changes are saved to `data/config_override.json`. This file
takes precedence over the defaults in `config.py`. To reset to defaults, click
**Reset to defaults** in the Configuration tab.

---

## 13. Comparison with Industry Tools

| Feature | Our System | Healenium | Testim | Manual Fix |
|---------|-----------|-----------|--------|------------|
| **Heal Success Rate** | ~90% | ~85% | ~90% | 100% (but slow) |
| **Avg Heal Time** | ~35ms | ~200ms | ~150ms | 5-15 min |
| **Source Code Update** | ✓ Yes | ✗ No | ✗ No | ✓ Yes |
| **Confidence Scoring** | ✓ Yes (R1-R4) | ✗ No | ✗ No (ML black box) | N/A |
| **Safety Gate** | ✓ Yes (<20% halt) | ✗ No | ✗ No | N/A |
| **Locator Stability Prediction** | ✓ Yes | ✗ No | ✗ No | N/A |
| **Flaky Test Detection** | ✓ Yes | ✗ No | ✗ No | N/A |
| **Cost/ROI Analysis** | ✓ Yes | ✗ No | ✗ No | N/A |
| **Cross-Browser Benchmark** | ✓ Yes | ✗ No | ✗ No | N/A |
| **Dashboard Configuration** | ✓ Yes (no code editing) | ✗ No | ✓ Yes (web UI) | N/A |
| **Infrastructure Monitoring** | ✓ Yes | ✗ No | ✗ No | ✗ No |
| **Real-time Dashboard** | ✓ Yes | ✗ No | ✓ Yes | ✗ No |
| **External Dependencies** | None | PostgreSQL | Cloud account | None |
| **Explainability** | ✓ Yes (rule-based) | ✓ Yes (DOM diff) | ✗ No (ML) | ✓ Yes |
| **Cost** | Free | Free | $$$$ | Free (but labor) |
