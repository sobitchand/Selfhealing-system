"""
Comprehensive test suite for the TaskFlow demo app.

Tests 25+ interactive elements across login, navigation, task CRUD,
filters, settings, and modal dialogs. Includes a safety-halt scenario
(locator that cannot be healed) to populate the Alerts tab.

    python test_comprehensive.py

The test uses the self-healing layer. When run against web_demo_broken.html,
all locators fail and the system heals them automatically.
"""

import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

# Enable self-healing
try:
    import selfheal
    selfheal.install()
    print("Self-healing system enabled")
except Exception as e:
    print(f"Warning: Could not enable self-healing: {e}")


def make_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def run_tests(driver, url=None):
    base_url = url or os.environ.get("MY_APP_URL", "http://127.0.0.1:8000")
    html_file = os.environ.get("MY_APP_HTML", "web_demo.html")
    full_url = f"{base_url}/{html_file}"

    print(f"\n{'='*60}")
    print(f"Test Configuration:")
    print(f"  URL: {full_url}")
    print(f"{'='*60}\n")

    driver.get(full_url)
    time.sleep(2)

    wait = WebDriverWait(driver, 10)
    passed = 0
    failed = 0
    total = 0

    def test(name, fn):
        nonlocal passed, failed, total
        total += 1
        try:
            fn()
            passed += 1
            print(f"  PASS: {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {name} - {e}")

    # --- Navigation Tests ---
    def test_nav_dashboard():
        el = wait.until(EC.element_to_be_clickable((By.ID, "nav-dashboard")))
        el.click()
    test("Click Dashboard nav link", test_nav_dashboard)

    def test_nav_tasks():
        el = driver.find_element(By.ID, "nav-tasks")
        el.click()
    test("Click Tasks nav link", test_nav_tasks)

    def test_nav_reports():
        el = driver.find_element(By.ID, "nav-reports")
        el.click()
    test("Click Reports nav link", test_nav_reports)

    def test_nav_settings():
        el = driver.find_element(By.ID, "nav-settings")
        el.click()
    test("Click Settings nav link", test_nav_settings)

    def test_nav_logout():
        el = driver.find_element(By.ID, "nav-logout")
        el.click()
    test("Click Logout nav link", test_nav_logout)

    # --- Stats Verification ---
    def test_stat_total():
        el = driver.find_element(By.ID, "stat-total")
        assert el.text == "3", f"Expected 3, got {el.text}"
    test("Verify total tasks stat", test_stat_total)

    def test_stat_active():
        el = driver.find_element(By.ID, "stat-active")
        assert el.text == "2", f"Expected 2, got {el.text}"
    test("Verify active tasks stat", test_stat_active)

    def test_stat_completed():
        el = driver.find_element(By.ID, "stat-completed")
        assert el.text == "1", f"Expected 1, got {el.text}"
    test("Verify completed tasks stat", test_stat_completed)

    # --- Sidebar Navigation ---
    def test_sidebar_all():
        el = driver.find_element(By.ID, "sidebar-all")
        el.click()
    test("Click sidebar All Tasks", test_sidebar_all)

    def test_sidebar_today():
        el = driver.find_element(By.ID, "sidebar-today")
        el.click()
    test("Click sidebar Today", test_sidebar_today)

    def test_sidebar_week():
        el = driver.find_element(By.ID, "sidebar-week")
        el.click()
    test("Click sidebar This Week", test_sidebar_week)

    def test_sidebar_important():
        el = driver.find_element(By.ID, "sidebar-important")
        el.click()
    test("Click sidebar Important", test_sidebar_important)

    def test_sidebar_completed():
        el = driver.find_element(By.ID, "sidebar-completed")
        el.click()
    test("Click sidebar Completed", test_sidebar_completed)

    # --- Add Task Form ---
    def test_task_title_input():
        el = driver.find_element(By.ID, "task-title")
        el.clear()
        el.send_keys("New test task")
    test("Enter task title", test_task_title_input)

    def test_task_desc_input():
        el = driver.find_element(By.ID, "task-description")
        el.send_keys("Test description")
    test("Enter task description", test_task_desc_input)

    def test_task_priority_select():
        el = driver.find_element(By.ID, "task-priority")
        el.click()
    test("Click priority dropdown", test_task_priority_select)

    def test_task_category_select():
        el = driver.find_element(By.ID, "task-category")
        el.click()
    test("Click category dropdown", test_task_category_select)

    def test_task_due_date():
        el = driver.find_element(By.ID, "task-due")
        el.send_keys("2026-08-01")
    test("Enter due date", test_task_due_date)

    def test_btn_add_task():
        el = driver.find_element(By.ID, "btn-add-task")
        el.click()
        time.sleep(1)
    test("Click Add Task button", test_btn_add_task)

    def test_btn_clear_form():
        el = driver.find_element(By.ID, "btn-clear-form")
        el.click()
    test("Click Clear Form button", test_btn_clear_form)

    # --- Search & Filter ---
    def test_search_input():
        el = driver.find_element(By.ID, "search-input")
        el.send_keys("Review")
    test("Enter search text", test_search_input)

    def test_btn_search():
        el = driver.find_element(By.ID, "btn-search")
        el.click()
    test("Click Search button", test_btn_search)

    def test_btn_clear_search():
        el = driver.find_element(By.ID, "btn-clear-search")
        el.click()
    test("Click Clear Search button", test_btn_clear_search)

    def test_filter_all():
        el = driver.find_element(By.ID, "filter-all")
        el.click()
    test("Click filter All", test_filter_all)

    def test_filter_active():
        el = driver.find_element(By.ID, "filter-active")
        el.click()
    test("Click filter Active", test_filter_active)

    def test_filter_completed():
        el = driver.find_element(By.ID, "filter-completed")
        el.click()
    test("Click filter Completed", test_filter_completed)

    def test_filter_high():
        el = driver.find_element(By.ID, "filter-high")
        el.click()
    test("Click filter High Priority", test_filter_high)

    # --- Task Actions ---
    def test_btn_complete():
        el = driver.find_element(By.ID, "btn-complete-1")
        el.click()
    test("Click Complete task button", test_btn_complete)

    def test_btn_edit():
        el = driver.find_element(By.ID, "btn-edit-1")
        el.click()
    test("Click Edit task button", test_btn_edit)

    def test_btn_delete():
        el = driver.find_element(By.ID, "btn-delete-2")
        el.click()
    test("Click Delete task button", test_btn_delete)

    def test_btn_undo():
        el = driver.find_element(By.ID, "btn-undo-3")
        el.click()
    test("Click Undo completed button", test_btn_undo)

    def test_btn_complete_all():
        el = driver.find_element(By.ID, "btn-complete-all")
        el.click()
    test("Click Complete All button", test_btn_complete_all)

    def test_btn_clear_completed():
        el = driver.find_element(By.ID, "btn-clear-completed")
        el.click()
    test("Click Clear Completed button", test_btn_clear_completed)

    def test_btn_export():
        el = driver.find_element(By.ID, "btn-export-tasks")
        el.click()
    test("Click Export Tasks button", test_btn_export)

    # --- Settings ---
    def test_setting_notifications():
        el = driver.find_element(By.ID, "setting-notifications")
        el.click()
    test("Toggle notifications checkbox", test_setting_notifications)

    def test_setting_autosave():
        el = driver.find_element(By.ID, "setting-auto-save")
        el.click()
    test("Toggle auto-save checkbox", test_setting_autosave)

    def test_setting_darkmode():
        el = driver.find_element(By.ID, "setting-dark-mode")
        el.click()
    test("Toggle dark mode checkbox", test_setting_darkmode)

    def test_setting_theme():
        el = driver.find_element(By.ID, "setting-theme")
        el.click()
    test("Click theme dropdown", test_setting_theme)

    def test_btn_save_settings():
        el = driver.find_element(By.ID, "btn-save-settings")
        el.click()
    test("Click Save Settings button", test_btn_save_settings)

    def test_btn_reset_settings():
        el = driver.find_element(By.ID, "btn-reset-settings")
        el.click()
    test("Click Reset Settings button", test_btn_reset_settings)

    # --- Modal ---
    def test_btn_save_edit():
        el = driver.find_element(By.ID, "btn-save-edit")
        el.click()
    test("Click Save Changes in modal", test_btn_save_edit)

    def test_btn_cancel_edit():
        el = driver.find_element(By.ID, "btn-cancel-edit")
        el.click()
    test("Click Cancel in modal", test_btn_cancel_edit)

    # --- Safety Halt Scenario ---
    # This locator does NOT exist in the app and has no similar element,
    # so the healing engine should refuse to heal (confidence < 20%).
    # This populates the Alerts tab with a CRITICAL FAULT.
    def test_safety_halt():
        try:
            el = driver.find_element(By.ID, "zzz-nonexistent-element-999")
            el.click()
        except NoSuchElementException:
            # Expected - the element doesn't exist
            # The healing engine should detect this and halt
            pass
    test("Safety halt: nonexistent element (should trigger alert)", test_safety_halt)

    # --- Results ---
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"{'='*60}")

    return passed, failed, total


if __name__ == "__main__":
    driver = make_driver()
    try:
        run_tests(driver)
    finally:
        driver.quit()
