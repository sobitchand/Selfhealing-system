"""
Day 1 → Day 2 self-healing demo runner for the Classes/IDs/Path-Classes app.

Day 1: Open index.html, run the QA test (passes), capture Golden Fingerprints
       via inline learning.
Day 2: Open index_broken.html (IDs/classes/paths renamed), run the SAME test
       with healing — broken locators are intercepted and repaired.
"""
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

import config
import selfheal
import automation_wrapper
from fingerprint_manager import FingerprintManager

DAY1_HTML = os.path.join(BASE_DIR, "index.html")
DAY2_HTML = os.path.join(BASE_DIR, "index_broken.html")
FP_PATH = os.path.join(config.DATA_DIR, "fingerprints", "classes_ids_paths_fingerprints.json")


def make_driver(headless=True):
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver_path = ChromeDriverManager().install()
    return webdriver.Chrome(service=Service(driver_path), options=options)


def run_tests(driver, html_path):
    """The QA test logic — identical on Day 1 and Day 2 (unmodified)."""
    driver.get(f"file://{html_path}")
    time.sleep(0.5)
    wait = WebDriverWait(driver, 5)
    passed = 0
    failed = 0
    total = 3

    # Test 1: Class-based buttons
    try:
        all_buttons = driver.find_elements(By.CLASS_NAME, "btn")
        if len(all_buttons) == 4:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL test_button_classes: expected 4 buttons, found {len(all_buttons)}")

        primary_btn = driver.find_element(By.CSS_SELECTOR, "button.btn-primary")
        success_btn = driver.find_element(By.CSS_SELECTOR, "button.btn-success")
        outline_btn = driver.find_element(By.CSS_SELECTOR, "button.btn-outline")

        assert primary_btn.text == "Primary Button"
        assert success_btn.text == "Success Button"
        assert outline_btn.text == "Outline Button"
        primary_btn.click()
        print(f"  PASS test_button_classes: all 3 class-based buttons found")
    except Exception as e:
        if "primary_btn" not in dir():
            failed += 1
            print(f"  FAIL test_button_classes: {type(e).__name__}: {e}")

    # Test 2: Unique ID
    try:
        special_btn = driver.find_element(By.ID, "special-button")
        assert special_btn.is_displayed()
        assert special_btn.text == "Unique Gradient Button"
        header = driver.find_element(By.ID, "custom-header")
        assert "HTML Classes, IDs, and Path Classes" in header.text
        print(f"  PASS test_unique_id_button: ID-based elements found")
        passed += 1
    except Exception as e:
        failed += 1
        print(f"  FAIL test_unique_id_button: {type(e).__name__}: {e}")

    # Test 3: SVG Path classes & hover
    try:
        outer_ring = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "path.path-outer-ring"))
        )
        assert outer_ring is not None
        heart_path = driver.find_element(By.CSS_SELECTOR, "path.path-core-icon")
        initial_color = heart_path.value_of_css_property("fill")
        actions = ActionChains(driver)
        actions.move_to_element(heart_path).perform()
        time.sleep(0.5)
        hover_color = heart_path.value_of_css_property("fill")
        assert initial_color != hover_color, "SVG Path color did not change on hover"
        print(f"  PASS test_svg_path_classes: SVG paths found, hover works")
        passed += 1
    except Exception as e:
        failed += 1
        print(f"  FAIL test_svg_path_classes: {type(e).__name__}: {e}")

    return passed, failed, total


def main():
    headless = "--headed" not in sys.argv

    config.ACTIVE_FINGERPRINT_PATH = FP_PATH
    config.POMODORO_FINGERPRINTS_PATH = FP_PATH
    config.SOURCE_HEAL_ENABLED = False
    config.APPROVAL_MODE_ENABLED = False

    if os.path.exists(FP_PATH):
        os.remove(FP_PATH)
    os.makedirs(os.path.dirname(FP_PATH), exist_ok=True)

    print("=" * 70)
    print("DAY 1 → DAY 2 SELF-HEALING DEMO")
    print("=" * 70)

    # ---- DAY 1: Learn fingerprints from passing test ----
    print("\n--- DAY 1: Baseline + Learning ---")
    driver = make_driver(headless=headless)
    try:
        selfheal.install(fingerprints=FP_PATH, heal_find_elements=False)

        # Pre-scan (captures all elements with id, text, or class)
        with automation_wrapper.suppressed():
            mgr = FingerprintManager(driver, fingerprint_path=FP_PATH)
            driver.get(f"file://{DAY1_HTML}")
            time.sleep(1)
            mgr.scan_interactive()

        # Inline learning: run the test, every successful find captures a fingerprint
        print("\nRunning QA test on Day 1 (should pass)...")
        with selfheal.learning_mode(driver):
            p1, f1, t1 = run_tests(driver, DAY1_HTML)
        print(f"\nDay 1 result: {p1}/{t1} passed")

        # Check what fingerprints we captured
        import json
        with open(FP_PATH) as fp_file:
            fps = json.load(fp_file)
        print(f"Golden Fingerprints captured: {len(fps)}")
        for key in sorted(fps.keys()):
            fp = fps[key]
            print(f"  {key}: tag={fp['tag_name']}, text='{fp.get('inner_text','')[:30]}', "
                  f"class='{fp.get('css_class','')[:30]}', locator={fp.get('locator_by')}='{fp.get('locator_value','')}'")
    finally:
        selfheal.uninstall()
        driver.quit()

    # ---- DAY 2: Same test, broken HTML, with healing ----
    print("\n--- DAY 2: Refactored HTML + Self-Healing ---")
    print("Changes: btn→button-style, btn-primary→primary-style, special-button→unique-action-btn,")
    print("         custom-header→main-title, path-outer-ring→svg-outer-circle, path-core-icon→svg-heart-shape")

    driver = make_driver(headless=headless)
    try:
        selfheal.install(fingerprints=FP_PATH, heal_find_elements=False)
        automation_wrapper.reset_session()

        print("\nRunning SAME QA test on Day 2 (broken HTML, with healing)...")
        p2, f2, t2 = run_tests(driver, DAY2_HTML)
        print(f"\nDay 2 result: {p2}/{t2} passed")

        stats = selfheal.session_stats()
        heals = selfheal.session_heals()
        print(f"\nHeals performed: {stats['heals']}")
        for h in heals:
            print(f"  {h['locator']} -> {h['resolved_to']} "
                  f"(confidence: {h['confidence']:.1f}%, policy: {h['policy']})")

        # Show dashboard log details
        import store
        ui_heals = store.read("ui_heals")
        if ui_heals:
            print(f"\n--- Dashboard Heal Log ({len(ui_heals)} entries) ---")
            for h in ui_heals:
                print(f"  Original: {h.get('broken_selector')}")
                print(f"  Repaired: {h.get('recovered_selector')}")
                print(f"  Confidence: {h.get('confidence_score')}%")
                print(f"  Reason: {h.get('reason', 'N/A')}")
                print(f"  Recommendation: {h.get('recommendation', 'N/A')}")
                print(f"  R1-R4: {h.get('details', {}).get('component_scores', {})}")
                print()
    finally:
        selfheal.uninstall()
        driver.quit()

    print("=" * 70)
    print(f"SUMMARY: Day 1 = {p1}/{t1}, Day 2 = {p2}/{t2}, Heals = {stats['heals']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
