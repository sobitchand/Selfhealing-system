# Quickstart — any page, any Selenium script

The framework contains no knowledge of any application. Register an app, run
your test once, edit the markup, run the same test again.

Everything below was executed end to end; the numbers are from a real run.

---

## 1. Write a page and a test

Any HTML file, any Selenium script. The only framework line is the `with`:

```python
import selfheal

with selfheal.run(app="shop", test="add_to_cart"):
    driver = make_driver()
    driver.get(PAGE)
    driver.find_element(By.ID, "qty").clear()
    driver.find_element(By.NAME, "quantity").send_keys("3")
    driver.find_element(By.CSS_SELECTOR, ".btn-main").click()
    driver.find_element(By.LINK_TEXT, "Proceed to checkout")
    count = driver.find_element(By.XPATH, "//span[@id='cart-count']").text
    assert count == "3"
```

Working example: `examples/shop/index.html` + `examples/shop/test_shop.py`.

## 2. Register the application

```bash
python cli.py register --app shop --name "Corner Shop" \
       --url file:///D:/Selfhealing-system/demo/examples/shop/index.html \
       --source examples/shop/index.html
```

Creates `data/apps/shop.json` and reserves `data/fingerprints/shop_fingerprints.json`.
`--source` is read-only; the framework never writes to your HTML.

## 3. Day 1 — run the test, the framework learns

```bash
python examples/shop/test_shop.py
```

```
PASS — cart shows 3
📸 baseline recorded for 'shop' — no healing was required.
```

Every locator the script resolved is now a Golden Fingerprint, keyed by the
locator itself:

```
id::qty
name::quantity
css selector::.btn-main
link text::Proceed to checkout
xpath:://span[@id='cart-count']
```

The baseline is written **only because the run passed**. A failing run leaves it
untouched, so a broken page can never become the reference state.

## 4. Edit the HTML by hand

Rename an id, rename a class, wrap something in a new `<div>`, add new elements.
Do not touch the test script.

## 5. Day 2 — same script, unchanged

```bash
python examples/shop/test_shop.py
```

```
⚠️ Element Missing: [id='qty']. Extracting DOM candidates...
⏳ Heal queued for approval! 'quantity-input' (Confidence: 90.33%)
⚠️ Element Missing: [css selector='.btn-main']. Extracting DOM candidates...
⏳ Heal queued for approval! 'btn-add-primary' (Confidence: 91.79%)
PASS — cart shows 3
🩹 self-healing [shop/add_to_cart]: 2 heal(s)
```

The test file is byte-identical. Each heal is logged with the repaired locator,
the rule breakdown, the reason and a copy-paste recommendation:

```
broken     : css selector='.btn-main'
repaired   : id -> btn-add-primary   (from the live element)
confidence : 91.79   margin over runner-up: 36.52
reason     : visible text matched; DOM position unchanged;
             CSS class partially matched (78%); neighbouring elements matched.
recommend  : Update the test script to use (By.ID, "btn-add-primary").
scores     : R1 100.0 | R2 87.11 | R3 78.26 | R4 100.0
```

## 6. `check` — what changed, and does it matter?

The question a developer actually asks. Runs **without** the test suite.

```bash
python cli.py check --app shop
```

Nothing broken — the case where the framework used to be silent:

```
INTACT: 5   MOVED: 0   CHANGED: 0   AMBIGUOUS: 0   MISSING: 0   NEW: 4

ADDED SINCE THE BASELINE RUN (4):
    <div> .newsletter Newsletter  Subscribe
    <h3> Newsletter
    <input> #email
    <button> #subscribe-btn Subscribe

VERDICT: SAFE — the page changed (4 element(s) added, 0 removed) but no
recorded locator is affected. The test suite is unaffected by this change.
```

Something recoverable:

```
[CHANGED] id='qty'
    'qty' no longer resolves, but the element is still on the page (90.3%
    match). It will be healed on the next run.
[MOVED] name='quantity'
    Still resolves, but its position changed
    (/html/body/div/input → /html/body/div/div/input).

VERDICT: RECOVERABLE — 3 tracked element(s) changed.
```

Something dangerous — an addition no exception would ever reveal:

```
VERDICT: AT RISK — 1 recorded locator(s) now match more than one element.
A test could pass against the wrong element.
```

## 7. Runs, tests and reports

Every execution is recorded as a run, stamped onto every heal and refusal it
produced. A test registers itself the first time it runs; its dependency list is
derived from the locators it actually resolved, not declared by hand.

```bash
python cli.py tests --app shop        # tests, health, last success/failure, locator count
python cli.py runs  --app shop        # run history
python cli.py report --run latest     # markdown hand-over report
python cli.py report --run latest --format patch
```

```
create_ticket            healing   runs=3 heals=4 locators=6
    script       : ...\examples\support\test_support.py
    last success : 2026-07-31T11:10:38+00:00
    last failure : never
```

```diff
--- examples/support/test_support.py
+++ examples/support/test_support.py (suggested)

- (By.ID, "full-name")
+ (By.ID, "customer-name")

- (By.CSS_SELECTOR, ".btn-submit")
+ (By.ID, "submit-ticket")
```

## 8. Dashboard

```bash
python -m streamlit run dashboard.py
```

The sidebar scopes the whole page: **Application ▸ Test ▸ Run**. Tabs:

- **Applications** — registry, URL/source file, fingerprint status, when the
  baseline was recorded, tests per app with health and last success/failure,
  run history, and export (Markdown / CSV / JSON / suggested patch).
- **Locator healing** — broken locator, new runtime locator, confidence,
  R1–R4 breakdown, and an expander per heal with the reason, the margin over the
  next-best candidate, and the QA recommendation.
- **Change impact** — the latest `check` verdict and its history.
- **Approval Queue**, **Alerts**, **Analytics**, **Configuration**.

## Commands

| Command | Purpose |
|---|---|
| `python cli.py register --app <id> --url <url>` | register an application |
| `python cli.py apps` | list registered applications |
| `python cli.py check --app <id>` | change-impact analysis vs the baseline |
| `python cli.py baseline --app <id>` | show the recorded Golden Fingerprints |
| `python cli.py tests --app <id>` | tests, health, dependencies |
| `python cli.py runs [--app <id>]` | run history |
| `python cli.py report --run latest [--format md\|csv\|json\|patch]` | export a run |
| `python cli.py learn --app <id> [--force]` | capture a baseline by page scan (fallback when no test exists yet) |

## Where things are stored

```
data/apps/<app>.json                          application registry
data/tests/<app>/<test>.json                  test registry + locator dependencies
data/runs/<run_id>.json                       one record per execution
data/fingerprints/<app>_fingerprints.json     Golden Fingerprints
data/fingerprints/<app>_snapshot.json         Day-1 page snapshot (change detection)
data/buckets/*.json                           heals, alerts, drift telemetry
```

## What the framework never does

- It never modifies the application's HTML, CSS or JavaScript.
- It never edits your test script. `SOURCE_HEAL_ENABLED` is off; repairs are
  queued for review in the dashboard's Approval Queue.
- It never guesses. With no baseline entry for a locator, or with a best match
  below the safety gate, it refuses and re-raises the original exception.
