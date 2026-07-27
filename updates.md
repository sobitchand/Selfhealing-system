# Operating Guide — Self-Healing System

How to run everything in the project as it now stands, what each command proves,
and what to do when something misbehaves.

For the presentation script specifically, see
[`demo/DEMO_RUNBOOK.md`](demo/DEMO_RUNBOOK.md) — that document is the talk track.
This one is the reference.

---

## 1. Setup

Requirements: Python 3.10+, Google Chrome installed.

```powershell
cd demo
pip install -r requirements.txt
```

Chromedriver is resolved automatically — a cached driver under `~/.wdm/` is
preferred, and `webdriver-manager` downloads one only if no cache exists. So the
first run needs network; later runs do not.

`pytest` is **not** in requirements. Everything works without it; install it only
if you want integration level 3 (`pip install pytest`).

---

## 2. Quick start

```powershell
cd demo
python demo.py --dashboard
```

One command. It starts the application under test, runs the same unmodified QA
suite twice against the same refactored build — once on stock Selenium, once
with the healing layer installed — and prints the comparison.

Expected ending:

```
  Baseline .................. 1/5 passed
  With self-healing layer ... 5/5 passed
  Tests recovered ........... 4
  Locator heals performed ... 5  (mean ~35ms each)
  Suite wall-clock .......... 15.7s → 2.5s
  Test code changed ......... 0 lines
```

Flags:

| Flag | Effect |
|------|--------|
| `--headed` | run Chrome visibly so the audience can watch |
| `--dashboard` | launch the Streamlit dashboard on :8501 alongside |
| `--break MODE` | fault to inject: `refactor` (default), `css`, `id`, `attr`, `all` |

It also clears `data/heal_state.json` on startup, so a previous bad run cannot
leave a locator locked and silently sabotage the demo.

---

## 3. Every entry point

Run all of these from inside `demo/`.

| Command | What it does |
|---------|--------------|
| `python demo.py` | **the demo** — baseline vs healed, one command |
| `python -m streamlit run dashboard.py` | dashboard on http://localhost:8501 |
| `python demo_target_app.py [port]` | the application under test (default :8000) |
| `python collector_server.py` | sink for in-browser agent events (:8766) |
| `python tests/runner.py [--heal]` | run the QA suite once, either way |
| `pytest tests/ --self-heal` | same suite through pytest (needs pytest) |
| `python run_qa_heal.py` | 4 single-attribute fault scenarios, expect 4/4 |
| `python run_selenium_heal.py` | one real end-to-end Selenium heal |
| `python demo_show.py` | narrated source write-back, with before/after diff |
| `python demo_show.py --reset` | re-arm the broken locator for another pass |
| `python simulate_infra_heal.py` | canned infrastructure recovery |
| `python test_ui_healing.py` | canned UI heal, no browser needed |
| `python reset_demo.py` | **run before presenting** — see §7 |

---

## 4. Putting the layer on a Selenium suite

Three integration levels, all sharing one heal core. `tests/test_pomodoro.py` and
`tests/pages/` are an ordinary page-object suite that imports none of this — they
are the control, byte-identical across every run below.

### Level 1 — transparent proxy (1 line)

```python
from automation_wrapper import SelfHealingWebDriver
driver = SelfHealingWebDriver(webdriver.Chrome())
```

Every non-lookup call is delegated to the real driver, so this is substitutable
for one — waits, page objects, `execute_script`, `quit()` all work.

### Level 2 — zero-touch patch (1 line, anywhere in setup)

```python
import selfheal
selfheal.install()
```

Patches `find_element` on both `WebDriver` and `WebElement`, so nested
page-object lookups heal too. Because `WebDriverWait`'s expected conditions call
`find_element` internally, **explicit waits heal instead of timing out**.
`selfheal.uninstall()` restores stock Selenium.

`find_elements` healing is opt-in — `selfheal.install(heal_find_elements=True)`.
An empty list is a legitimate answer to `find_elements`, not a failure signal, so
healing it by default converts every true absence into a false match. Learning
Mode also runs with healing suppressed, so the baseline scan cannot generate
heals of its own.

```powershell
python tests/runner.py                    # baseline  -> 1/5
python tests/runner.py --heal             # healed    -> 5/5
python tests/runner.py --heal --headed    # ...and watch it
```

