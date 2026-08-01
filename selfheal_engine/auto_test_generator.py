"""
Auto Test Generator — discovers interactive elements on ANY page and generates
test actions dynamically. No hardcoded element IDs needed.

Usage:
    from auto_test_generator import discover_and_test
    passed, failed, total = discover_and_test(driver, url)

This works with any real website, not just our demo app.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, ElementNotInteractableException, StaleElementReferenceException
)


def discover_interactive_elements(driver, max_elements=30):
    """
    Find all interactive elements on the current page.
    Returns list of {tag, id, text, type, locator} dicts.
    """
    elements = []
    tags = ['button', 'a', 'input', 'select', 'textarea', '[onclick]', '[role="button"]']

    for tag in tags:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, tag)
            for el in els[:5]:  # Max 5 per tag type
                try:
                    if not el.is_displayed():
                        continue

                    el_id = el.get_attribute('id') or ''
                    el_text = (el.text or el.get_attribute('value') or '').strip()[:50]
                    el_type = el.get_attribute('type') or el.tag_name
                    el_class = el.get_attribute('class') or ''

                    # Build a locator strategy
                    if el_id:
                        locator = (By.ID, el_id)
                    elif el_text:
                        locator = (By.LINK_TEXT if el.tag_name == 'a' else By.XPATH,
                                   f"//*[text()='{el_text}']")
                    elif el_class:
                        locator = (By.CSS_SELECTOR, f"{el.tag_name}.{el_class.split()[0]}")
                    else:
                        continue  # Skip unlocatable elements

                    elements.append({
                        'tag': el.tag_name,
                        'id': el_id,
                        'text': el_text,
                        'type': el_type,
                        'class': el_class,
                        'locator': locator,
                    })
                except (StaleElementReferenceException, ElementNotInteractableException):
                    continue
        except NoSuchElementException:
            continue

        if len(elements) >= max_elements:
            break

    return elements[:max_elements]


def generate_test_actions(elements):
    """
    Generate test actions for discovered elements.
    Returns list of (action_name, action_fn) tuples.
    """
    actions = []

    for elem in elements:
        by, value = elem['locator']
        tag = elem['tag']
        el_id = elem['id']
        el_text = elem['text']

        # Generate a human-readable name
        if el_id:
            name = f"Interact with #{el_id} ({tag})"
        elif el_text:
            name = f"Interact with '{el_text[:30]}' ({tag})"
        else:
            name = f"Interact with {tag} element"

        # Generate the action function
        def make_action(by, value, tag, el_id):
            def action(driver, wait):
                el = wait.until(EC.element_to_be_clickable((by, value)))
                if tag in ['input', 'textarea']:
                    el.clear()
                    el.send_keys("test")
                else:
                    el.click()
                time.sleep(0.3)
                return True
            return action

        actions.append((name, make_action(by, value, tag, el_id)))

    return actions


def discover_and_test(driver, url, wait_time=10):
    """
    Full workflow: navigate to URL, discover elements, generate tests, run them.
    Returns (passed, failed, total).
    """
    print(f"\nNavigating to: {url}")
    driver.get(url)
    time.sleep(2)

    wait = WebDriverWait(driver, wait_time)

    # Discover elements
    print("Discovering interactive elements...")
    elements = discover_interactive_elements(driver)
    print(f"Found {len(elements)} interactive elements")

    if not elements:
        print("No interactive elements found on page")
        return 0, 0, 0

    # Generate test actions
    actions = generate_test_actions(elements)
    print(f"Generated {len(actions)} test actions")

    # Run tests
    passed = 0
    failed = 0
    total = len(actions)

    for name, action_fn in actions:
        try:
            action_fn(driver, wait)
            passed += 1
            print(f"  PASS: {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {name} - {type(e).__name__}")

    print(f"\nResults: {passed}/{total} passed, {failed} failed")
    return passed, failed, total


def discover_and_collect_fingerprints(driver, url, fingerprint_path):
    """
    Navigate to URL and capture fingerprints for all interactive elements.
    Returns the number of fingerprints captured.
    """
    print(f"\nLearning fingerprints from: {url}")
    driver.get(url)
    time.sleep(2)

    import automation_wrapper
    import learning_mode

    with automation_wrapper.suppressed():
        count = learning_mode.ensure_fingerprints(driver, fingerprint_path)

    print(f"Captured {count} fingerprints")
    return count
