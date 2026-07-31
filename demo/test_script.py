import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
try:
    import config_manager
    config_manager.apply_overrides()
except Exception as e:
    print(f"⚠ Warning: Could not apply config overrides: {e}")

try:
    import selfheal
    selfheal.install(fingerprints="data/fingerprints/normal_fingerprints.json")
    print("✓ Self-healing system enabled")
except Exception as e:
    print(f"⚠ Warning: Could not enable self-healing: {e}")

# 1. Initialize Chrome Driver
driver = webdriver.Chrome()

try:
    
    # 2. Open the local HTML file (adjust path if needed)
    file_path = os.path.abspath("test_page.html")
    driver.get(f"file://{file_path}")
    driver.maximize_window()

    # Setup explicit wait engine
    wait = WebDriverWait(driver, 10)

    # 3. Target elements using ID, Class Name, and Text (XPath)
    
    # Locate Heading using ID
    heading = wait.until(EC.presence_of_element_located((By.ID, "page-heading")))
    print(f"Page Title Found: {heading.text}")

    # Enter Username using ID
    username_field = driver.find_element(By.ID, "username-input")
    username_field.clear()
    username_field.send_keys("test_user")

    # Enter Password using Class Name combination
    password_field = driver.find_element(By.CLASS_NAME, "control-pass")
    password_field.clear()
    password_field.send_keys("SuperSecret123")

    # Target Submit Button using ID and click
    submit_btn = driver.find_element(By.ID, "submit-btn")
    print(f"Clicking button with text: '{submit_btn.text}'")
    submit_btn.click()

    # Target Forgot Password link using visible text (XPath)
    forgot_link = driver.find_element(By.XPATH, "//a[text()='Forgot Password?']")
    print(f"Link target found: {forgot_link.get_attribute('href')}")

    print("\n✅ All Selenium element lookups executed successfully!")

finally:
    # Clean up and close the browser window
    driver.quit()