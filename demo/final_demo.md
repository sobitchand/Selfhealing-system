# Self-Healing Test Automation — Demo Guide

A complete, end-to-end demonstration you can run in front of judges, and a template
for applying the framework to any other project.

The demo application here is **Bistro Nova**, a table-reservation page. It lives in
`demo/storefront/` — a plain folder with no special status, which is the point: the
framework has no knowledge of it, and nothing about it was configured in advance.

**Everything in this guide has been run and verified.** The outputs shown are real.

---

## Contents

1. [What you are demonstrating](#1-what-you-are-demonstrating)
2. [Project layout](#2-project-layout)
3. [The application — `app.html` (Day 1)](#3-the-application--apphtml-day-1)
4. [The test — `test_booking.py`](#4-the-test--test_bookingpy)
5. [The refactored application (Day 2)](#5-the-refactored-application-day-2)
6. [Run the demo — step by step](#6-run-the-demo--step-by-step)
7. [The dashboard, tab by tab](#7-the-dashboard-tab-by-tab)
8. [Reports — turning a run into an artefact](#8-reports--turning-a-run-into-an-artefact)
9. [How the decision engine works](#9-how-the-decision-engine-works)
10. [Reset between rehearsals](#10-reset-between-rehearsals)
11. [Applying this to a different project](#11-applying-this-to-a-different-project)
12. [Troubleshooting](#12-troubleshooting)
13. [Anticipated questions](#13-anticipated-questions)

---

## 1. What you are demonstrating

A QA team writes a Selenium test. It passes. Next sprint a front-end developer
renames ids and classes — a refactor no user would notice. Every locator in the
test breaks and the suite goes red. Someone spends an afternoon fixing selectors
by hand.

This framework does three things about that:

| # | Capability | Where you see it |
|---|---|---|
| 1 | **Keeps the failing run alive** by matching the intended element against a learned baseline and rerouting the lookup mid-flight | Step 6.7 |
| 2 | **Repairs the test script itself**, after a human approves it | Steps 6.9–6.10 |
| 3 | **Refuses to guess** when nothing on the page is a credible match | Step 6.11 |

The third is as important as the first two. A healer that always finds *something*
is worse than no healer, because it turns a loud failure into a silent wrong pass.

---

## 2. Project layout

```
D:\Selfhealing-system\demo\
    selfheal.py              <- the framework (you do not touch this)
    cli.py
    dashboard.py
    reset_all.py
    storefront\              <- YOUR project. An ordinary folder.
        app.html             <- the application under test
        test_booking.py      <- the Selenium test
```

Two files. No config file, no plugin registration, no framework-specific base class.

Open a terminal for everything below:

```powershell
cd D:\Selfhealing-system\demo
.venv\Scripts\Activate
```

---

## 3. The application — `app.html` (Day 1)

`D:\Selfhealing-system\demo\storefront\app.html`

An ordinary self-contained page. Enter guests, pick a sitting, confirm — it shows
the deposit due. Nothing in it refers to the healing framework.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Bistro Nova — Reserve a table</title>
  <style>
    * { box-sizing: border-box; }
    body { margin:0; font-family: system-ui, "Segoe UI", Arial, sans-serif;
           background:#f6f5f2; color:#22201d; }
    header { background:#1f4d3a; color:#fff; padding:18px 28px; }
    header h1 { margin:0; font-size:19px; letter-spacing:.3px; }
    main { max-width:520px; margin:34px auto; padding:0 16px; }
    .card { background:#fff; border:1px solid #e6e3dc; border-radius:10px;
            padding:26px 28px; box-shadow:0 1px 3px rgba(30,25,20,.06); }
    h2 { margin:0 0 4px; font-size:16px; }
    .muted { color:#6d675f; font-size:13px; margin:0 0 18px; }
    .fee-line { font-size:14px; margin:0 0 20px; }
    .field { margin-bottom:16px; }
    .field label { display:block; font-size:12px; text-transform:uppercase;
                   letter-spacing:.6px; color:#6d675f; margin-bottom:6px; }
    .field-box { width:100%; padding:10px 12px; font-size:15px;
                 border:1px solid #d5d0c7; border-radius:6px; background:#fff; }
    .btn { padding:11px 18px; font-size:15px; border:0; border-radius:6px; cursor:pointer; }
    .btn-reserve { background:#1f4d3a; color:#fff; width:100%; }
    .links { margin-top:18px; }
    .link { color:#1f4d3a; font-size:13px; text-decoration:none; }
    #notice { min-height:19px; font-size:13px; color:#1c6b3f; margin:14px 0 0; }
  </style>
</head>
<body>
  <header><h1>Bistro Nova</h1></header>
  <main>
    <div class="card">
      <h2>Reserve a table</h2>
      <p class="muted">Deposit NPR 250.00 per guest</p>
      <p class="fee-line">Deposit due: NPR <span id="fee">0.00</span></p>

      <div class="field">
        <label for="guests">Guests</label>
        <input id="guests" name="party-size" type="number" class="field-box" placeholder="0">
      </div>

      <div class="field">
        <label for="slot">Sitting</label>
        <select id="slot" name="slot" class="field-box">
          <option value="">Choose a sitting…</option>
          <option value="18:00">6:00 PM</option>
          <option value="19:30">7:30 PM</option>
        </select>
      </div>

      <button class="btn btn-reserve">Confirm booking</button>
      <p id="notice"></p>

      <div class="links">
        <a class="link" href="#bookings">My reservations</a>
      </div>
    </div>
  </main>

  <script>
    var PER_GUEST = 250.00;
    var SURCHARGE = { "18:00": 0, "19:30": 200 };
    function fmt(n) {
      return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    document.querySelector('.btn-reserve').addEventListener('click', function () {
      var guests = parseInt(document.getElementById('guests').value, 10);
      var sel = document.getElementById('slot');
      if (!guests || guests <= 0 || !sel.value) {
        document.getElementById('notice').textContent = 'Enter guests and pick a sitting.';
        return;
      }
      var fee = guests * PER_GUEST + SURCHARGE[sel.value];
      document.getElementById('fee').textContent = fmt(fee);
      document.getElementById('notice').textContent =
        'Table booked — ' + guests + ' guest(s), ' + sel.options[sel.selectedIndex].text + '.';
    });
  </script>
</body>
</html>
```

**Sanity check:** open it in a browser, enter `4`, pick **7:30 PM**, click
**Confirm booking**. It must read **1,200.00** (4 × 250 + 200 surcharge). If it
does not, the page is broken and no test result below will mean anything.

---

## 4. The test — `test_booking.py`

`D:\Selfhealing-system\demo\storefront\test_booking.py`

An ordinary Selenium script. **The only framework integration is one line:**
`with selfheal.run(...)`. The five lookups deliberately use five *different*
locator strategies, so the demo covers every kind of breakage at once.

```python
"""
Bistro Nova reservation test -- one ordinary Selenium script.

The only framework integration is the `with selfheal.run(...)` line. The test
body never changes: not between the learning run and the healing run, and not
when the developer renames every id and class in app.html. That is the point --
the script is the control, and the only variable is whether the healing layer
is installed.

    python storefront/test_booking.py                   learn / heal (normal)
    python storefront/test_booking.py --keep-baseline   heal without overwriting
                                                        the baseline
    python storefront/test_booking.py --no-heal         plain Selenium, no framework
    python storefront/test_booking.py --headed          watch it in a browser
    python storefront/test_booking.py --refuse          ask for an element that
                                                        exists nowhere
"""

import glob
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException

# One level up from storefront/ is the framework root. This single line is the
# only thing that has to change if the project lives at a different depth.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import selfheal

PAGE = "file:///" + os.path.join(HERE, "app.html").replace("\\", "/")

HEAL = "--no-heal" not in sys.argv
LEARN = "--keep-baseline" not in sys.argv
HEADED = "--headed" in sys.argv
REFUSE = "--refuse" in sys.argv


def make_driver():
    options = webdriver.ChromeOptions()
    if not HEADED:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    cached = sorted(glob.glob(os.path.expanduser(
        "~/.wdm/drivers/chromedriver/*/*/chromedriver-win64/chromedriver.exe")))
    if cached:
        return webdriver.Chrome(service=Service(cached[-1]), options=options)
    from webdriver_manager.chrome import ChromeDriverManager
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def book_a_table(driver):
    """The test itself. Five lookups, five different locator strategies."""
    driver.get(PAGE)

    driver.find_element(By.ID, "guests").send_keys("4")
    Select(driver.find_element(By.NAME, "slot")).select_by_visible_text("7:30 PM")
    driver.find_element(By.CSS_SELECTOR, ".btn-reserve").click()
    driver.find_element(By.LINK_TEXT, "My reservations")
    deposit = driver.find_element(By.XPATH, "//span[@id='fee']").text

    assert deposit == "1,200.00", f"expected deposit 1,200.00, got {deposit!r}"
    print(f"PASS - deposit due: NPR {deposit}")


def safety_gate(driver):
    """Ask for something with no analogue on the page. The best candidate scores
    below CONFIDENCE_THRESHOLD_LOW, so the engine must refuse rather than guess."""
    driver.get(PAGE)
    print("asking for id='wine-pairing-option' -- no such concept exists on this page")
    try:
        driver.find_element(By.ID, "wine-pairing-option")
        print("UNEXPECTED: an element was returned. The system guessed!")
    except NoSuchElementException as e:
        print("\nCORRECT: the system refused rather than guessing.")
        print(f"   {str(e).splitlines()[0][:140]}")


def main():
    body = safety_gate if REFUSE else book_a_table

    if not HEAL:
        print("mode: plain Selenium, NO self-healing")
        driver = make_driver()
        try:
            body(driver)
        finally:
            driver.quit()
        return

    print(f"mode: self-healing ON, learning {'OFF (baseline pinned)' if not LEARN else 'ON'}")
    with selfheal.run(app="bistro", test="refusal" if REFUSE else "booking",
                      learn=False if REFUSE else LEARN):
        driver = make_driver()
        try:
            body(driver)
        finally:
            driver.quit()


if __name__ == "__main__":
    main()
```

### The five locators

| # | Strategy | Locator | Why it is in the demo |
|---|---|---|---|
| 1 | `By.ID` | `guests` | the most common strategy in real suites |
| 2 | `By.NAME` | `slot` | form-field convention |
| 3 | `By.CSS_SELECTOR` | `.btn-reserve` | styling hook, renamed on every redesign |
| 4 | `By.LINK_TEXT` | `My reservations` | copy changes constantly |
| 5 | `By.XPATH` | `//span[@id='fee']` | the most brittle strategy of all |

### The flags

| Flag | Effect |
|---|---|
| *(none)* | healing on, learning on — normal Day-1 run |
| `--keep-baseline` | healing on, learning **off** — use for Day 2, so the run is repeatable |
| `--no-heal` | plain Selenium, framework never loaded — the control |
| `--headed` | show the browser instead of running headless |
| `--refuse` | ask for an element that exists nowhere, to show the safety gate |

---

## 5. The refactored application (Day 2)

At Step 6.5 you replace the **entire contents** of `app.html` with the version
below. Same file — you are simulating a developer committing a refactor.

Every id, class, and link text the test depends on has changed. To a human the
page is identical.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Bistro Nova — Reserve a table</title>
  <style>
    * { box-sizing: border-box; }
    body { margin:0; font-family: system-ui, "Segoe UI", Arial, sans-serif;
           background:#f6f5f2; color:#22201d; }
    header { background:#1f4d3a; color:#fff; padding:18px 28px; }
    header h1 { margin:0; font-size:19px; letter-spacing:.3px; }
    main { max-width:520px; margin:34px auto; padding:0 16px; }
    .card { background:#fff; border:1px solid #e6e3dc; border-radius:10px;
            padding:26px 28px; box-shadow:0 1px 3px rgba(30,25,20,.06); }
    h2 { margin:0 0 4px; font-size:16px; }
    .muted { color:#6d675f; font-size:13px; margin:0 0 18px; }
    .fee-line { font-size:14px; margin:0 0 20px; }
    .field { margin-bottom:16px; }
    .field label { display:block; font-size:12px; text-transform:uppercase;
                   letter-spacing:.6px; color:#6d675f; margin-bottom:6px; }
    .input-field { width:100%; padding:10px 12px; font-size:15px;
                 border:1px solid #d5d0c7; border-radius:6px; background:#fff; }
    .btn { padding:11px 18px; font-size:15px; border:0; border-radius:6px; cursor:pointer; }
    .btn-solid { background:#1f4d3a; color:#fff; width:100%; }
    .links { margin-top:18px; }
    .link { color:#1f4d3a; font-size:13px; text-decoration:none; }
    #notice { min-height:19px; font-size:13px; color:#1c6b3f; margin:14px 0 0; }
  </style>
</head>
<body>
  <header><h1>Bistro Nova</h1></header>
  <main>
    <div class="card">
      <h2>Reserve a table</h2>
      <p class="muted">Deposit NPR 250.00 per guest</p>
      <p class="fee-line">Deposit due: NPR <span id="deposit-total">0.00</span></p>

      <div class="field">
        <label for="party-count">Guests</label>
        <input id="party-count" name="guest-count" type="number" class="input-field" placeholder="0">
      </div>

      <div class="field">
        <label for="time-slot">Sitting</label>
        <select id="time-slot" name="booking-slot" class="input-field">
          <option value="">Choose a sitting…</option>
          <option value="18:00">6:00 PM</option>
          <option value="19:30">7:30 PM</option>
        </select>
      </div>

      <button id="confirm-booking" class="btn btn-solid">Confirm booking</button>
      <p id="notice"></p>

      <div class="links">
        <a class="link" href="#bookings">View my bookings</a>
      </div>
    </div>
  </main>

  <script>
    var PER_GUEST = 250.00;
    var SURCHARGE = { "18:00": 0, "19:30": 200 };
    function fmt(n) {
      return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    document.getElementById('confirm-booking').addEventListener('click', function () {
      var guests = parseInt(document.getElementById('party-count').value, 10);
      var sel = document.getElementById('time-slot');
      if (!guests || guests <= 0 || !sel.value) {
        document.getElementById('notice').textContent = 'Enter guests and pick a sitting.';
        return;
      }
      var fee = guests * PER_GUEST + SURCHARGE[sel.value];
      document.getElementById('deposit-total').textContent = fmt(fee);
      document.getElementById('notice').textContent =
        'Table booked — ' + guests + ' guest(s), ' + sel.options[sel.selectedIndex].text + '.';
    });
  </script>
</body>
</html>
```

### What changed — say this out loud to the judges

| The test asks for | Day 1 | Day 2 |
|---|---|---|
| `By.ID` `guests` | `id="guests"` | `id="party-count"` |
| `By.NAME` `slot` | `name="slot"` | `name="booking-slot"` |
| `By.CSS_SELECTOR` `.btn-reserve` | `class="btn-reserve"` | `id="confirm-booking" class="btn-solid"` |
| `By.LINK_TEXT` `My reservations` | `My reservations` | `View my bookings` |
| `By.XPATH` `//span[@id='fee']` | `id="fee"` | `id="deposit-total"` |

The CSS and JavaScript were updated to match, so **the page still works**. This
matters: if the JavaScript still pointed at `.btn-reserve`, the click handler
would never attach, the deposit would stay `0.00`, and the test would fail for a
reason that has nothing to do with healing.

> **Before running Step 6.6, open the refactored page in a browser and confirm it
> still totals 1,200.00.** If it does not, the app is broken, not the framework.

---

## 6. Run the demo — step by step

### 6.0 — Start clean

```powershell
python reset_all.py
```

```
=== RESET ===
  cleared bucket: alerts.json
  cleared bucket: approval_queue.json
  ...
  emptied data/apps/
  emptied data/fingerprints/
```

Every dashboard tab is now empty. Everything that appears from here on is
produced by this demo.

### 6.1 — Keep a Day-1 snapshot of both files

**Do not skip this.** Approving heals edits your test script, so you need copies
of both files to rehearse again.

```powershell
Copy-Item storefront\app.html storefront\app.v1.html
Copy-Item storefront\test_booking.py storefront\test_booking.v1.py
```

### 6.2 — Start the dashboard

Second terminal, leave it running:

```powershell
cd D:\Selfhealing-system\demo
.venv\Scripts\Activate
streamlit run dashboard.py
```

Open <http://localhost:8501>, then press **Ctrl+Shift+R**. Press **R** to refresh
after each step below.

### 6.3 — Register the application

```powershell
python cli.py register --app bistro --name "Bistro Nova" --url "file:///D:/Selfhealing-system/demo/storefront/app.html" --source storefront/app.html
```

```
Registered 'bistro' (Bistro Nova)
  url:       file:///D:/Selfhealing-system/demo/storefront/app.html
  baseline:  D:\Selfhealing-system\demo\data\fingerprints\bistro_fingerprints.json
  source:    storefront/app.html
```

➡ **Applications** now has one row. Baseline: *not yet recorded*.

> Registering is optional — `selfheal.run(app="bistro")` would create the record
> automatically. Do it explicitly so the dashboard shows a real name and URL.

### 6.4 — Day 1: the test passes, the system learns

```powershell
python storefront\test_booking.py
```

```
mode: self-healing ON, learning ON
▶ run r_20260801T..._bistro_booking  [bistro / booking]
PASS - deposit due: NPR 1,200.00

📸 baseline recorded for 'bistro' — no healing was required.
```

Every lookup that **succeeded** was fingerprinted: tag, id, classes, visible
text, attributes, XPath, and neighbouring elements. Because it was learned from a
*passing* run, the system knows these locators genuinely work — it never learns
from a broken page.

Inspect what it learned:

```powershell
python cli.py baseline --app bistro
```

➡ **Applications** now shows *6 element(s)* and one successful run.

### 6.5 — Day 2: the developer refactors

Replace the entire contents of `storefront\app.html` with the Day-2 version from
[section 5](#5-the-refactored-application-day-2). Open it in a browser and
confirm it still totals **1,200.00**.

**Nothing about the test changes. Not one character.**

### 6.6 — First, what happens without the framework

```powershell
python storefront\test_booking.py --no-heal
```

```
mode: plain Selenium, NO self-healing
...
selenium.common.exceptions.NoSuchElementException: Message: no such element:
Unable to locate element: {"method":"css selector","selector":"[id="guests"]"}
```

> *"This is what happens in every QA team today. One renamed id and the suite is
> red — and it dies on the first lookup, so you do not even learn how much else
> is broken."*

### 6.7 — Now the same test, with the framework

```powershell
python storefront\test_booking.py --keep-baseline
```

```
mode: self-healing ON, learning OFF (baseline pinned)
⚠️ Element Missing: [id='guests']. Extracting DOM candidates...
🔬 Scanned 23 structural layout candidates. Evaluating heuristics...
⏳ Heal queued for approval! 'party-count' (Confidence: 83.33%)
⏳ Heal queued for approval! 'time-slot' (Confidence: 80.7%)
⏳ Heal queued for approval! 'confirm-booking' (Confidence: 92.86%)
⏳ Heal queued for approval! 'View my bookings' (Confidence: 69.89%)
⏳ Heal queued for approval! 'deposit-total' (Confidence: 100.0%)
PASS - deposit due: NPR 1,200.00

🩹 self-healing [bistro/booking]: 5 heal(s), 0 cached re-use(s)
```

**Byte-identical test file to Step 6.6. Five locator strategies. It passes.**

It must say **5 heal(s)**. Fewer means the Day-2 paste was incomplete — see
[Troubleshooting](#12-troubleshooting).

➡ **Locator healing** and **Approval Queue** both fill.

> `--keep-baseline` pins the baseline to the Day-1 page so this step is
> repeatable. Without it, a passing run re-learns from the refactored page and a
> second run reports **0 heals** — which is exactly what you do not want to
> happen live.

### 6.8 — Two separate things just happened

This is the distinction to make explicit:

| | What it did | Did it touch your files? |
|---|---|---|
| **Runtime heal** | rerouted each failing lookup mid-flight, so the run finished green | No |
| **Queued recommendation** | recorded the proposed source edit for a human to review | No |

The script on disk is still unchanged. Your system is configured so it will
**never** silently rewrite committed test code (`APPROVAL_MODE_ENABLED = True`).

### 6.9 — Approve, and the system repairs the test script

Dashboard → **Approval Queue**. Five entries, each with the old locator, the
proposed replacement, the confidence, and a diff.

Click **✅ Approve** on all five.

Now look at the file:

```powershell
Compare-Object (Get-Content storefront\test_booking.v1.py) (Get-Content storefront\test_booking.py)
```

| Before | After | |
|---|---|---|
| `By.ID, "guests"` | `By.ID, "party-count"` | |
| `By.NAME, "slot"` | `By.ID, "time-slot"` | **strategy upgraded** |
| `By.CSS_SELECTOR, ".btn-reserve"` | `By.ID, "confirm-booking"` | **strategy upgraded** |
| `By.LINK_TEXT, "My reservations"` | `By.LINK_TEXT, "View my bookings"` | |
| `By.XPATH, "//span[@id='fee']"` | `By.ID, "deposit-total"` | **strategy upgraded** |

> If your editor still shows the old text, it is displaying a stale buffer.
> Close and reopen the file.

Point at the three rows where **`By.` itself changed**. The system did not merely
substitute a value — it ranked the live element's identifying attributes by
stability and wrote back the most durable one available. A brittle XPath and a
CSS class both became ids.

### 6.10 — The moment

```powershell
python storefront\test_booking.py --no-heal
```

```
mode: plain Selenium, NO self-healing
PASS - deposit due: NPR 1,200.00
```

> *"Plain Selenium. The healing layer is not even imported. The same script that
> crashed in Step 6.6 now passes — because the system repaired it. We never
> edited a line."*

### 6.11 — It refuses when it should

```powershell
python storefront\test_booking.py --refuse
```

```
asking for id='wine-pairing-option' -- no such concept exists on this page
⚠️ Element Missing: [id='wine-pairing-option']. Extracting DOM candidates...
🔬 Scanned 23 structural layout candidates. Evaluating heuristics...
❌ Confidence below safety gate (0.0%). Manual intervention required.

CORRECT: the system refused rather than guessing.
```

➡ **Alerts** fills.

> *"A healer that always finds something is worse than no healer — it turns a
> loud failure into a silent wrong pass. Below 20% confidence ours stops and
> says so."*

### 6.12 — Change impact, without running any test

```powershell
python cli.py check --app bistro
```

```
  INTACT: 1   MOVED: 0   CHANGED: 5   AMBIGUOUS: 0   MISSING: 0   NEW: 6   REMOVED: 6

  [CHANGED] id='guests'
      'guests' no longer resolves, but the element is still on the page (83.3% match).
      It will be healed on the next run. DOM position unchanged; ...

  VERDICT: RECOVERABLE — 5 tracked element(s) changed.
```

➡ **Change impact** fills.

> *"A developer can ask 'what will my refactor break?' before CI ever runs — and
> a change that breaks nothing produces an answer instead of silence."*

### 6.13 — Infrastructure healing

```powershell
python simulate_infra_heal.py
```

```
[Combined phase 2/4: disk stress]
⚙️ Infrastructure heal: Log Rotation & Temp File Purge — Purged 0 temp file(s), ...
[Combined phase 3/4: error rate spike]
⚙️ Infrastructure heal: Worker Pool Error Counter Reset — Reset error counter sliding window
[Combined phase 4/4: service down]
⚙️ Infrastructure heal: Service Restart Attempt — relaunched on port 8000 — verified responding
```

➡ **Infrastructure** fills with one row per heal type, and the sidebar's Live
Metrics start moving.

Only the metric snapshots are synthetic. Each recovery row is produced by the
same `DynamicInfrastructureHealer` the live metrics monitor drives — the script
writes the snapshots, then runs the real engine over them.

> *"Locators are only half of it. The monitor watches disk, error rate and
> service health, and fires rule-based recovery — log rotation, temp purge,
> process restart."*

The service-down scenario genuinely restarts whatever is listening on
`TARGET_APP_PORT` (8000) and launches `demo_target_app.py` in its place. If that
port is in use by something you care about:

```powershell
python simulate_infra_heal.py --no-restart      # disk + error rate only
```

| Command | Rows produced |
|---|---|
| `python simulate_infra_heal.py` | all three heal types, healed phase by phase |
| `python simulate_infra_heal.py disk` \| `error` \| `down` | one scenario on its own |
| `python simulate_infra_heal.py all` | each scenario separately |
| `--no-restart` | skips the scenario that restarts port 8000 |

### 6.14 — Reports

```powershell
python cli.py runs  --app bistro
python cli.py tests --app bistro
python cli.py report --app bistro --test booking --format md
python cli.py report --app bistro --test booking --format patch
```

> **`--test booking` is not optional here.** Without it, `report` renders the
> *latest* run — which at this point in the demo is the refusal from 6.11, a run
> with zero heals. `--format patch` would print nothing at all and look broken.
> [Section 8](#8-reports--turning-a-run-into-an-artefact) explains the targeting
> rules in full.

---

## 7. The dashboard, tab by tab

| Tab | What it shows | Fills at step |
|---|---|---|
| **Applications** | Every registered app, its baseline element count, its tests, run history, pass/fail health | 6.3, 6.4 |
| **Locator healing** | Every runtime heal: broken locator → repaired locator, confidence, the R1–R4 score breakdown, and a written reason | 6.7 |
| **Approval Queue** | Pending source edits with Approve / Reject / Rollback | 6.7 → 6.9 |
| **Change impact** | Drift between the live page and the baseline, without running tests | 6.12 |
| **Source write-back** | Fully automatic rewrites (a separate, opt-in path) | stays empty — see below |
| **Infrastructure** | Disk / error-rate / service-health telemetry and recovery actions | 6.13 |
| **Alerts** | Refusals and threshold breaches | 6.11 |
| **Analytics** | Locator stability scores, flaky detection, heal-time and cost analysis | after 6.7 |
| **Configuration** | Active application, confidence thresholds, approval mode, fingerprint profiles | anytime |

### The Configuration tab

It follows the application registry: the active app decides which baseline every
heal is scored against, and the tab reads and writes that rather than a
standalone URL setting. Three buttons there run the same commands as the
terminal steps above — **Re-learn baseline** (`cli.py learn --force`), **Run
change-impact check** (`cli.py check`, step 6.12) and **Simulate infrastructure
stress** (step 6.13) — so you can drive 6.12 and 6.13 without leaving the
browser. Output is printed verbatim and the auto-refresh pauses while you read
it.

### Reading the Locator healing tab

Each heal shows four component scores — the rules that decided the match:

| Rule | Weight | What it compares |
|---|---|---|
| **R1** | 40% | visible text |
| **R2** | 30% | position in the DOM tree |
| **R3** | 20% | CSS class overlap |
| **R4** | 10% | neighbouring elements |

Worked example from this demo — `xpath='//span[@id='fee']'` → `deposit-total` at
**100%**, with `R1 100 · R2 100 · R3 0 · R4 0`. The text and tree position were
identical; the class contributed nothing because the span has no class. Contrast
`id='guests'` → `party-count` at **83.3%** with `R1 0`: an empty input has no
visible text, so the match rested on position, class and neighbours.

That breakdown is why the system can defend every decision it makes.

### Why "Source write-back" stays empty

There are two paths that can edit your test file:

| Path | Trigger | Config required |
|---|---|---|
| **Approval Queue** *(what this demo uses)* | a human clicks Approve | `APPROVAL_MODE_ENABLED = True` — the default |
| **Source write-back** | fully automatic on a high-confidence heal | `APPROVAL_MODE_ENABLED = False` **and** `SOURCE_HEAL_ENABLED = True` |

In approval mode the second path is deliberately inert, so its tab stays empty
and your approvals appear under **Approval Queue**. Nothing is broken.

---

## 8. Reports — turning a run into an artefact

A dashboard is only useful while it is on screen. A QA engineer attaching a heal
to a Jira ticket, or a reviewer asking why last night's build went green, needs
the same information as a file. Every run already writes a self-contained record
under `data/runs/`, so a report is a *rendering* of that record — not a second
source of truth that could disagree with the dashboard.

```powershell
python cli.py report --app <id> [--test <id>] [--run <run-id>] --format md|patch|csv|json [--out FILE]
```

### 8.1 — Which run gets reported

This is the part that trips people up. `--app` alone does **not** mean "everything
this app ever did". `report` renders exactly **one run**, and by default that is
the most recent one:

| Flags | Run selected |
|---|---|
| `--app bistro` | the latest run of **any** test for `bistro` |
| `--app bistro --test booking` | the latest run of the `booking` test |
| `--run r_20260801T180627_bistro_booking` | that exact run |

So if you follow the demo in order, `--app bistro` on its own lands on the
**refusal** run from step 6.11 — because that is genuinely the latest thing that
happened:

```powershell
python cli.py runs --app bistro
```

```
  r_20260801T180700_bistro_refusal             passed  heals=0 refusals=1 3.03s
  r_20260801T180627_bistro_booking             passed  heals=5 refusals=0 3.38s
  r_20260801T180622_bistro_booking             passed  heals=0 refusals=0 3.67s
```

That run has `heals=0`, and a patch of zero heals is an empty file:

```powershell
python cli.py report --app bistro --format patch     # prints nothing — correct
```

**This is not a bug and not an empty database.** It is the report of a run in
which nothing was repaired. Add `--test booking`, or name the run explicitly with
`--run`, to report the healing run instead. `python cli.py runs --app bistro` is
how you find the id.

### 8.2 — `--format md`

The human-readable run report: what happened, what was repaired, why, and what QA
should do about it. Paste it into a ticket or a PR description.

```powershell
python cli.py report --app bistro --test booking --format md
```

```markdown
# Self-healing run report — bistro / booking

- **Result:** PASSED
- **Run id:** `r_20260801T180627_bistro_booking`
- **Script:** `D:\Selfhealing-system\demo\storefront\test_booking.py`
- **Browser:** chrome
- **Started:** 2026-08-01T18:06:27.047782+00:00
- **Duration:** 3.38s
- **Heals:** 5   **Refusals:** 0

## Repaired locators

### `id='guests'`

- **Repaired to:** `(By.ID, "party-count")`  *(derived from the live element)*
- **Confidence:** 83.33% — AUTOMATIC HEAL (margin over next-best: 65.23%)
- **Rules:** R1 0.0%, R2 100.0%, R3 50.0%, R4 100.0%
- **Why:** DOM position unchanged; CSS class partially matched (50%);
  neighbouring elements matched.
- **Recommendation:** Update the test script to use (By.ID, "party-count").

### `name='slot'`

- **Repaired to:** `(By.ID, "time-slot")`  *(derived from the live element)*
- **Confidence:** 80.7% — AUTOMATIC HEAL (margin over next-best: 34.57%)
- **Rules:** R1 76.74%, R2 100.0%, R3 50.0%, R4 100.0%
- **Why:** text partially matched (77%); DOM position unchanged; CSS class
  partially matched (50%); neighbouring elements matched.
- **Recommendation:** Update the test script to use (By.ID, "time-slot").
...
```

Each heal carries its four component scores and a written reason, so the report
defends every decision rather than asserting one. The footer states plainly that
neither the application nor the test file was modified.

Run it against the **refusal** instead and you get the other half of the story —
which is worth showing to judges precisely because it is the unglamorous case:

```markdown
- **Heals:** 0   **Refusals:** 1

## Refused (manual intervention required)

- `id='wine-pairing-option'` — best match 0.0%, below the safety gate.
  No element was interacted with.
```

### 8.3 — `--format patch`

The same run as a diff-style block: the edits a QA engineer would actually make.

```powershell
python cli.py report --app bistro --test booking --format patch
```

```diff
--- D:\Selfhealing-system\demo\storefront\test_booking.py
+++ D:\Selfhealing-system\demo\storefront\test_booking.py (suggested)

- (By.ID, "guests")
+ (By.ID, "party-count")

- (By.NAME, "slot")
+ (By.ID, "time-slot")

- (By.CSS_SELECTOR, ".btn-reserve")
+ (By.ID, "confirm-booking")

- (By.LINK_TEXT, "My reservations")
+ (By.LINK_TEXT, "View my bookings")

- (By.XPATH, "//span[@id='fee']")
+ (By.ID, "deposit-total")
```

Three of the five come back on a *more stable* strategy than they went in with —
a CSS class and a brittle XPath both became ids. That is the Locator Recovery
ranking in [section 9](#9-how-the-decision-engine-works) doing its job, and it is
the answer to "won't it just break again next sprint?".

It is **rendered, not applied**. This is deliberate: the framework repairs the
*execution* of a test, never the committed test file. The only thing that edits
your source is a human clicking Approve in the Approval Queue (step 6.9).

> The header is a real file path, not a `diff -u` hunk — there are no line
> numbers or context lines, so `git apply` will not consume it. It is a review
> artefact for a person, and good material for a report appendix.

### 8.4 — `--format csv` and `--format json`

| Format | Shape | Use it for |
|---|---|---|
| `csv` | one row per heal, columns for confidence, margin, policy, reason | spreadsheets, charts, a results appendix |
| `json` | the raw run record, exactly as stored | feeding another tool, or proving nothing was massaged |

### 8.5 — Writing to a file

```powershell
python cli.py report --app bistro --test booking --format md    --out heal-report.md
python cli.py report --app bistro --test booking --format patch --out suggested.diff
```

Without `--out` everything goes to stdout. The dashboard offers the same three
renderings as download buttons: **Applications → Run history**, select a run in
the sidebar, then Markdown / CSV / JSON.

---

## 9. How the decision engine works

Every candidate element on the live page is scored 0–100 against the golden
fingerprint, then routed by policy:

| Score | Margin over runner-up | Policy | Outcome |
|---|---|---|---|
| **≥ 75** | clear | `AUTOMATIC HEAL` | applied, run continues |
| **≥ 75** | ambiguous | `CAUTIOUS HEAL` | applied, flagged for review |
| **20 – 75** | — | `CAUTIOUS HEAL` | applied, flagged for review |
| **< 20** | — | `CRITICAL FAULT` | **refused** — the test fails honestly |

The margin check matters: a 90% match is not trustworthy if the runner-up also
scores 88%. Ambiguity is treated as a reason for caution, not confidence.

Thresholds live in `config.py` (`CONFIDENCE_THRESHOLD_HIGH = 75.0`,
`CONFIDENCE_THRESHOLD_LOW = 20.0`) and can be changed live in the
**Configuration** tab.

### Locator Recovery ranking

When writing a repaired locator, the engine ranks the live element's attributes
by expected stability and picks the highest available:

```
id  →  data-testid  →  data-test  →  data-qa  →  data-cy
    →  name  →  aria-label  →  visible text  →  css class  →  xpath
```

This is why three of the five repairs in this demo came back on a *more* stable
strategy than they started with.

---

## 10. Reset between rehearsals

Three commands. All three are required — approving heals edits the test script,
so restoring only the HTML leaves the two out of sync and every later run fails
for the wrong reason.

```powershell
python reset_all.py
Copy-Item storefront\app.v1.html storefront\app.html -Force
Copy-Item storefront\test_booking.v1.py storefront\test_booking.py -Force
```

Then refresh the dashboard (**R**).

`reset_all.py` options:

| Command | Effect |
|---|---|
| `python reset_all.py` | wipe everything — telemetry, approvals, apps, baselines, runs |
| `python reset_all.py --keep-apps` | keep registered apps and baselines, clear the rest |
| `python reset_all.py --backup` | copy `data\` to `data_backup_<timestamp>\` first |

---

## 11. Applying this to a different project

### 11.1 — What "bistro" actually is

Every command in this guide carries `--app bistro`, so it is worth being explicit:
**`bistro` is not a feature, a mode, or anything the framework knows about.** It
is an *application id* — a short name you invented at registration time, and the
only thing tying the whole system together.

You chose it here:

```powershell
python cli.py register --app bistro --name "Bistro Nova" --url "file:///.../app.html"
#                            ^^^^^^
#                            invented on the spot. "shop", "checkout",
#                            "admin-portal" would all have worked identically.
```

From that moment the id is the key to everything:

| What | Where it lives | Named after the id |
|---|---|---|
| The application record | `data/apps/bistro.json` | yes |
| The Golden Fingerprint baseline | `data/fingerprints/bistro_fingerprints.json` | yes |
| Every heal, refusal and drift row | the telemetry buckets, stamped `app_id` | yes |
| Every run record | `data/runs/r_<timestamp>_bistro_<test>.json` | yes |
| Dashboard scoping | sidebar → Application | yes |

Which is why the *same* string has to appear in three places, and why they must
agree:

```python
with selfheal.run(app="bistro", test="booking"):   # in the test script
```
```powershell
python cli.py register --app bistro ...            # at registration
python cli.py report   --app bistro ...            # when reporting
```

If the test says `app="bistro"` and you report `--app restaurant`, you get *"No
runs recorded yet"* — not because anything failed, but because you asked about an
application that has never run. Registration is optional precisely because
`selfheal.run(app="bistro")` registers the id on the spot if it is new; you
register explicitly only so the dashboard can show a real name and URL.

The second id, `test="booking"`, works the same way one level down. It is what
makes `--test booking` in [section 8](#8-reports--turning-a-run-into-an-artefact)
select the healing run rather than the refusal — the refusal run declares
`test="refusal"`, so they are two separate test identities under one application.

**Choosing ids for a new project.** Anything lowercase and filesystem-safe; the
registry normalises the rest (`My Shop!` becomes `my-shop`). One id per
*application under test*, not per page and not per test file — a checkout flow and
a product page in the same web app share one id, so they share one baseline and
one drift report. Use a second id only when it is genuinely a different
application, because two ids can never see each other's fingerprints. That
isolation is the point: two apps that both contain `#submit` keep separate
baselines and cannot corrupt each other.

### 11.2 — The five steps

The framework has no knowledge of Bistro Nova. To point it at anything else:

**1. Make a folder anywhere under `demo\`** and put your page and test in it.

**2. Fix one line in your test** — the path back to the framework root:

| Your test lives in | Use |
|---|---|
| `demo\myproject\` | `sys.path.insert(0, os.path.join(HERE, ".."))` |
| `demo\examples\myproject\` | `sys.path.insert(0, os.path.join(HERE, "..", ".."))` |

**3. Wrap your existing test body** in the context manager. Nothing else changes:

```python
import selfheal

with selfheal.run(app="myapp", test="mytest"):
    driver = webdriver.Chrome()
    driver.get(...)
    # ... your existing, unmodified Selenium code ...
```

**4. Register it** so the dashboard shows a proper name:

```powershell
python cli.py register --app myapp --name "My App" --url "file:///C:/path/to/page.html" --source myproject/page.html
```

**5. Run it once against a working page** to record the baseline, then refactor
and run again.

That is the whole integration. There is no base class to inherit, no decorator on
every test, no locator repository to maintain. `selfheal.run()` patches
Selenium's own lookup methods in-process, so **every** driver the suite creates
heals — including drivers built deep inside a fixture, a page-object factory, or
a third-party helper, and including lookups made through `WebDriverWait`.

### 11.3 — The same demo, for a project called `checkout`

Substituting one id throughout. Nothing else about the framework changes.

```powershell
# the id you invent -------------------------------v
python cli.py register --app checkout --name "Acme Checkout" `
    --url "file:///D:/Selfhealing-system/demo/acme/cart.html" `
    --source acme/cart.html
```

```python
# acme/test_cart.py — must name the SAME id
with selfheal.run(app="checkout", test="place_order"):
    ...
```

```powershell
python acme\test_cart.py                                  # Day 1: learns
#   ...developer refactors cart.html...
python acme\test_cart.py --keep-baseline                  # Day 2: heals

python cli.py baseline --app checkout                     # what it learned
python cli.py check    --app checkout                     # change impact
python cli.py runs     --app checkout                     # find the run ids
python cli.py report   --app checkout --test place_order --format patch
```

Read the last line as: *"the suggested source edits from the most recent run of
the `place_order` test of the `checkout` application"*. Every `--app` value is
the id from the `register` line; every `--test` value is the `test=` argument
from `selfheal.run(...)`. There is nothing else to configure.

The baseline lands in `data/fingerprints/checkout_fingerprints.json`, the
dashboard sidebar gains a `checkout` entry, and `bistro` is entirely unaffected.

> **Two worked examples ship with the project.** `demo/minimal/` is a page with
> no ids, no stylesheet and no JavaScript (5 heals); `demo/webapp/` is a
> conventional `index.html` + `styles.css` + `app.js` application (6 heals).
> Neither is configured differently from Bistro Nova, which is the point. See
> [`applying_to_any_project.md`](applying_to_any_project.md).

### Designing a good demo for another project

- Use **several different locator strategies** in one test. Healing an id is
  unremarkable; healing an id, a name, a CSS class, link text and an XPath in one
  run is the story.
- Make the refactor **invisible to a user**. If the page looks different, judges
  will suspect the test is passing for the wrong reason.
- **Update the JavaScript and CSS** alongside the ids. A page whose click handler
  no longer attaches will fail for reasons unrelated to healing, and it looks
  like your system broke.
- Assert on a **computed value** (here, the deposit total), not just element
  presence. It proves the healed elements were the *functionally correct* ones,
  not merely something with a similar name.
- Include one lookup that **cannot** be healed, to demonstrate the safety gate.

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Day 2 reports fewer than 5 heals | the Day-2 paste was incomplete — some ids still match | replace the whole file with the section 5 content, do not hand-edit |
| `AssertionError: expected 1,200.00, got '0.00'` | the page's JavaScript still references old ids, so the click handler never attached | re-paste the Day-2 file in full |
| Second Day-2 run shows **0 heals** | you omitted `--keep-baseline`, so the refactored page became the new baseline | delete `data\fingerprints\bistro_fingerprints.json`, restore the v1 page, redo Step 6.4 |
| Test fails on the *original* page | the script was healed by an earlier approval and never restored | restore from `test_booking.v1.py` |
| The script "did not change" after Approve | your editor is showing a stale buffer | close and reopen the file |
| `report --format patch` prints **nothing** | it reported the latest run, which was the refusal from 6.11 — a run with 0 heals | add `--test booking`, or `--run <id>` from `python cli.py runs --app bistro`. See [section 8.1](#81--which-run-gets-reported) |
| `report` says **"No runs recorded yet"** | the `--app` value does not match the id in `selfheal.run(app=...)` | `python cli.py apps` to list the real ids. See [section 11.1](#111--what-bistro-actually-is) |
| **Change impact** tab empty | step 6.12 was never run — it is the only thing that writes the drift bucket | `python cli.py check --app bistro`, or the button in Configuration → Target application |
| **Infrastructure** tab empty | step 6.13 was never run | `python simulate_infra_heal.py`, or Configuration → Quick actions |
| **Source write-back** tab empty | expected — approval mode routes edits to the Approval Queue instead | nothing to fix; see [section 7](#why-source-write-back-stays-empty) |
| Configuration shows a fingerprint profile that does not exist | a stale `data\config_override.json` from an older layout | Configuration → **Reset to Defaults**, or delete that file |
| Dashboard still shows old data | Streamlit cached the page | press **R**, or **Ctrl+Shift+R** |
| Dashboard survives `Ctrl+C` and holds port 8501 | known Streamlit shutdown race | `netstat -ano \| findstr :8501` then `taskkill /F /PID <pid>` |
| `RuntimeError: Event loop is closed` on shutdown | cosmetic Streamlit teardown race — no data is lost | ignore |
| Script runs and prints nothing at all | the file saved empty | check the file size; re-paste |
| Sidebar collapsed and will not reopen | fixed — the expand button is restored in `theme.py` | hard-refresh with **Ctrl+Shift+R** |

---

## 13. Anticipated questions

**"Doesn't it just break again next sprint?"**
No — the repaired script is *more* resistant than the original. Three of five
lines in this demo came back on a more stable strategy: a brittle XPath and a CSS
class both became ids. The Locator Recovery ranking exists precisely to avoid
re-introducing fragile selectors.

**"What if it matches the wrong element?"**
Three defences. Below 20% confidence it refuses outright (Step 6.11). A high
score with an ambiguous runner-up is downgraded to a cautious heal. And nothing
reaches your source file without a human clicking Approve — with a backup taken
first and a Rollback button beside it.

**"Does it silently edit our committed tests?"**
No. Runtime healing keeps the run alive and touches no files. The source edit is
a queued *recommendation*, applied only on approval. Silent rewriting is the one
behaviour a QA team cannot audit, so it is off by default.

**"How much work is it to adopt?"**
One line per test file. `selfheal.run()` patches Selenium's lookup methods in
process, so existing suites work unmodified — no base class, no decorators, no
locator repository.

**"How do we know the heal was correct and not a coincidence?"**
Two ways. Every heal exposes its R1–R4 component scores and a written reason, so
the decision is auditable rather than a black box. And the test asserts on a
computed value — the deposit total — which can only be right if the healed
elements were the functionally correct ones.

**"What about things that are not locators?"**
The Infrastructure monitor watches disk, error rate and service health, and
applies rule-based recovery: log rotation, temp-file purge, and restarting a
dead target process (Step 6.13).

---

## Quick reference — the whole demo

```powershell
cd D:\Selfhealing-system\demo
.venv\Scripts\Activate

python reset_all.py                                    # 6.0  clean slate
Copy-Item storefront\app.html storefront\app.v1.html   # 6.1  snapshot
Copy-Item storefront\test_booking.py storefront\test_booking.v1.py

streamlit run dashboard.py                             # 6.2  (second terminal)

python cli.py register --app bistro --name "Bistro Nova" --url "file:///D:/Selfhealing-system/demo/storefront/app.html" --source storefront/app.html
python storefront\test_booking.py                      # 6.4  Day 1 — learns

#                                                        6.5  paste the Day-2 app.html

python storefront\test_booking.py --no-heal            # 6.6  crashes
python storefront\test_booking.py --keep-baseline      # 6.7  5 heals, passes
#                                                        6.9  Approve all 5 in the dashboard
python storefront\test_booking.py --no-heal            # 6.10 PASSES  <- the moment

python storefront\test_booking.py --refuse             # 6.11 safety gate
python cli.py check --app bistro                       # 6.12 change impact
python simulate_infra_heal.py                          # 6.13 infrastructure

python cli.py runs   --app bistro                      # 6.14 find the run ids
python cli.py report --app bistro --test booking --format md
python cli.py report --app bistro --test booking --format patch
```

`--test booking` matters: without it `report` renders the refusal from 6.11,
which has zero heals, and `--format patch` prints an empty result.

---

## Command reference

| Command | What it does | Fills |
|---|---|---|
| `cli.py register --app <id> --url <url>` | create the application record | Applications |
| `cli.py apps` | list registered applications and their baselines | — |
| `cli.py learn --app <id> [--force]` | capture a baseline by scanning the page | Applications |
| `cli.py baseline --app <id>` | print the tracked elements | — |
| `cli.py check --app <id>` | change impact vs the baseline, without running tests | Change impact |
| `cli.py tests --app <id>` | tests registered for the app, and their health | — |
| `cli.py runs --app <id>` | run history with ids, heal and refusal counts | — |
| `cli.py report --app <id> [--test <id>] --format md\|patch\|csv\|json` | render one run | — |
| `simulate_infra_heal.py [disk\|error\|down\|combined\|all] [--no-restart]` | drive the infrastructure healer | Infrastructure, Alerts |
| `reset_all.py [--keep-apps] [--backup]` | wipe telemetry, runs, apps and baselines | clears everything |