Runner flags: `--url`, `--baseline-url`, `--relearn`, `--quiet`.

### Level 3 — pytest (0 lines)

```powershell
pip install pytest
pytest tests/                # 1/5 — stock Selenium
pytest tests/ --self-heal    # 5/5 — same files
```

`--headed` also works. The fixture prints a heal summary at the end of the run.

### Recording the golden baseline

Fingerprints must be learned from a **known-good** build, never from a broken
page. `demo.py` and the runner do this automatically before the healed run; to
do it by hand:

```python
selfheal.learn_baseline(driver, url="http://127.0.0.1:8000", force=True)
```

`force=True` rescans; without it, learning only runs when no baseline exists.

---

## 5. The dashboard

```powershell
python -m streamlit run dashboard.py     # http://localhost:8501
```

| Tab | Shows |
|-----|-------|
| **Locator healing** | every heal, with confidence and the R1·R2·R3·R4 breakdown |
| **Source write-back** | corrected locators written back into automation source |
| **Infrastructure** | disk / error-rate / health recovery actions |
| **Alerts** | safety-gate refusals, repeated-failure escalations, browser faults |

The sidebar carries live traffic, active requests, error rate and disk usage from
the target app. The page refreshes every 3 seconds.

Styling lives in `theme.py`: Libertinus Serif (the maintained fork of Linux
Libertine) inlined from `assets/` as base64, so it renders identically with no
network. Streamlit's own chrome — the running-man status widget, toolbar, deploy
button, rainbow bar and footer — is hidden by CSS, not removed; the refresh loop
is untouched. To bring any of it back, delete the relevant selector from the
`Streamlit chrome` block in `theme.py`.

`DASH_NO_REFRESH=1` freezes the page, which is what the screenshot capture uses.

---

## 6. Individual scenarios

Start the three services first, each in its own terminal:

```powershell
python -m streamlit run dashboard.py     # :8501
python collector_server.py               # :8766
python demo_target_app.py                # :8000
```

| Case | Command | Proves |
|------|---------|--------|
| **Safety halt** | set `run_selenium_heal.py` line 43 to `(By.ID, "zzz-nonexistent-999")`, then `python run_selenium_heal.py` | confidence below 20% → refuses to act, critical row in **Alerts**. The system knows when *not* to guess. |
| **Intent-aware** | line 43 → `(By.ID, "btn-focus")` | heals to **Focus**, not START — not hardcoded to one element |
| **Source write-back** | `python demo_show.py` | the broken locator is rewritten in the test source |
| **Attribute faults** | `python run_qa_heal.py` | 4 faults (class / id / data-attr / all), 4/4 healed |
| **Infrastructure** | `python simulate_infra_heal.py` | a rule-based recovery action |
| **Browser agent** | open http://127.0.0.1:8000 in Chrome | broken image → warning in **Alerts** |

After the safety-halt or write-back cases, restore state with
`python demo_show.py --reset` and set line 43 back to `(By.ID, "start-btn")`.

---

## 7. Before presenting

```powershell
python reset_demo.py
```

Clears every telemetry bucket and the metrics history so the dashboard starts
empty and fills **live** in front of the audience, resets the feedback-loop locks,
and re-arms the source-heal target from its `.bak`. Idempotent — safe to run
repeatedly. Add `--keep-history` to keep the infrastructure metrics.

Then: `python demo.py --dashboard`.

---

## 8. Environment variables

| Variable | Used by | Meaning |
|----------|---------|---------|
| `APP_URL` | tests | application under test (default `http://127.0.0.1:8000`) |
| `BASELINE_URL` | conftest | known-good build to learn fingerprints from |
| `RELEARN_BASELINE=1` | conftest | force a fresh baseline scan |
| `QA_TIMEOUT` | page object | explicit-wait timeout in seconds (default 5) |
| `TARGET_APP_PORT` | target app, scenario scripts | port to bind / connect to (default 8000) |
| `TARGET_URL` | scenario scripts | full override for the application URL |
| `DASH_NO_REFRESH=1` | dashboard | freeze the page, no auto-refresh |

---

## 9. Troubleshooting

