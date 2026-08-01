# Rule-Based Self-Healing System for Web Application Reliability

A deterministic, rule-based layer that keeps Selenium test suites running when a
developer renames the ids and classes they depend on — and explains every
decision it makes. No machine learning, no training data, no black box.

Implementation of the major project *"Rule-Based Self-Healing System for
Enhancing the Reliability of Web Applications"*.

---

## 1. The problem

A QA team writes a Selenium test. It passes. Next sprint a front-end developer
renames some ids and classes — a refactor no user would notice. Every locator in
the test breaks, the suite goes red, and someone spends an afternoon fixing
selectors by hand.

This system does three things about that:

| # | Capability | Touches your files? |
|---|---|---|
| 1 | **Keeps the failing run alive** — matches the intended element against a learned baseline and reroutes the lookup mid-flight | No |
| 2 | **Repairs the test script**, after a human approves the change | Only on approval |
| 3 | **Refuses to guess** when nothing on the page is a credible match | No |

The third matters as much as the first two. A healer that always finds
*something* is worse than no healer, because it turns a loud failure into a
silent wrong pass.

> The application under test is **never** modified. It is the target, not the
> patient. Only the *locator* is repaired — at runtime always, and in your test
> source only when a human clicks Approve.

---

## 2. Quick start

Python 3.10+, Google Chrome.

```powershell
cd demo
python -m venv .venv
.venv\Scripts\Activate
pip install -r requirements.txt
```

Run the demo that ships with it:

```powershell
python reset_all.py

python cli.py register --app bistro --name "Bistro Nova" `
    --url "file:///D:/Selfhealing-system/demo/storefront/app.html" `
    --source storefront/app.html

python storefront\test_booking.py                    # Day 1 — learns the baseline
Copy-Item storefront\app.v2.html storefront\app.html # the developer refactors
python storefront\test_booking.py --no-heal          # crashes, as any suite would
python storefront\test_booking.py --keep-baseline    # 5 heals, passes
```

Dashboard, in a second terminal:

```powershell
python -m streamlit run dashboard.py      # http://localhost:8501
```

Full walkthrough: [`final_demo.md`](final_demo.md).

---

## 3. The integration is one line

The layer is designed to bolt onto a suite that knows nothing about it:

```python
import selfheal

with selfheal.run(app="bistro", test="booking"):
    driver = webdriver.Chrome()
    driver.get(PAGE)
    driver.find_element(By.ID, "guests").send_keys("4")   # heals if this breaks
```

`selfheal.run()` patches `find_element` on Selenium's own `WebDriver` and
`WebElement` classes, so **every** driver the suite creates heals — including
ones built deep inside a fixture, a page-object factory or a third-party helper.
Verified consequences of patching the class rather than an instance:

| | Heals |
|---|---|
| `driver.find_element(...)` | yes |
| `element.find_element(...)` — nested, page-object style | yes |
| `WebDriverWait(...).until(EC.presence_of_element_located(...))` | yes — the condition calls `find_element` internally, so the heal beats the timeout |
| a driver created *before* the `with` block | yes |
| `driver.find_elements(...)` — plural | **no**, by default |
| anything after the block exits | no — stock Selenium is restored |

