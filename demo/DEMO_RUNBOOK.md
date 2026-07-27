# Demo Runbook — Self-Healing System

**The whole demonstration is one command.** Everything below the fold is
optional material for questions.

---

## The demo

```powershell
cd demo
python demo.py --dashboard
```

That starts the application under test, then runs the **same unmodified QA
suite twice** against the **same refactored build**:

| | |
|---|---|
| **Run 1 — baseline** | stock Selenium. Locators have rotted. **1/5 pass.** |
| **Run 2 — healed** | identical suite, `selfheal.install()` added. **5/5 pass.** |

Test files, page objects and the application are byte-identical between the two
runs. The only variable is whether the healing layer is installed — which is
what makes it evidence rather than a demo.

Expected output ends with:

```
  Baseline .................. 1/5 passed
  With self-healing layer ... 5/5 passed
  Tests recovered ........... 4
  Locator heals performed ... 5  (mean ~35ms each)
  Suite wall-clock .......... 16.9s → 2.8s
  Test code changed ......... 0 lines
```

Add `--headed` to watch Chrome do it.

---

## The 90-second talk track

1. **"This is an ordinary Selenium QA suite."** Open `tests/test_pomodoro.py`
   and `tests/pages/pomodoro_page.py`. Page objects, explicit waits, assertions
   on real behaviour. Nothing in either file mentions self-healing.

2. **"A developer refactored the app."** `demo_target_app.py` `?break=refactor`
   renames `start-btn → btn-start-primary`, `reset-btn → btn-reset-secondary`,
   `skip-btn → btn-skip-forward`, `btn-main → btn-cta`, `data-action` value.
   The renames are **consistent**, so the application still works perfectly —
   the timer ticks, buttons respond, a human user notices nothing. Only QA's
   recorded locators have rotted. *That is how locator rot actually happens.*

3. **"Run 1: the suite collapses."** 4 of 5 tests fail — `NoSuchElementException`
   and `TimeoutException`. Note that the failing run is also **6× slower**,
   because every broken locator burns its full wait timeout. This is the real
   cost of locator rot: red builds *and* slow builds.

4. **"Run 2: one line of integration."**

   ```python
   import selfheal
   selfheal.install()
   ```

   Same suite. 5/5. Each heal prints the broken locator, the element the engine
   recovered, the confidence, and the policy applied.

5. **"How does it decide?"** Point at the confidence column. `start-btn` heals
   at 95.65% because text and structure are untouched and only the class moved;
   `reset-btn` at 78.48% because it has no class at all, so R3 contributes
   nothing. Both clear the 75% automatic gate. That is Table 3.1 doing visible
   work — not a black box.

6. **"And when it shouldn't act?"** → optional case E below.

---

## The three integration levels

Show whichever the panel asks about.

| Level | Integration | Lines the QA team changes |
|-------|-------------|---------------------------|
| 1 | `driver = SelfHealingWebDriver(webdriver.Chrome())` | 1 |
| 2 | `import selfheal; selfheal.install()` | 1, anywhere in setup |
| 3 | `pytest tests/ --self-heal` | 0 |

Level 2 patches Selenium's own `find_element` / `find_elements` on both
`WebDriver` and `WebElement`, so nested page-object lookups and explicit waits
are covered too. Level 1 is a transparent proxy — every non-lookup call is
delegated untouched, so it is substitutable for a real driver.

```powershell
# level 3, if pytest is installed
pytest tests/                # 1/5 — stock Selenium
pytest tests/ --self-heal    # 5/5 — same files
```

---

## Optional cases (only if asked)

Start the services first — dashboard on :8501, collector on :8766, app on :8000:

```powershell
python -m streamlit run dashboard.py     # terminal A
python collector_server.py               # terminal B
python demo_target_app.py                # terminal C
```

| | Case | Command | Shows |
|---|------|---------|-------|
| **E** | **Safety halt** | set `run_selenium_heal.py` line 43 to `(By.ID, "zzz-nonexistent-999")`, run `python run_selenium_heal.py` | confidence < 20% → refuses to act, CRITICAL row in **Alert Notification Logs**. *The system knows when not to guess.* |
| **D** | Intent-aware | line 43 → `(By.ID, "btn-focus")` | heals to **Focus**, not START — the engine is not hardcoded to one element |
| **C** | Source write-back | `python demo_show.py` | the broken locator is rewritten in the test source; **Locator Self-Correction** tab. Re-arm with `--reset` |
| **A** | Attribute-level suite | `python run_qa_heal.py` | 4 single-attribute faults (class / id / data-attr / all), 4/4 healed |
| **F** | Infrastructure heal | `python simulate_infra_heal.py` | **Server Infrastructure Heals** tab |
| **G** | Browser agent | open http://127.0.0.1:8000 in Chrome | broken image → **Alert Notification Logs** |

After case C or E, reset: `python demo_show.py --reset`, then set line 43 back
to `(By.ID, "start-btn")`.

---

## Dashboard tabs

- 🔗 **UI Heuristic Healing** — locator heals + R1–R4 confidence breakdown
- 📝 **Locator Self-Correction** — source write-back log
- ⚙️ **Server Infrastructure Heals** — infra anomaly fixes
- 🚨 **Alert Notification Logs** — critical faults, resource failures, escalations
