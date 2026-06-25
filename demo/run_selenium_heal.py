"""
Real end-to-end self-healing demo.

Unlike test_ui_healing.py (which only writes canned scenarios), this script
launches a real headless Chrome browser, points a SelfHealingWebDriver at the
live Pomodoro target app, and requests a DELIBERATELY BROKEN locator. The wrapper
intercepts the NoSuchElementException, scrapes the DOM, scores candidates against
the golden fingerprints in data/pomodoro_3d_fingerprints.json, and heals the
click path automatically -- recording the heal in data/buckets/ui_heals.json.

Prerequisites:
  1. Google Chrome installed.
  2. The target app running:  python demo_target_app.py   (http://127.0.0.1:8000)
"""

import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

from automation_wrapper import SelfHealingWebDriver
import learning_mode
import config

TARGET_URL = "http://127.0.0.1:8000"
BROKEN_LOCATOR = (By.ID, "old-start-btn")  # this id does NOT exist on the page

def main():
    print("🌐 Launching headless Chrome runner...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as e:
        print(f"❌ Could not start Chrome. Is Google Chrome installed? Details: {e}")
        sys.exit(1)

    healing_driver = SelfHealingWebDriver(driver)

    try:
        print(f"➡️  Loading target application: {TARGET_URL}")
        driver.get(TARGET_URL)

        # Learning Mode: auto-build the golden fingerprint baseline if missing.
        learning_mode.ensure_fingerprints(driver, config.POMODORO_FINGERPRINTS_PATH)

        print(f"🔎 Requesting intentionally broken locator: {BROKEN_LOCATOR[0]}='{BROKEN_LOCATOR[1]}'")
        try:
            element = healing_driver.find_element(*BROKEN_LOCATOR)
            print(f"✅ Healed element resolved: <{element.tag_name}> text='{element.text}'")
            print("📡 Real heal logged. Watch the dashboard UI Heuristic Healing tab update!")
        except NoSuchElementException as e:
            print(f"❌ Self-healing could not recover the element: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