`find_elements` is off deliberately: an empty list is a legitimate answer ("no
error banners on screen"), so healing it would convert every true absence into a
false match. Enable with `selfheal.run(..., heal_find_elements=True)`.

An explicit wrapper (`automation_wrapper.SelfHealingWebDriver`) also exists for
suites that prefer substituting a driver object rather than patching.

Contract reference: [`testscript_guid.md`](testscript_guid.md).

---

## 4. How it decides

**Learning.** On a passing run, every locator the test *successfully resolved* is
recorded as a Golden Fingerprint — tag, id, visible text, classes, attributes,
XPath and neighbouring elements. Learning is bound to a passing run: if the test
raises, the capture is discarded rather than recording a broken page as the
reference state.

**Healing.** When a lookup raises `NoSuchElementException`, every candidate
element on the live page is scored against the fingerprint:

| Rule | Attribute | Weight |
|---|---|---|
| R1 | Inner text | 40% |
| R2 | XPath pattern (tree position) | 30% |
| R3 | CSS class | 20% |
| R4 | Neighbouring elements | 10% |

**The weights are normalised, not summed flat.** Where an attribute is absent
from *both* the fingerprint and the candidate, that rule is excluded and the
remaining weights are renormalised, so absence is never scored as a mismatch.
This is why an empty `<input>` with no visible text can still score 83% on
position, class and neighbours alone — and why the system works on pages with no
ids at all.

**Policy:**

| Score | Margin over runner-up | Outcome | Test sees an error? |
|---|---|---|---|
| ≥ 75% | clear | Automatic heal | No |
| ≥ 75% | ambiguous | Cautious heal — applied, flagged | No |
| 20–75% | — | Cautious heal — applied, flagged | No |
| < 20% | — | **Refused** — critical alert raised | **Yes** |

A 90% match is not trustworthy if the runner-up scores 88%; ambiguity is treated
as a reason for caution, not confidence.

**Locator Recovery.** When writing a repaired locator the engine ranks the live
element's attributes by expected stability and picks the best available:

```
id → data-testid → data-test → data-qa → data-cy → name → aria-label
   → visible text → css class → xpath
```

This is why a brittle XPath often comes back as a `By.ID`, and why the repaired
script is *more* resistant to the next refactor than the original.

---

## 5. Three safety gates

Worth knowing precisely, because they are what separate this from a fuzzy matcher.

**1. Intent gate (40%).** Before scoring anything, the engine resolves *which*
tracked element a broken locator meant, by string-similarity against the
baseline. Below 40% it refuses outright — it does not know what you were looking
for, so it will not guess. This is also why two different broken locators heal to
two different elements instead of both grabbing the top match.

**2. Identity gate.** R2 and R4 describe *where* an element sits, not *which*
element it is. When a tracked element is deleted, the neighbour that shifts into
its place inherits both — and could clear the safety gate on structural evidence
alone. The gate blocks that whenever the fingerprint carries anything
identifying (text, class, name, `aria-label`, `placeholder`, input type, any
`data-*`).

**3. Feedback loop.** Every heal is verified. A locator that fails to heal three
times running is locked and escalated, so there are no infinite recovery loops.

**Known bound, stated plainly:** an element that never existed but whose *name*
shares a token with a tracked one can clear the intent gate and be scored
structurally. Measured: `renew-membership-button` scores 43.8% against
`member-id` and heals; `printer-jam-warning` scores 31.2% and is refused. When it
happens the runner-up margin downgrades it to a cautious heal, so it is queued
for human review and never written to source — but it is a real bound, not an
impossibility.

---

## 6. What ships with it

Three demo applications, deliberately at different scales, **none of them
configured differently from the others**:

| Folder | Shape | Heals on Day 2 |
|---|---|---|
| `minimal/` | one HTML file, **no ids**, no CSS file, no JavaScript | 5 |
| `storefront/` | one self-contained HTML file (Bistro Nova) | 5 |
| `webapp/` | `index.html` + `styles.css` + `app.js` | 6 |

Each has `.v1` / `.v2` snapshots so the Day-1 → Day-2 refactor is repeatable.
Separate CSS and JS files change nothing: the framework reads the **live DOM**
after the browser has parsed and executed everything, and never opens your source
files.

---

## 7. Command line

```powershell
python cli.py register --app <id> --url <url> [--name ...] [--source ...]
python cli.py apps                       # registered applications and baselines
python cli.py learn     --app <id>       # capture a baseline by scanning the page
python cli.py baseline  --app <id>       # show the tracked elements
python cli.py check     --app <id>       # change impact, WITHOUT running the suite
python cli.py tests     --app <id>       # tests registered for this app
python cli.py runs      --app <id>       # run history with ids and heal counts
python cli.py report    --app <id> --test <id> --format md|patch|csv|json
```

`check` is the one to reach for after a developer edits the markup: it compares
the live page against the baseline and reports the impact before CI ever runs —
including the case where nothing broke.

`report` renders **one run**, defaulting to the latest. Pass `--test` or `--run`
to pick a different one; reporting an app whose most recent run was a refusal
will correctly produce an empty patch.

---

## 8. The application registry

Nothing in the framework names an application. An app is registered once, gets
its own namespaced baseline, and every later operation is scoped to it:

| Artefact | Path |
|---|---|
| Application record | `data/apps/<id>.json` |
| Golden Fingerprint baseline | `data/fingerprints/<id>_fingerprints.json` |
| Run records | `data/runs/r_<timestamp>_<id>_<test>.json` |
| Telemetry | `data/buckets/*.json`, each row stamped with `app_id` |

Two applications that both contain `#submit` keep entirely separate baselines and
cannot corrupt each other. The id in `selfheal.run(app=...)` is the key — it must
match what you pass to `cli.py`.

---

## 9. Dashboard

`python -m streamlit run dashboard.py` — nine tabs, read-only about healing:

| Tab | Shows |
|---|---|
| Applications | registered apps, baselines, tests, run history, report exports |
| Locator healing | every runtime heal: broken → repaired, R1–R4 breakdown, written reason |
| Approval Queue | pending source edits, with diff, Approve / Reject / Rollback |
| Change impact | drift between the live page and the baseline |
| Source write-back | fully automatic rewrites (opt-in path; inert under approval mode) |
| Infrastructure | disk / error-rate / service-health recovery actions |
| Alerts | refusals and threshold breaches |
| Analytics | locator stability, flaky detection, heal-time and cost analysis |
| Configuration | active application, thresholds, approval mode, fingerprint profiles |

The sidebar scopes every tab to one application, test or individual run.

---

## 10. Approval workflow

`APPROVAL_MODE_ENABLED = True` by default. Runtime healing keeps the run alive
and touches no files; the corresponding source edit is a queued *recommendation*.
Approving it patches the script, keeping a `.bak` for one-click rollback.

Silent rewriting of committed test code is the one behaviour a QA team cannot
audit, so the fully automatic path (`SOURCE_HEAL_ENABLED`, `source_healer.py`) is
opt-in and off.

---

## 11. Architecture

```
demo/
├── selfheal.py              # the integration: patches Selenium in-process
├── cli.py                   # register / learn / check / baseline / runs / report
├── dashboard.py             # Streamlit control panel
│
├── healing_engine.py        # R1–R4 scoring, thresholds, safety gates, infra rules
├── automation_wrapper.py    # find_element interceptor + explicit driver wrapper
├── fingerprint_manager.py   # capture Golden Fingerprints
├── learning_mode.py         # baseline bootstrap
├── dom_features.py          # xpath + neighbour extraction (shared by both modes)
├── drift_analyzer.py        # change impact without running tests
├── feedback.py              # verify → escalate, loop guard
├── handlers.py              # active (sync heal) vs passive (telemetry) paths
│
├── app_registry.py          # applications and their namespaced baselines
├── test_registry.py         # tests, their scripts and health
├── run_context.py           # one record per execution
├── reports.py               # md / patch / csv / json renderings of a run
│
├── approval_workflow.py     # queue → human review → patch → rollback
├── source_healer.py         # automatic write-back (opt-in, off by default)
│
├── store.py                 # per-bucket atomic JSON store (filelock + rolling window)
├── config.py                # paths, thresholds, buckets
├── config_manager.py        # dashboard-editable overrides
├── theme.py / assets/       # dashboard styling
│
├── demo_target_app.py       # tiny HTTP app, relaunched by the infrastructure healer
├── simulate_infra_heal.py   # drives the infrastructure healer with synthetic metrics
├── selfhealing/             # background metrics monitor
├── collector_server.py      # HTTP sink for the in-browser agent (passive path)
├── selfhealing_agent.js     # in-browser agent: JS errors, selector events
│
├── minimal/ storefront/ webapp/   # the three demo applications
├── data/                    # apps, fingerprints, runs, buckets, backups
└── qa_evidence/             # QA report and screenshots
```

### Storage

Each telemetry stream is its own file under `data/buckets/`, written through
`store.py`: temp file → `os.replace`, per-bucket `filelock` for cross-process
safety, and a rolling-window size cap. The approval queue uses the same
discipline, plus a retry — on Windows, `os.replace` fails if another process
(such as the polling dashboard) has the file open.

---

## 12. Boundaries

Stated plainly, because the honest scope is still a strong one.

| Works | Does not |
|---|---|
| Any **Python + Selenium** suite: pytest, unittest, behave, page objects, fixtures, `WebDriverWait` | Playwright, Cypress — different API and runtime |
| Any page: static, SPA, `file://`, `http://`, any file layout | Java / C# / Robot Framework Selenium |
| `find_element`, top-level and nested | `find_elements` unless explicitly enabled |
| Refactors changing ids, classes, names, link text, structure | A refactor changing text *and* class *and* position *and* neighbours at once — correctly refused, nothing left to match on |

The infrastructure monitor watches disk, error rate and service health and
applies rule-based recovery (log rotation, temp purge, process restart). In the
shipped demo the metric snapshots are **synthetic**; the recovery actions
themselves are real and performed by the same engine the live monitor drives.

---

## 13. Documentation

| File | Contents |
|---|---|
| [`final_demo.md`](final_demo.md) | the full demo, step by step, with real captured output |
| [`applying_to_any_project.md`](applying_to_any_project.md) | proof it works on a trivial page and a multi-file app |
| [`testscript_guid.md`](testscript_guid.md) | the test-script contract: imports, what heals, a template |
| [`QUICKSTART.md`](QUICKSTART.md) | shortest path from zero to a heal |

---

## 14. Tech stack

Python 3.10+ · Selenium WebDriver 4 · Streamlit + Plotly (dashboard) · pandas ·
filelock (cross-process atomic store) · JSON for all persistence.
**Rule-based only — no ML, no training data, no model to retrain.**
