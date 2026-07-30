import os
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Enable self-healing system
try:
    import selfheal
    selfheal.install()
    print("✓ Self-healing system enabled")
except Exception as e:
    print(f"⚠ Warning: Could not enable self-healing: {e}")

# Setup WebDriver
options = webdriver.ChromeOptions()
# options.add_argument("--headless")  # Uncomment to run headlessly
driver = webdriver.Chrome(options=options)

try:
    # Use HTTP server URL (not file:///)
    base_url = os.environ.get("MY_APP_URL", "http://127.0.0.1:8000")
    html_file = os.environ.get("MY_APP_HTML", "web.html")
    full_url = f"{base_url}/{html_file}"
    
    print(f"\n{'='*60}")
    print(f"Test Configuration:")
    print(f"  Base URL: {base_url}")
    print(f"  HTML File: {html_file}")
    print(f"  Full URL: {full_url}")
    print(f"{'='*60}\n")
    
    print(f"Loading URL: {full_url}")
    driver.get(full_url)
    
    # Wait for page to load
    import time
    time.sleep(2)
    
    print(f"Current URL: {driver.current_url}")
    print(f"Page title: {driver.title}")
    
    # Check if page loaded correctly
    if "404" in driver.page_source or "Not Found" in driver.page_source:
        print("❌ ERROR: Page not found! Make sure the server is running.")
        print("   Run: python -m http.server 8000")
        raise Exception("Page not found - server may not be running")

    wait = WebDriverWait(driver, 10)

    # Test 1: Add a new task
    print("\nRunning Test: Add task...")
    item_input = wait.until(EC.presence_of_element_located((By.ID, "itemInput")))
    add_btn = wait.until(EC.element_to_be_clickable((By.ID, "addBtn")))

    print("  Entering text: 'Learn Selenium'")
    item_input.send_keys("Learn Selenium")
    print("  Clicking Add button...")
    add_btn.click()
    
    # Wait a moment for JavaScript to execute
    import time
    time.sleep(1)
    
    # Check what's in the list
    list_items = driver.find_elements(By.CSS_SELECTOR, "#itemList li")
    print(f"  Found {len(list_items)} items in list")
    
    if len(list_items) == 0:
        print("  ⚠ No items found, checking if button click worked...")
        # Try clicking again with JavaScript
        driver.execute_script("arguments[0].click();", add_btn)
        time.sleep(1)
        list_items = driver.find_elements(By.CSS_SELECTOR, "#itemList li")
        print(f"  After JS click: {len(list_items)} items")

    # Verify item is added
    list_items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#itemList li")))
    assert len(list_items) == 1
    assert "Learn Selenium" in list_items[0].text
    print("Test Passed: Add task.")

    # Test 2: Add a task using the Enter key
    print("Running Test: Add task via Enter key...")
    item_input.clear()
    item_input.send_keys("Build automation" + Keys.RETURN)

    list_items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#itemList li")))
    assert len(list_items) == 2
    assert "Build automation" in list_items[1].text
    print("Test Passed: Add task via Enter key.")

    # Test 3: Delete a specific task
    print("Running Test: Delete specific task...")
    first_item_delete_btn = list_items[0].find_element(By.TAG_NAME, "button")
    first_item_delete_btn.click()

    list_items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#itemList li")))
    assert len(list_items) == 1
    assert "Build automation" in list_items[0].text
    print("Test Passed: Delete specific task.")

    # Test 4: Clear all tasks
    # This will trigger healing when HTML has id="clBtn" instead of "clearBtn"
    print("Running Test: Clear all tasks...")
    clear_btn = driver.find_element(By.ID, "clearBtn")  # Will heal to "clBtn"
    clear_btn.click()

    list_items = driver.find_elements(By.CSS_SELECTOR, "#itemList li")
    assert len(list_items) == 0
    print("Test Passed: Clear all tasks.")

    print("\n=== All tests passed! ===")

finally:
    driver.quit()
