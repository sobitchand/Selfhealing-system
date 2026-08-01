# Applying the framework to any project

A companion to [`final_demo.md`](final_demo.md). That guide walks through one
polished demo. This one answers the question behind it:

> **Does the framework need a specific kind of project, or does it work on
> whatever you point it at?**

It works on whatever you point it at. The two projects below are deliberately at
opposite ends of the scale, and **neither is configured differently from the
other**. They exist as proof rather than assertion.

| | Tier 1 — `minimal/` | Tier 2 — `webapp/` |
|---|---|---|
| Files | one `.html` | `index.html` + `styles.css` + `app.js` |
| Identifiers | **no ids at all** — classes only | ids, names, classes, `data-testid` |
| JavaScript | none | external file, computes a value |
| Locator strategies | 4 (+ a nested lookup) | 6 |
| Heals on Day 2 | **5** | **6** |
| Setup difference | *none* | *none* |

**Everything below has been run and verified.** The outputs are real.

---

## Contents

1. [What the framework actually requires](#1-what-the-framework-actually-requires)
2. [Tier 1 — the smallest possible page](#2-tier-1--the-smallest-possible-page)
3. [Tier 2 — a conventional multi-file app](#3-tier-2--a-conventional-multi-file-app)
4. [What the two tiers prove](#4-what-the-two-tiers-prove)
5. [Designing the refusal case — read this one](#5-designing-the-refusal-case--read-this-one)
6. [Checklist for your own project](#6-checklist-for-your-own-project)
7. [The real boundaries](#7-the-real-boundaries)

---

## 1. What the framework actually requires

There is **no per-project configuration file**. The complete set of inputs is
three lines, two of which are ordinary Python:

```python
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))    # so `import selfheal` resolves
import selfheal

with selfheal.run(app="yourid", test="yourtest"):
    ...your existing, unmodified Selenium code...
```

That is the entire integration. Specifically, the framework does **not** need:

| It does not need | Why |
|---|---|
| A config file per project | the app id is the only per-project value, and it is a string you invent |
| Registration | `selfheal.run(app="x")` creates the record on the spot if `x` is new (`selfheal.py:62`) |
| ids on your elements | scoring normalises around whatever is absent (see §2) |
| A particular file layout | it reads the **live DOM**, never your source files (see §3) |
| A page object model, base class or decorator | it patches `WebDriver.find_element` itself |
| Any change to your existing test body | that is the point — the script is the control |

Registering with `cli.py register` is worth doing anyway, purely so the dashboard
shows a real name and URL instead of a bare id.

---

## 2. Tier 1 — the smallest possible page

`demo/minimal/page.html` — a heading, two paragraphs, a link. **No ids. No
stylesheet. No JavaScript. No form controls.**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Department Notice Board</title>
</head>
<body>
  <h1 class="board-title">Department Notice Board</h1>

  <div class="notice-list">
    <p class="notice-item">Library closes at 6 PM on Fridays.</p>
    <p class="notice-item">Lab reports are due on the 20th.</p>
  </div>

  <a class="board-link" href="#archive">Older notices</a>
</body>
</html>
```

### The test — `minimal/test_notices.py`

Four strategies, and the last lookup is **nested inside another element** — the
shape page objects are built from:

```python
heading = driver.find_element(By.CLASS_NAME, "board-title")
board   = driver.find_element(By.CSS_SELECTOR, ".notice-list")
first   = driver.find_element(By.XPATH, "//p[@class='notice-item']")
link    = driver.find_element(By.LINK_TEXT, "Older notices")

# Resolved against `board`, not the driver.
nested  = board.find_element(By.CLASS_NAME, "notice-item")
```

### Day 2 — every class renamed

| Day 1 | Day 2 |
|---|---|
| `board-title` | `page-heading` |
| `notice-list` | `announcements` |
| `notice-item` | `announcement` |
| `board-link` | `archive-link` |
| link text `Older notices` | `View archive` |

### Run it

```powershell
cd D:\Selfhealing-system\demo
.venv\Scripts\Activate

Copy-Item minimal\page.v1.html minimal\page.html -Force
python cli.py register --app notices --name "Notice Board" `
    --url "file:///D:/Selfhealing-system/demo/minimal/page.html" --source minimal/page.html

python minimal\test_notices.py                     # Day 1 — learns
Copy-Item minimal\page.v2.html minimal\page.html -Force
python minimal\test_notices.py --no-heal           # crashes
python minimal\test_notices.py --keep-baseline     # heals
```

**Day 1:**

```
PASS - heading: 'Department Notice Board'
       notice : 'Library closes at 6 PM on Fridays.'

📸 baseline recorded for 'notices' — no healing was required.
```

**Day 2 without the framework:**

```
selenium.common.exceptions.NoSuchElementException: Message: no such element:
Unable to locate element: {"method":"css selector","selector":".board-title"}
```

**Day 2 with the framework — same file, not one character changed:**

```
⏳ Heal queued for approval! 'h1.page-heading'    (Confidence: 79.76%)
⏳ Heal queued for approval! 'div.announcements'  (Confidence: 85.23%)
⏳ Heal queued for approval! 'p.announcement'     (Confidence: 88.7%)
⏳ Heal queued for approval! 'View archive'       (Confidence: 59.03%)
⏳ Heal queued for approval! 'p.announcement'     (Confidence: 88.7%)
PASS - heading: 'Department Notice Board'

🩹 self-healing [notices/read_board]: 5 heal(s), 0 cached re-use(s)
```

**Five heals on a page with no ids, no CSS and no JavaScript** — and the fifth is
the nested `board.find_element(...)`, proving healing follows page-object-style
code, not just top-level driver calls.

### Why a bare page still scores well

Because absence is not treated as mismatch. `healing_engine.py:208`:

> *Where an attribute is absent from both the Golden Fingerprint and the
> candidate element — that rule is excluded from the calculation and the
> remaining weights are normalized.*

So on this page R1 (text) and R2 (position) carry the score and the missing
attributes simply drop out of the denominator. It is also why `id='guests'` in
the Bistro demo scores 83.33% with `R1 0.0%` — an empty input has no text, and it
is not punished for that.

**The one honest caveat.** There is an identity gate at `healing_engine.py:303`:
R2 (position) and R4 (neighbours) describe *where* an element sits, not *which*
element it is, so a deleted element's neighbour could otherwise inherit its slot
and heal falsely. The gate blocks that — but it can only apply when the baseline
element carries *something* identifying: text, a class, a name, `aria-label`,
`placeholder`, an input type, or any `data-*`. A completely bare `<div>` with
none of those heals on structural evidence alone, which is the weakest case the
system supports. Every element in this tier has a class, so the gate applies.

---

## 3. Tier 2 — a conventional multi-file app

`demo/webapp/` — the layout almost every real project uses:

```
webapp\
    index.html      <- markup only
    styles.css      <- external stylesheet
    app.js          <- external script, computes the value under test
    test_fine.py    <- the Selenium test
```

An overdue-fine calculator: enter a borrower number, days overdue and a
membership tier; `app.js` computes what is owed.

### The test — six lookups, six strategies

```python
driver.find_element(By.ID, "member-id").send_keys("B-1042")
driver.find_element(By.NAME, "overdue-days").send_keys("6")
Select(driver.find_element(By.CSS_SELECTOR, "#tier")).select_by_visible_text("Standard")
driver.find_element(By.CLASS_NAME, "btn-calc").click()
driver.find_element(By.LINK_TEXT, "Fee policy")
amount = driver.find_element(By.XPATH, "//span[@id='total-fee']").text

assert amount == "30.00"      # 6 days x NPR 5.00 — computed by app.js
```

The assertion is on a **computed value**, not element presence. A heal is only
correct if it found the functionally right element — matching something with a
similar name would produce the wrong number.

### Day 2 — renamed across all three files

| The test asks for | Day 1 | Day 2 |
|---|---|---|
| `By.ID` `member-id` | `id="member-id"` | `id="borrower-code"` |
| `By.NAME` `overdue-days` | `name="overdue-days"` | `name="overdue-count"` |
| `By.CSS_SELECTOR` `#tier` | `id="tier"` | `id="membership-level"` |
| `By.CLASS_NAME` `btn-calc` | `class="btn-calc"` | `class="btn-primary"` |
| `By.LINK_TEXT` `Fee policy` | `Fee policy` | `Fine policy` |
| `By.XPATH` `//span[@id='total-fee']` | `id="total-fee"` | `id="amount-due"` |

`styles.css` and `app.js` were updated to match, so **the page still works** —
the fine still computes to 30.00. This matters: if `app.js` still called
`getElementById('total-fee')` the click handler would break, the assertion would
fail, and it would look like the healing framework was at fault.

### Run it

```powershell
Copy-Item webapp\index.v1.html webapp\index.html -Force
Copy-Item webapp\styles.v1.css webapp\styles.css  -Force
Copy-Item webapp\app.v1.js     webapp\app.js      -Force

python cli.py register --app library --name "City Library" `
    --url "file:///D:/Selfhealing-system/demo/webapp/index.html" --source webapp/index.html

python webapp\test_fine.py                    # Day 1 — learns

Copy-Item webapp\index.v2.html webapp\index.html -Force
Copy-Item webapp\styles.v2.css webapp\styles.css -Force
Copy-Item webapp\app.v2.js     webapp\app.js     -Force

python webapp\test_fine.py --no-heal          # crashes
python webapp\test_fine.py --keep-baseline    # heals
python webapp\test_fine.py --refuse           # safety gate
```

**Day 2 with the framework:**

```
⏳ Heal queued for approval! 'borrower-code'                  (Confidence: 90.0%)
⏳ Heal queued for approval! 'days-overdue'                   (Confidence: 90.0%)
⏳ Heal queued for approval! 'membership-level'               (Confidence: 85.11%)
⏳ Heal queued for approval! '[data-testid='calculate-fine']' (Confidence: 93.33%)
⏳ Heal queued for approval! 'Fine policy'                    (Confidence: 93.65%)
⏳ Heal queued for approval! 'amount-due'                     (Confidence: 100.0%)
PASS - amount due: NPR 30.00

🩹 self-healing [library/fine]: 6 heal(s), 0 cached re-use(s)
```

### The `data-testid` moment — point at this one

```powershell
python cli.py report --app library --test fine --format patch
```

```diff
- (By.ID, "member-id")
+ (By.ID, "borrower-code")

- (By.NAME, "overdue-days")
+ (By.ID, "days-overdue")

- (By.CSS_SELECTOR, "#tier")
+ (By.ID, "membership-level")

- (By.CLASS_NAME, "btn-calc")
+ (By.CSS_SELECTOR, "[data-testid='calculate-fine']")

- (By.LINK_TEXT, "Fee policy")
+ (By.LINK_TEXT, "Fine policy")

- (By.XPATH, "//span[@id='total-fee']")
+ (By.ID, "amount-due")
```

Four of six came back on a **more stable strategy** than they went in with. The
button is the one to talk about: it has no id, its class was renamed, but it
carries `data-testid="calculate-fine"` — and the recovery ranking prefers a
deliberate test anchor over a styling hook:

```
id → data-testid → data-test → data-qa → data-cy → name → aria-label
   → visible text → css class → xpath
```

> *"The system did not merely substitute a value. It ranked the live element's
> identifying attributes by stability and chose the one your team added on
> purpose for testing."*

---

## 4. What the two tiers prove

**Separate CSS and JS files change nothing — not one line of code path.** The
framework never opens your source files. Selenium sees the DOM *after* the
browser has fetched the stylesheet and executed the script, so by the time any
lookup happens, `<style>` inline and `styles.css` are indistinguishable.

The only place a file path appears anywhere is `--source`, and that is read-only,
purely so the dashboard can display what the developer changed.

Which means the same code path serves a one-file page, a three-file app, a
fifty-file project, or a React SPA behind a dev server. The only things that
matter are: **can Selenium load the URL**, and **did `find_element` fail**.

---

## 5. Designing the refusal case — read this one

The safety gate is the most important thing you demonstrate, and it is the
easiest to get wrong when building your own demo. This bit cost me a broken run
while writing this guide.

Before scoring any candidates, the engine resolves **which** tracked element a
broken locator was meant to find, by string-similarity against the baseline's
locators, and refuses outright below 40% (`healing_engine.py:124`). So your
"impossible" element must share **no vocabulary** with anything the test tracks:

| Probe | Similarity to nearest baseline locator | Outcome |
|---|---|---|
| `renew-membership-button` | **43.8%** vs `member-id` — shares *member* | passed the gate, got scored, **healed** |
| `printer-jam-warning` | 31.2% | **refused** ✓ |
| `wine-pairing-option` | 25.0% | **refused** ✓ |

The first one is instructive rather than embarrassing: the second gate still
engaged and downgraded it to a **CAUTIOUS HEAL** on a 9.3% margin, so it was
queued for human review and never silently applied. But it is not the clean
refusal you want on stage.

**Rule: name your refusal probe from a different domain entirely.** The page is
about library fines, so ask for a printer jam.

```
asking for id='printer-jam-warning' -- no such concept on this page
❌ Confidence below safety gate (0.0%). Manual intervention required.

CORRECT: the system refused rather than guessing.
```

---

## 6. Checklist for your own project

**Structure**

- [ ] Folder anywhere under `demo\`
- [ ] `sys.path.insert(0, os.path.join(HERE, ".."))` — add another `".."` per extra level
- [ ] `with selfheal.run(app="<id>", test="<id>"):` wrapping **both** driver creation and the test body
- [ ] The id in `selfheal.run(app=...)` matches `cli.py register --app ...` exactly

**Test design**

- [ ] Several **different** locator strategies — healing one id is unremarkable
- [ ] `find_element` (singular). `find_elements` does **not** heal by default, because an empty list is a legitimate answer
- [ ] Assert on a **computed value**, not element presence
- [ ] One lookup that cannot be healed — named from a different domain (§5)
- [ ] Optionally a `data-testid` element, for the ranking moment

**The Day-1 → Day-2 pair**

- [ ] Snapshot both files **before** refactoring (`.v1` / `.v2`)
- [ ] Day 2 renames exactly the hooks the test uses — renaming anything else dilutes the heal count
- [ ] Day 2 updates the **JavaScript and CSS** alongside the ids, or the page silently stops working and it looks like your framework broke
- [ ] The test file does **not** change between the two runs — it is the control
- [ ] Use `--keep-baseline` on the healing run, or a passing run re-learns the new page and the next run reports 0 heals

**Sanity check before presenting**

- [ ] Open the Day-2 page in a browser and confirm it still works
- [ ] Run the whole sequence once end to end
- [ ] Confirm the heal count is what you expect to say out loud

---

## 7. The real boundaries

Be precise about these rather than claiming universality — an examiner will
probe, and the honest answer is still strong.

| Works | Does not |
|---|---|
| Any **Python + Selenium** suite: pytest, unittest, behave, page objects, fixtures, `WebDriverWait` | Playwright, Cypress — different API and runtime |
| Any page: static, SPA, `file://`, `http://`, any file layout | Java / C# / Robot Framework Selenium |
| `find_element`, top-level and nested | `find_elements` (plural), unless explicitly enabled |
| Refactors that change ids, classes, names, link text, structure | A refactor that changes text *and* class *and* position *and* neighbours at once — correctly refuses, nothing left to match on |

The claim to make is **"works with any Python Selenium suite, without modifying
it"** — not "works with any framework". The first is true, demonstrable live, and
still the strongest adoption story in this space: `selfheal.run()` patches
Selenium's own lookup methods in-process, so every driver the suite creates heals
— including ones built deep inside a fixture or a third-party helper.

---

## Quick reference

```powershell
cd D:\Selfhealing-system\demo
.venv\Scripts\Activate
python reset_all.py

# ---- Tier 1: minimal ----
Copy-Item minimal\page.v1.html minimal\page.html -Force
python cli.py register --app notices --url "file:///D:/Selfhealing-system/demo/minimal/page.html" --source minimal/page.html
python minimal\test_notices.py
Copy-Item minimal\page.v2.html minimal\page.html -Force
python minimal\test_notices.py --no-heal
python minimal\test_notices.py --keep-baseline          # 5 heals

# ---- Tier 2: multi-file ----
Copy-Item webapp\index.v1.html webapp\index.html -Force
Copy-Item webapp\styles.v1.css webapp\styles.css -Force
Copy-Item webapp\app.v1.js webapp\app.js -Force
python cli.py register --app library --url "file:///D:/Selfhealing-system/demo/webapp/index.html" --source webapp/index.html
python webapp\test_fine.py
Copy-Item webapp\index.v2.html webapp\index.html -Force
Copy-Item webapp\styles.v2.css webapp\styles.css -Force
Copy-Item webapp\app.v2.js webapp\app.js -Force
python webapp\test_fine.py --no-heal
python webapp\test_fine.py --keep-baseline              # 6 heals
python webapp\test_fine.py --refuse                     # safety gate
python cli.py report --app library --test fine --format patch
```
