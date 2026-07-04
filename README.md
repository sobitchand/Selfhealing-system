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
Request & Application Layer   demo_target_app.py      (Pomodoro AUT + UI + backend)
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

## 5. How to run & show each step

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

## 6. Project layout

```
demo/
├── demo_target_app.py        # Pomodoro AUT + live metrics thread + JS agent host
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
├── test_ui_healing.py        # fast canned UI-heal scenario (no browser)
├── simulate_infra_heal.py    # canned infrastructure-heal scenario
│
├── store.py                  # per-bucket atomic JSON store (filelock + rolling window)
├── config.py                 # paths, thresholds, buckets, source-heal targets
├── dashboard.py              # Streamlit control panel (4 tabs + sidebar)
│
├── selfhealing/metrics_monitor.py   # background telemetry thread (passive)
├── data/                     # fingerprints, metrics history, per-bucket store, heal_state
└── qa_evidence/              # capture.py, qa_checks.py, QA_REPORT.md, screenshots/
```

---

## 7. Storage

Each telemetry stream is its own file under `data/buckets/` (`ui_heals`,
`infrastructure`, `alerts`, `browser_events`, `source_heals`), written through
`store.py`: atomic temp→`os.replace`, per-bucket `filelock` (cross-process safe),
and a rolling-window size cap (`config.BUCKET_LIMITS`).

---

## 8. Tech stack

Python · Selenium WebDriver · JSON (lightweight fingerprint/metadata store) ·
Streamlit + Plotly (dashboard) · filelock (atomic store). Rule-based only — no ML.
