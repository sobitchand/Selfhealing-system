# Updates — Self-Healing Layer for Selenium QA Suites

Branch: `feat/updates` · 10 commits · 22 files changed

---

## Why

Two problems with the project as it stood:

1. **The supervisor's request wasn't possible yet.** `SelfHealingWebDriver`
   exposed exactly one method — `find_element`. It had no `__getattr__`, no
   `find_elements`. So `driver.get(...)` raised `AttributeError`, and the class
   could not be handed to a test script it didn't already control. Our own
   `run_qa_heal.py` worked around it by keeping the real driver for navigation
   and routing only `find_element` through the healer. "Wrap an existing QA
   script" was therefore not achievable.

2. **The demo was too long to present.** The runbook needed 4 terminals and
   walked through 7 cases (A–G), with manual source edits between cases D and E.
   A jury loses the thread well before the end.

There was also a coverage hole: real Selenium suites are mostly explicit waits.
`WebDriverWait(...).until(...)` raises `TimeoutException`, not
`NoSuchElementException`, so healing covered none of them.

---

## What changed

### 1. The wrapper is now a real wrapper

`automation_wrapper.py` was restructured around a reusable heal core:

- **`__getattr__` delegation** — every non-lookup call (`get`, `quit`,
  `execute_script`, `current_url`, `switch_to`, …) passes through to the real
  driver, so the object is substitutable for one.
- **`find_elements`** — heals when the list comes back empty (Selenium returns
  `[]` rather than raising, so emptiness is the failure signal).
- **Re-entrancy guard** — the heal path itself drives the browser; without a
  guard a failed lookup *inside* a heal would recurse.
- **Resolved-locator cache** — an explicit wait polls `find_element` every
  ~500ms and a page object may look the same element up in a dozen places. We
  score once, remember the live xpath, and re-validate on re-use. Without this a
  single stale locator would be re-scored and re-logged on every poll.
- **Loop-guard ordering fixed** — `feedback.is_locked` is now checked *before*
  scoring, so an already-escalated locator no longer generates another dashboard
  row on every retry.

### 2. Zero-touch integration (`selfheal.py`, new)

```python
import selfheal
selfheal.install()
```

Patches `find_element`/`find_elements` on both `WebDriver` **and** `WebElement`,
so nested page-object lookups are covered — and because `WebDriverWait`'s
expected conditions call `find_element` internally, **explicit waits now heal
instead of timing out**. `uninstall()` restores stock Selenium.

Three integration levels are now supported, all sharing one heal core:

| Level | Integration | Test-suite changes |
|-------|-------------|--------------------|
| 1 — transparent proxy | `SelfHealingWebDriver(webdriver.Chrome())` | 1 line |
| 2 — zero-touch patch | `selfheal.install()` | 1 line, anywhere in setup |
| 3 — pytest | `pytest tests/ --self-heal` | none |

### 3. A QA suite that doesn't know the healing layer exists (`tests/`, new)

| File | Purpose |
|------|---------|
| `tests/test_pomodoro.py` | 5 behavioural tests: start, pause-toggle, reset, skip counter, mode switch |
| `tests/pages/pomodoro_page.py` | page object — locators + explicit waits |
| `tests/conftest.py` | pytest fixture and the `--self-heal` flag |
| `tests/runner.py` | pytest-free runner (`--heal` / `--headed`), since pytest isn't in requirements |
| `tests/driver_factory.py` | shared Chrome factory |

Neither test file imports, configures, or mentions the healing system. They are
**byte-identical between the healed and unhealed runs**, which is what makes the
comparison evidence rather than a demo.

### 4. A realistic fault (`?break=refactor`)

The existing `?break=id` / `?break=all` modes renamed markup only, which also
broke the application's own JavaScript — the timer stopped working entirely.
Fine for a locator demo, useless for one that asserts real behaviour.

The new `refactor` mode renames identifiers **consistently** across markup and
script:

| Before | After |
|--------|-------|
| `start-btn` | `btn-start-primary` |
| `reset-btn` | `btn-reset-secondary` |
| `skip-btn` | `btn-skip-forward` |
| `btn-focus` | `mode-focus-tab` |
| `btn-main` | `btn-cta` |
| `data-action="start"` | `data-action="begin"` |

The app still works perfectly — the timer ticks, buttons respond, a human user
notices nothing. Only QA's recorded locators have rotted. **That is how locator
rot actually happens.**

### 5. Heal latency: ~1500 round trips → 1

