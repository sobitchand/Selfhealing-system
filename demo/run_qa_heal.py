"""
QA self-healing scenario suite.

Acts like a QA/DevOps engineer auditing the app after a refactor. For each
scenario it tells the target app to MUTATE the START button's markup
(via ?break=<mode>, served by demo_target_app.py) the way a developer might —
rename a CSS class, rename the element id, change a data attribute, or all at
once. The old locator now ERRORS (NoSuchElementException). The SelfHealingWebDriver
then scrapes the live DOM, scores every element against the golden fingerprint
(text + structure + neighbours), recognises the START button despite the changed
attribute, re-grabs it by its live position, and logs the heal to the dashboard.

A normal Selenium test would crash on every one of these. Here all of them heal.

Prerequisites:
  1. Google Chrome installed.
  2. Target app running:  python demo_target_app.py   (http://127.0.0.1:8000)

Run:
  python run_qa_heal.py
"""

import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

# Reuse the cached-chromedriver resolver so this suite gets the same
# network-free startup fix as the main demo runner.
from run_selenium_heal import _resolve_chromedriver
from automation_wrapper import SelfHealingWebDriver
import learning_mode
import config

TARGET_URL = "http://127.0.0.1:8000"

# Each scenario: a developer change to the app, the stale locator it breaks, and
# what the healed element must turn out to be. The broken locators live here
# (not in config.SOURCE_HEAL_TARGETS), so source write-back never mutates them
# and the suite stays repeatable.
SCENARIOS = [
    {
        "name": "CSS class renamed  (btn-main -> btn-primary)",
        "break": "css",
        "locator": (By.CSS_SELECTOR, ".btn-main"),
        "expect_text": "START",
    },
    {
        "name": "Element id renamed (start-btn -> start-btn-v2)",
        "break": "id",
        "locator": (By.ID, "start-btn"),
        "expect_text": "START",
    },
    {
        "name": "Data attribute changed (data-action start -> begin)",
        "break": "attr",
        "locator": (By.CSS_SELECTOR, "[data-action='start']"),
        "expect_text": "START",
    },
    {
        "name": "Multiple changes at once (class + id + attribute)",
        "break": "all",
        "locator": (By.CSS_SELECTOR, ".btn-main"),
        "expect_text": "START",
    },
]


def _make_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(_resolve_chromedriver()), options=options)


def run_scenario(driver, scenario):
    """Apply one fault, attempt the stale locator, return a result dict."""
    by, value = scenario["locator"]
    url = f"{TARGET_URL}/?break={scenario['break']}"
    driver.get(url)

    healing_driver = SelfHealingWebDriver(driver)
    result = {"name": scenario["name"], "locator": f"{by}='{value}'", "passed": False, "detail": ""}

    try:
        element = healing_driver.find_element(by, value)
        text = (element.text or "").strip()
        if text == scenario["expect_text"]:
            result["passed"] = True
            result["detail"] = f"healed -> <{element.tag_name}> text='{text}'"
        else:
            result["detail"] = f"healed to WRONG element: text='{text}' (expected '{scenario['expect_text']}')"
    except NoSuchElementException as e:
        result["detail"] = f"NOT healed: {str(e).splitlines()[0]}"
    return result


def main():
    print("🧪 QA Self-Healing Suite — auditing the app after a refactor\n")
    print("🌐 Launching headless Chrome runner...")
    try:
        driver = _make_driver()
    except Exception as e:
        print(f"❌ Could not start Chrome. Is Google Chrome installed? Details: {e}")
        sys.exit(1)

    try:
        # Establish the golden baseline from the CLEAN app (never from a broken
        # page, which would poison the fingerprint).
        driver.get(TARGET_URL)
        learning_mode.ensure_fingerprints(driver, config.POMODORO_FINGERPRINTS_PATH)

        results = []
        for sc in SCENARIOS:
            print("\n" + "=" * 70)
            print(f"▶ SCENARIO: {sc['name']}")
            print(f"  Dev changed the app; stale locator now points at nothing: {sc['locator'][0]}='{sc['locator'][1]}'")
            results.append(run_scenario(driver, sc))
    finally:
        driver.quit()

    # ---------------------------- QA report ----------------------------
    print("\n" + "=" * 70)
    print("QA SELF-HEALING REPORT")
    print("=" * 70)
    passed = 0
    for r in results:
        mark = "✅ PASS" if r["passed"] else "❌ FAIL"
        if r["passed"]:
            passed += 1
        print(f"{mark}  {r['name']}")
        print(f"        broken locator: {r['locator']}")
        print(f"        result        : {r['detail']}")
    total = len(results)
    print("-" * 70)
    print(f"RESULT: {passed}/{total} scenarios healed.")
    print("📡 Every heal is logged — watch the dashboard 'UI Heuristic Healing' tab.")

    # Non-zero exit if any scenario failed, so this can gate CI like a real test.
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
