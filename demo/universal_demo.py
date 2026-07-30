"""
Universal Demo Runner — works with ANY web application.

    python universal_demo.py [URL] [--headed] [--dashboard]

Examples:
    python universal_demo.py                              # uses default TaskFlow demo
    python universal_demo.py http://localhost:3000        # your React app
    python universal_demo.py https://example.com          # any public site
    python universal_demo.py --headed                     # visible Chrome
    python universal_demo.py --dashboard                  # launch dashboard too

Workflow:
    1. Navigate to URL
    2. Discover all interactive elements
    3. Capture fingerprints (Learning Mode)
    4. Run tests against clean page (baseline)
    5. Mutate the DOM (rename IDs/classes)
    6. Run tests WITHOUT healing (expect failures)
    7. Run tests WITH healing (expect recovery)
    8. Show summary
"""

import os
import sys
import time
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config
import selfheal
import automation_wrapper
from fingerprint_manager import FingerprintManager

DEFAULT_URL = "http://127.0.0.1:8000/"
FINGERPRINT_PATH = os.path.join(config.DATA_DIR, "fingerprints", "universal_fingerprints.json")


def find_chromedriver():
    import glob
    paths = glob.glob(os.path.expanduser(
        "~/.wdm/drivers/chromedriver/*/*/chromedriver-win64/chromedriver.exe"
    ))
    if paths:
        return paths[-1]
    from webdriver_manager.chrome import ChromeDriverManager
    return ChromeDriverManager().install()


def make_driver(headless=True):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver_path = find_chromedriver()
    return webdriver.Chrome(service=Service(driver_path), options=options)


def start_dashboard():
    dash_script = os.path.join(BASE_DIR, "dashboard.py")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", dash_script,
         "--server.port", "8501", "--server.headless", "true"],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    print("Dashboard running at http://localhost:8501")
    return proc


def main():
    # Parse arguments
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]

    url = args[0] if args else DEFAULT_URL
    headed = '--headed' in flags
    with_dashboard = '--dashboard' in flags
    headless = not headed

    # Configure system
    config.ACTIVE_FINGERPRINT_PATH = FINGERPRINT_PATH
    config.POMODORO_FINGERPRINTS_PATH = FINGERPRINT_PATH
    config.SOURCE_HEAL_ENABLED = True

    print("=" * 70)
    print("UNIVERSAL SELF-HEALING DEMO")
    print("=" * 70)
    print(f"Target URL: {url}")
    print(f"Headless:   {headless}")
    print("=" * 70)

    # Start dashboard if requested
    dash_proc = None
    if with_dashboard:
        print("\nStarting dashboard...")
        dash_proc = start_dashboard()

    driver = make_driver(headless=headless)

    try:
        # Phase 1: Discover & Learn
        print(f"\n[Phase 1] Learning from {url}...")
        from auto_test_generator import discover_interactive_elements, discover_and_collect_fingerprints

        discover_and_collect_fingerprints(driver, url, FINGERPRINT_PATH)

        elements = discover_interactive_elements(driver)
        print(f"Discovered {len(elements)} interactive elements")
        for i, el in enumerate(elements[:10]):
            print(f"  {i+1}. <{el['tag']}> id='{el['id']}' text='{el['text'][:30]}'")
        if len(elements) > 10:
            print(f"  ... and {len(elements) - 10} more")

        if not elements:
            print("\nNo interactive elements found. Check the URL.")
            return

        # Phase 2: Baseline test (no mutation)
        print(f"\n[Phase 2] Running baseline tests (no mutation)...")
        from auto_test_generator import generate_test_actions, discover_and_test

        selfheal.install(fingerprints=FINGERPRINT_PATH)
        passed1, failed1, total1 = discover_and_test(driver, url)
        selfheal.uninstall()

        # Phase 3: Mutate DOM
        print(f"\n[Phase 3] Mutating page elements...")
        from dom_mutator import mutate_page

        driver.get(url)
        time.sleep(1)
        changes = mutate_page(driver)
        print(f"Mutated {len(changes)} elements")

        # Phase 4: Test WITHOUT healing
        print(f"\n[Phase 4] Running tests WITHOUT self-healing (expect failures)...")
        passed2, failed2, total2 = discover_and_test(driver, url)

        # Phase 5: Test WITH healing
        print(f"\n[Phase 5] Running tests WITH self-healing (expect recovery)...")
        selfheal.install(fingerprints=FINGERPRINT_PATH)

        # Re-discover elements after mutation (IDs changed)
        from auto_test_generator import discover_interactive_elements
        mutated_elements = discover_interactive_elements(driver)
        print(f"Found {len(mutated_elements)} elements after mutation")

        # Run tests with healing
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import NoSuchElementException

        passed3 = 0
        failed3 = 0
        total3 = 0

        for elem in mutated_elements[:20]:  # Test first 20
            by, value = elem['locator']
            total3 += 1
            try:
                wait = WebDriverWait(driver, 5)
                el = wait.until(EC.element_to_be_clickable((by, value)))
                if elem['tag'] in ['input', 'textarea']:
                    el.clear()
                    el.send_keys("test")
                else:
                    el.click()
                passed3 += 1
                print(f"  PASS: {elem['text'][:30] or elem['id'] or elem['tag']}")
            except NoSuchElementException:
                failed3 += 1
                print(f"  FAIL: {elem['text'][:30] or elem['id'] or elem['tag']}")
            except Exception as e:
                failed3 += 1
                print(f"  FAIL: {type(e).__name__}")

        stats = selfheal.session_stats()
        heals = selfheal.session_heals()

        # Summary
        print(f"\n{'='*70}")
        print("DEMO SUMMARY")
        print(f"{'='*70}")
        print(f"  URL: {url}")
        print(f"  Elements discovered: {len(elements)}")
        print(f"  Elements mutated: {len(changes)}")
        print(f"")
        print(f"  Baseline (clean page) ......... {passed1}/{total1} passed")
        print(f"  Without healing (mutated) ...... {passed2}/{total2} passed")
        print(f"  With self-healing (mutated) .... {passed3}/{total3} passed")
        print(f"  Tests recovered ................ {passed3 - passed2}")
        print(f"  Locator heals performed ........ {stats['heals']}")

        if heals:
            print(f"\n  Healed locators:")
            for h in heals[:10]:
                print(f"    {h['locator']} -> {h['resolved_to']} ({h['confidence']:.1f}%)")
            if len(heals) > 10:
                print(f"    ... and {len(heals) - 10} more")

        if with_dashboard:
            print(f"\n  Dashboard: http://localhost:8501")
            print(f"  Press Ctrl+C to stop everything.")

        print(f"{'='*70}")

        if with_dashboard:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    finally:
        selfheal.uninstall()
        driver.quit()
        if dash_proc:
            dash_proc.terminate()
            dash_proc.wait()


if __name__ == "__main__":
    main()