**Every test fails, including ones that should pass.**
Something else is on port 8000. `demo.py` verifies the page really is the
Pomodoro app before reusing a port and falls back to 8010/8020/8030 with a
printed notice, so it handles this by itself. The standalone scenario scripts
(`run_qa_heal.py`, `run_selenium_heal.py`, `demo_show.py`) connect to whatever
`TARGET_APP_PORT` says, so tell them where the app is:

```powershell
curl http://127.0.0.1:8000/ | Select-String "Pomodoro"    # is it ours?

$env:TARGET_APP_PORT = "8010"
python demo_target_app.py 8010
python run_qa_heal.py                                      # now uses :8010
```

**"Self-healing locked for 'X' after repeated failures."**
The three-strike loop guard tripped in an earlier run and persists to disk by
design. Clear it:

```powershell
python reset_demo.py
```

**A heal picks the wrong element, or confidence is unexpectedly low.**
The golden baseline is stale — it was learned from a different build. Rescan:

```powershell
python tests/runner.py --heal --relearn
```

**Chrome won't start.**
Google Chrome must be installed. The first run may need network to fetch
chromedriver; after that it uses the `~/.wdm/` cache.

**The dashboard is empty.**
Nothing has healed yet. Run `python demo.py`, or check that the buckets under
`data/buckets/` are not all `[]` after a `reset_demo.py`.

---

## 10. What changed

| Area | Before | Now |
|------|--------|-----|
| Wrapper | `find_element` only; not substitutable for a driver | full delegation, re-entrancy guard, heal cache |
| Waits | `TimeoutException` never healed | heal inside `find_element`, so waits recover |
| Integration | none | three levels: proxy / `install()` / `pytest --self-heal` |
| Test suite | none | `tests/` — page objects, explicit waits, healing-agnostic |
| Fault | markup-only rename that also broke the app's own JS | `?break=refactor`, consistent rename; app still works, only locators rot |
| Heal cost | ~6 WebDriver round trips × 200 elements | one `execute_script`; mean heal ≈ 30ms |
| Demo | 4 terminals, 7 cases, manual edits | `python demo.py` |
| Dashboard | dark, emoji headings, inflated labels | white, Libertinus Serif, plain language, Streamlit chrome hidden |
| Port handling | assumed anything on :8000 was ours | verifies the app, falls back to 8010/8020/8030 |
| False heals | Learning Mode's discovery scan was itself healed | learning runs suppressed; `find_elements` healing is opt-in |

### The false-heal fix, in detail

Worth knowing because it is the answer to "what if it heals the wrong thing?".

From a clean reset the system used to log `tag name='select' → button` at 80%
confidence as an AUTOMATIC HEAL — there is no `<select>` on the page — plus two
critical alerts for `input` and `textarea`. `FingerprintManager.scan_interactive()`
probes each interactive tag with `find_elements` while building the baseline, and
with the layer installed those *discovery* probes were being healed. So the
system was healing its own learning pass and inventing matches.

Two changes: baseline learning now runs inside `automation_wrapper.suppressed()`,
and `find_elements` healing became opt-in, because an empty list is a legitimate
answer rather than a failure signal.

A clean run now logs exactly 5 heals and 0 alerts.

---

## 11. Known gaps

Neither blocks the demo. Worth knowing before the defence in case a judge asks.

1. **`--relearn` merges rather than replaces.** The fingerprint registry has
   accumulated stale entries (`time-display`, `session-log`, `dur-focus`,
   `stat-pomodoros` — divs and spans `scan_interactive` doesn't capture).
   Harmless today, but a stale fingerprint winning intent matching is a real
   failure mode.

2. **`source_healer.py` rewrites test source with regex.** Fine for the demo;
   nobody would let it near a production repo. The stronger answer is a locator
   repository the tests reference by logical name, with source-patching kept as
   an opt-in flag — that is what industry tools do, so it defends better.

3. **The tag gate is absolute.** `healing_engine.py` skips any candidate whose
   tag differs from the golden fingerprint, so a `<button>` refactored into an
   `<a>` heals to nothing. A heavy score penalty would be more forgiving than a
   hard skip.

4. **`qa_evidence/screenshots/` still shows the old dark dashboard.** Re-run
   `python qa_evidence/capture.py` before submitting so the evidence matches the
   live UI.