Candidate scraping used to call, per element: `tag_name`, two `get_attribute`s,
`compute_xpath` (its own `execute_script`) and `compute_neighbors` (another
`find_elements` plus per-sibling calls) — roughly 6 WebDriver round trips ×
200 elements per heal.

`dom_features.collect_candidates()` now walks the DOM inside the browser and
returns every candidate's R1–R4 features in **one** `execute_script`. The xpath
algorithm and the neighbour rule are kept byte-for-byte identical to the
originals, so golden fingerprints and live candidates still compare
like-for-like.

Measured result: **mean heal ≈ 35ms.**

### 6. The demo is one command

```bash
python demo.py --dashboard        # --headed to watch Chrome
```

Starts the application under test, then runs the same unmodified suite twice
against the same refactored build — once on stock Selenium, once with the layer
installed — and prints the contrast.

`DEMO_RUNBOOK.md` was rewritten around this: one command up front, a 90-second
talk track, and the old cases A–G demoted to an appendix for questions.

---

## The result

```
Baseline .................. 1/5 passed
With self-healing layer ... 5/5 passed
Tests recovered ........... 4
Locator heals performed ... 5  (mean ~35ms each)
Suite wall-clock .......... 16.0s → 2.6s
Test code changed ......... 0 lines
```

Per-test detail from the healed run:

| Test | Heal | Confidence |
|------|------|------------|
| `test_start_button_starts_the_timer` | `id='start-btn'` → `<button> "START"` | 95.65% AUTOMATIC |
| `test_start_button_toggles_to_pause_and_back` | `id='start-btn'` → `<button> "START"` | 95.65% AUTOMATIC |
| `test_reset_restores_the_focus_duration` | `id='start-btn'`, `id='reset-btn'` | 95.65% / 78.48% AUTOMATIC |
| `test_skip_increments_the_pomodoro_counter` | `id='skip-btn'` → `<button> "Skip"` | 80.00% AUTOMATIC |
| `test_short_break_mode_sets_five_minutes` | none needed | — |

Two details worth pointing at during the defence:

- **The confidence spread is explainable, not magic.** `start-btn` heals at
  95.65% because its text and structure are untouched and only the class moved.
  `reset-btn` heals at 78.48% because it has no CSS class at all, so R3
  contributes nothing. Both clear the 75% automatic gate. That is Table 3.1
  doing visible work.
- **The failing baseline is ~6× slower** (16.0s vs 2.6s), because every broken
  locator burns its full wait timeout. Locator rot costs red builds *and* slow
  builds.

---

## Verified not broken

| Entry point | Result |
|-------------|--------|
| `run_qa_heal.py` | 4/4 scenarios healed |
| `run_selenium_heal.py` | heals as before |
| `demo_show.py` | intact (`--reset` works) |
| all modules | import clean |

---

## Commits

| | |
|---|---|
| `c29ae06` | Harvest all DOM candidate features in a single execute_script |
| `741d7f9` | Make SelfHealingWebDriver a transparent driver proxy |
| `7146188` | Add selfheal.install() to patch Selenium lookups in place |
| `140d8b3` | Add page-object QA suite that is unaware of the healing layer |
| `dca76fc` | Add ?break=refactor fault that rots locators but keeps the app working |
| `e4643b5` | Add one-command baseline vs healed demonstration |
| `4c241ea` | Reset demo locator back to start-btn |
| `c3cd973` | Document the three integration levels and shorten the demo runbook |
| `96b7c07` | Refresh demo telemetry and golden fingerprint baseline |
| `a404f54` | Trim comments in the QA scenario suite |

Ordered so each commit builds on one that already works.

---

## Known gaps

Neither blocks the demo; both are worth knowing before the defence in case a
judge asks.

1. **`--relearn` merges instead of replacing.** The fingerprint registry has
   accumulated stale entries (`time-display`, `session-log`, `dur-focus`,
   `stat-pomodoros` — divs and spans that `scan_interactive` doesn't capture).
   Harmless today, but a stale fingerprint winning intent matching is a real
   failure mode.

2. **`source_healer.py` rewrites test source with regex.** Fine for the demo;
   nobody would let it near a production repo. The stronger answer is a
   **locator repository** the tests reference by logical name, with
   source-patching kept as an opt-in flag. That is also what industry tools
   (e.g. Healenium) do, so it defends better under questioning.

Also unaddressed from the original review: the tag gate in `healing_engine.py`
skips any candidate whose tag differs from the golden fingerprint, so a
`<button>` refactored into an `<a>` heals to nothing. A heavy score penalty
would be more forgiving than a hard skip.
