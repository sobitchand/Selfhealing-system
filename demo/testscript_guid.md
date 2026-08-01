# Writing a test script for the self-healing framework

A companion to [`final_demo.md`](final_demo.md) and
[`applying_to_any_project.md`](applying_to_any_project.md). Those explain the
demo and the projects. **This one is the contract**: exactly what a Selenium
script must contain to be healed, what happens if you leave something out, and
what the framework does and does not intercept.

Everything in the tables below was **probed against the running framework**, not
inferred from the source. Where something is untested, it says so.

---

## Contents

1. [The minimum script](#1-the-minimum-script)
2. [Every line, and why it is there](#2-every-line-and-why-it-is-there)
3. [`sys.path` — the one line that depends on where your file lives](#3-syspath--the-one-line-that-depends-on-where-your-file-lives)
4. [`selfheal.run()` — the parameters](#4-selfhealrun--the-parameters)
5. [What heals and what does not](#5-what-heals-and-what-does-not)
6. [What gets learned, and when](#6-what-gets-learned-and-when)
7. [Locator strategies](#7-locator-strategies)
8. [The standard flags](#8-the-standard-flags)
9. [Common mistakes and their symptoms](#9-common-mistakes-and-their-symptoms)
10. [pytest and unittest](#10-pytest-and-unittest)
11. [Full template — copy this](#11-full-template--copy-this)
12. [Pre-flight check](#12-pre-flight-check)

---

## 1. The minimum script

Strip away the flags and the driver helper and this is all of it:

```python
import os, sys
from selenium import webdriver
from selenium.webdriver.common.by import By

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import selfheal

with selfheal.run(app="myapp", test="mytest"):
    driver = webdriver.Chrome()
    driver.get("file:///D:/path/to/page.html")
    driver.find_element(By.ID, "submit").click()
    driver.quit()
```

Nine lines, of which **three** are framework-related: the `sys.path` line, the
`import selfheal`, and the `with` statement. Everything else is ordinary
Selenium.

---

## 2. Every line, and why it is there

### Required imports

```python
import os, sys                                    # to build the sys.path entry
from selenium import webdriver                    # your driver
from selenium.webdriver.common.by import By       # your locators
import selfheal                                   # the framework
```

That is the complete list. There is **nothing else to import** — no engine, no
wrapper, no base class, no decorator. You do not import `healing_engine`,
`automation_wrapper`, `fingerprint_manager` or anything else; those are
internals.

### Optional, depending on what your test does

```python
from selenium.webdriver.support.ui import Select              # <select> dropdowns
from selenium.webdriver.support.ui import WebDriverWait       # explicit waits — these heal
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException # to demo the refusal
from selenium.webdriver.chrome.service import Service         # a pinned chromedriver
```

### The three framework lines

```python
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))   # 1. make `selfheal` importable
import selfheal                                # 2. load it
with selfheal.run(app="myapp", test="mytest"): # 3. patch Selenium for this block
```

Line 3 is the whole integration. Inside that block, every `find_element` call in
your process is healed. Outside it, Selenium behaves exactly as it always did —
**verified**: `selfheal.is_installed()` returns `False` after the block exits.

---

## 3. `sys.path` — the one line that depends on where your file lives

`import selfheal` only works if Python can find `demo/selfheal.py`. Count the
directories between your test and `demo\`:

| Your test lives in | Use |
|---|---|
| `demo\mytest.py` | `sys.path.insert(0, HERE)` |
| `demo\myproject\test_x.py` | `sys.path.insert(0, os.path.join(HERE, ".."))` |
| `demo\examples\myproject\test_x.py` | `sys.path.insert(0, os.path.join(HERE, "..", ".."))` |
| `demo\a\b\c\test_x.py` | `sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))` |

Always build it from `HERE`, never a relative path like `".."` on its own —
`sys.path` is resolved against the **current working directory**, so a bare
`".."` breaks the moment someone runs the test from a different folder.

```python
HERE = os.path.dirname(os.path.abspath(__file__))   # always do this first
```

**Symptom if you get it wrong:** `ModuleNotFoundError: No module named 'selfheal'`.

---

## 4. `selfheal.run()` — the parameters

```python
selfheal.run(app, test=None, learn=True, heal_find_elements=None)
```

| Parameter | Meaning |
|---|---|
| `app` | **Required.** The application id. A string you invent. Auto-registers if new. |
| `test` | Names this test in reports and the dashboard. Defaults to the calling function's name — pass it explicitly, it is worth the four characters. |
| `learn` | `True` (default): a passing run records/updates the baseline. `False`: heal only, leave the baseline pinned. |
| `heal_find_elements` | `True` heals `find_elements` (plural) too. Off by default — see §5. |

### `app` — the id ties everything together

The same string must appear in `selfheal.run(app=...)` and in
`cli.py register --app ...` and in `cli.py report --app ...`. It names the
baseline file (`data/fingerprints/<app>_fingerprints.json`), stamps every heal,
and scopes the dashboard.

### `learn` — when to pin the baseline

```python
with selfheal.run(app="shop", test="checkout"):                # Day 1: learn
with selfheal.run(app="shop", test="checkout", learn=False):   # Day 2: heal only
```

Pin it (`learn=False`, or the `--keep-baseline` flag by convention) whenever you
want the run to be **repeatable**. Without it, a passing run re-learns from the
current page, so running the same demo twice reports 5 heals and then 0.

---

## 5. What heals and what does not

**Probed directly against the framework.** A Day-1 baseline was recorded, the
page was refactored, and each call style was then exercised:

| Call style | Heals? | Verified |
|---|---|---|
| `driver.find_element(By.X, "v")` | **yes** | ✅ |
| `element.find_element(By.X, "v")` — nested, page-object style | **yes** | ✅ |
| `WebDriverWait(d, 3).until(EC.presence_of_element_located(...))` | **yes** | ✅ |
| Driver created **before** the `with` block, used inside it | **yes** | ✅ |
| `driver.find_elements(...)` — plural, default | **no** | ✅ |
| `driver.find_elements(...)` with `heal_find_elements=True` | **yes** | ✅ |
| Anything at all after the block exits | **no** — Selenium restored | ✅ |

Three consequences worth knowing:

**Explicit waits heal.** `expected_conditions` calls `find_element` internally,
so a heal happens *before* the wait can time out. You do not have to rewrite
waits.

**The driver can be created anywhere.** The patch is applied to Selenium's
*classes*, not to a driver instance, so a driver built in a fixture, a factory or
a helper — even one created before the block — heals from that point on. You do
not have to restructure your suite.

**`find_elements` (plural) is off on purpose.** An empty list is a legitimate
answer: `find_elements(By.CLASS_NAME, "error-banner")` returning `[]` means "no
errors on screen", and healing that would invent a match for something that
correctly wasn't there. Turn it on only if every `find_elements` call in your
suite is genuinely expected to match:

```python
with selfheal.run(app="shop", test="checkout", heal_find_elements=True):
```

---

## 6. What gets learned, and when

The baseline is built from **the locators your test successfully resolved**, not
from a scan of the page. If your test never touches an element, that element is
never tracked.

Two rules that follow from that:

**Learning only happens on a passing run.** If the block raises, whatever was
captured is discarded rather than recording a broken page as the reference state.
You will see:

```
⚠️ run did not complete cleanly; baseline for 'myapp' left unchanged.
```

**Learn from a known-good build.** Point the Day-1 run at a page you have opened
in a browser and confirmed works. A baseline learned from a broken page bakes the
fault in permanently.

To inspect what was recorded:

```powershell
python cli.py baseline --app myapp
```

---

## 7. Locator strategies

All eight Selenium strategies work, as broken input and as repaired output:

```python
driver.find_element(By.ID, "submit")
driver.find_element(By.NAME, "email")
driver.find_element(By.CLASS_NAME, "btn-primary")
driver.find_element(By.CSS_SELECTOR, "#cart .checkout")
driver.find_element(By.XPATH, "//span[@id='total']")
driver.find_element(By.LINK_TEXT, "My account")
driver.find_element(By.PARTIAL_LINK_TEXT, "My acc")
driver.find_element(By.TAG_NAME, "button")
```

**Use several different ones in one test.** Healing an id is unremarkable;
healing an id, a name, a class, link text and an XPath in a single run is the
demonstration.

When the engine writes a repaired locator it ranks the live element's attributes
by stability and picks the best available:

```
id → data-testid → data-test → data-qa → data-cy → name → aria-label
   → visible text → css class → xpath
```

This is why a brittle `By.XPATH` often comes back as a `By.ID` — and why adding
`data-testid` to an element is worth doing, since it outranks everything except a
real id.

---

## 8. The standard flags

Not required by the framework — a convention the demo scripts follow, and worth
copying so every test in the project behaves the same way:

```python
HEAL   = "--no-heal"       not in sys.argv    # skip the framework entirely
LEARN  = "--keep-baseline" not in sys.argv    # heal without re-learning
HEADED = "--headed"        in sys.argv        # show the browser
REFUSE = "--refuse"        in sys.argv        # ask for something impossible
```

| Flag | Effect | Use it for |
|---|---|---|
| *(none)* | healing on, learning on | Day 1 |
| `--keep-baseline` | healing on, learning off | Day 2 — makes the run repeatable |
| `--no-heal` | framework never loaded | the control — proves the test really is broken |
| `--headed` | visible browser | showing a live audience |
| `--refuse` | probe for a non-existent element | the safety gate |

`--no-heal` matters more than it looks. It is what proves the test genuinely
fails without the framework, and later that the repaired script passes without
it.

---

## 9. Common mistakes and their symptoms

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'selfheal'` | wrong `sys.path` depth | §3 |
| Test crashes normally, no healing attempted | lookups are outside the `with` block | move them inside |
| `0 heal(s)` on the refactored page | the refactor renamed things the test never uses | rename the hooks the test actually asks for |
| `0 heal(s)` on the *second* Day-2 run | the first run re-learned the new page | add `learn=False` / `--keep-baseline` |
| Heals happen but the assertion fails | the page's JS still references the old ids, so the handler never attached | update `app.js` alongside the markup |
| `find_elements` returns `[]`, nothing healed | plural is off by default | `heal_find_elements=True`, if appropriate |
| The refusal probe heals instead of refusing | its name shares a word with a tracked element | rename it — see below |
| `No runs recorded yet` from `cli.py report` | `--app` doesn't match `selfheal.run(app=...)` | `python cli.py apps` |
| Run aborts with `Self-healing engine error` | *fixed* — was a Windows file-lock race with the dashboard | pull the current `approval_workflow.py` |

### Naming the refusal probe

Before scoring candidates the engine works out **which** tracked element a broken
locator meant, by string-similarity against the baseline, and refuses below 40%.
So an "impossible" element that shares vocabulary with a real one will *not*
refuse. Measured:

| Probe | Similarity to nearest baseline locator | Outcome |
|---|---|---|
| `renew-membership-button` | 43.8% vs `member-id` — shares *member* | healed |
| `printer-jam-warning` | 31.2% | refused ✓ |
| `wine-pairing-option` | 25.0% | refused ✓ |

**Name it from a different domain than the page.** A library page? Ask for a
printer jam.

---

## 10. pytest and unittest

`selfheal.run()` is an ordinary context manager, so it composes with any runner.

> **Not verified in this environment** — pytest is not installed in
> `demo\.venv`. The pattern follows directly from the context-manager behaviour
> in §5, which *is* verified, but run it once before relying on it.

**pytest** — one autouse fixture heals the whole module:

```python
import pytest, selfheal

@pytest.fixture(autouse=True)
def healing():
    with selfheal.run(app="shop", test="checkout"):
        yield
```

Pass `test=` explicitly here. Left out, the run is named after the *fixture*
function rather than the test.

**unittest**:

```python
class CheckoutTest(unittest.TestCase):
    def setUp(self):
        self._heal = selfheal.run(app="shop", test=self._testMethodName)
        self._heal.__enter__()

    def tearDown(self):
        self._heal.__exit__(None, None, None)
```

Because the patch is class-level (§5), a driver built in `setUpClass` or a shared
fixture still heals.

---

## 11. Full template — copy this

Save as `demo\myproject\test_myproject.py` and change the four marked lines.

```python
"""
<one line about what this test does>

    python myproject/test_myproject.py                   learn / heal (normal)
    python myproject/test_myproject.py --keep-baseline   heal without relearning
    python myproject/test_myproject.py --no-heal         plain Selenium, no framework
    python myproject/test_myproject.py --headed          watch it in a browser
    python myproject/test_myproject.py --refuse          demonstrate the safety gate
"""

import glob
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))          # <-- 1. depth: see section 3
import selfheal

PAGE = "file:///" + os.path.join(HERE, "index.html").replace("\\", "/")   # <-- 2. your page

APP_ID = "myproject"                                  # <-- 3. your app id
TEST_ID = "main_flow"                                 # <-- 4. your test id

HEAL = "--no-heal" not in sys.argv
LEARN = "--keep-baseline" not in sys.argv
HEADED = "--headed" in sys.argv
REFUSE = "--refuse" in sys.argv


def make_driver():
    """Reuses the cached chromedriver when present, so a demo never stalls on a
    download. Falls back to webdriver_manager on a clean machine."""
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


def main_flow(driver):
    """The test. Use several different locator strategies, and assert on a value
    the page COMPUTES -- that is what proves a heal found the functionally
    correct element rather than something with a similar name."""
    driver.get(PAGE)

    driver.find_element(By.ID, "...").send_keys("...")
    driver.find_element(By.NAME, "...").send_keys("...")
    driver.find_element(By.CSS_SELECTOR, "...").click()
    driver.find_element(By.LINK_TEXT, "...")
    result = driver.find_element(By.XPATH, "...").text

    assert result == "...", f"expected ..., got {result!r}"
    print(f"PASS - {result}")


def safety_gate(driver):
    """Ask for an element that exists nowhere. Name it from a DIFFERENT DOMAIN
    than the page, or it will resemble a tracked element and heal instead of
    refusing -- see section 9."""
    driver.get(PAGE)
    print("asking for id='...' -- no such concept on this page")
    try:
        driver.find_element(By.ID, "...")
        print("UNEXPECTED: an element was returned. The system guessed!")
    except NoSuchElementException as e:
        print("\nCORRECT: the system refused rather than guessing.")
        print(f"   {str(e).splitlines()[0][:140]}")


def main():
    body = safety_gate if REFUSE else main_flow

    if not HEAL:
        print("mode: plain Selenium, NO self-healing")
        driver = make_driver()
        try:
            body(driver)
        finally:
            driver.quit()
        return

    print(f"mode: self-healing ON, learning {'OFF (baseline pinned)' if not LEARN else 'ON'}")
    with selfheal.run(app=APP_ID,
                      test="refusal" if REFUSE else TEST_ID,
                      learn=False if REFUSE else LEARN):
        driver = make_driver()
        try:
            body(driver)
        finally:
            driver.quit()


if __name__ == "__main__":
    main()
```

---

## 12. Pre-flight check

You do not need to review generated code. Run it and read the output.

```powershell
cd D:\Selfhealing-system\demo
.venv\Scripts\Activate

python cli.py register --app myproject --name "My Project" `
    --url "file:///D:/Selfhealing-system/demo/myproject/index.html" `
    --source myproject/index.html

python myproject\test_myproject.py                 # 1
#   ...swap in the refactored page...
python myproject\test_myproject.py --no-heal       # 2
python myproject\test_myproject.py --keep-baseline # 3
python myproject\test_myproject.py --refuse        # 4
```

| Step | Must print | If it doesn't |
|---|---|---|
| 1 | `📸 baseline recorded` | the test failed — fix the test before anything else |
| 2 | `NoSuchElementException` | your refactor didn't touch the locators the test uses |
| 3 | `N heal(s)` **and** `PASS` | 0 heals → see step 2. Heals but no PASS → the page's JS wasn't updated |
| 4 | `❌ Confidence below safety gate` | rename the probe — §9 |

Then confirm the dashboard filled:

```powershell
python cli.py runs     --app myproject
python cli.py report   --app myproject --test main_flow --format patch
```

If all four steps behave, the script is correct and the demo is safe to present.
