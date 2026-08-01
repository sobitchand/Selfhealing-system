"""
QA Test Script - Self-Healing Selenium Framework Demo
======================================================
Demonstrates four element-location strategies:
  1. By ID            -> sum-btn
  2. By CSS Selector  -> button.btn-secondary
  3. By XPath (@id)   -> //button[@id='sum-btn']
  4. By XPath (text)  -> //button[normalize-space()='Cancel']

When the page is intact, all four pass without healing.
When attributes are changed in the HTML, the self-healing engine
intercepts NoSuchElementException and repairs the locator automatically.
"""

import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import config_manager
config_manager.apply_overrides()

import selfheal
selfheal.install(fingerprints="data/fingerprints/baseline_fingerprints.json")

# ── Launch browser ──────────────────────────────────────────────────
html_file_path = os.path.abspath("demo_page.html")
file_url = f"file://{html_file_path}"

driver = webdriver.Chrome()

try:
    driver.get(file_url)
    driver.maximize_window()
    print("[INFO] Opened demo page: demo_page.html\n")

    wait = WebDriverWait(driver, 10)

    # ── TEST 1: Submit button via ID ────────────────────────────────
    submit_btn = wait.until(EC.element_to_be_clickable((By.ID, "sum-btn")))
    submit_btn.click()
    print("[PASS] Test 1 - Submit button located by ID")

    status_log = driver.find_element(By.ID, "status-log").text
    assert "Submit Button (by ID) clicked" in status_log
    print(f"       Status: {status_log}")
    time.sleep(1)

    # ── TEST 2: Cancel button via CSS Selector ─────────────────────
    cancel_btn = driver.find_element(By.CSS_SELECTOR, "button.btn-secondary")
    cancel_btn.click()
    print("[PASS] Test 2 - Cancel button located by CSS Selector")

    status_log = driver.find_element(By.ID, "status-log").text
    assert "Cancel Button (by Class) clicked" in status_log
    print(f"       Status: {status_log}")
    time.sleep(1)

    # ── TEST 3: Submit button via Relative XPath ───────────────────
    submit_btn = driver.find_element(By.XPATH, "//button[@id='sum-btn']")
    submit_btn.click()
    print("[PASS] Test 3 - Submit button located by XPath (@id)")
    time.sleep(1)

    # ── TEST 4: Cancel button via XPath text match ─────────────────
    cancel_btn = driver.find_element(By.XPATH, "//button[normalize-space()='Cancel']")
    cancel_btn.click()
    print("[PASS] Test 4 - Cancel button located by XPath (text)")

    print("\n[DONE] All test cases completed successfully.")

finally:
    time.sleep(2)
    driver.quit()
