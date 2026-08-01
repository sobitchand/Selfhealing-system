"""
A conventional multi-file web application -- index.html, styles.css, app.js.

This exists to settle a question the single-file demo cannot: does the framework
care how the project is laid out? It does not. Selenium sees the DOM *after* the
browser has fetched the stylesheet and executed the script, so a separate
styles.css and app.js are indistinguishable from inline ones by the time any
lookup happens. Nothing here is configured differently from the single-file demo.

Six lookups, six different locator strategies, and an assertion on a value the
JavaScript computes -- so a heal is only correct if it found the functionally
right element, not merely one with a similar name.

    python webapp/test_fine.py                   learn / heal (normal)
    python webapp/test_fine.py --keep-baseline   heal without relearning
    python webapp/test_fine.py --no-heal         plain Selenium, no framework
    python webapp/test_fine.py --headed          watch it in a browser
    python webapp/test_fine.py --refuse          ask for something that does not exist
"""

import glob
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import selfheal

PAGE = "file:///" + os.path.join(HERE, "index.html").replace("\\", "/")

HEAL = "--no-heal" not in sys.argv
LEARN = "--keep-baseline" not in sys.argv
HEADED = "--headed" in sys.argv
REFUSE = "--refuse" in sys.argv


def make_driver():
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


def calculate_a_fine(driver):
    """Six lookups, six strategies. The test body never changes between builds."""
    driver.get(PAGE)

    driver.find_element(By.ID, "member-id").send_keys("B-1042")
    driver.find_element(By.NAME, "overdue-days").send_keys("6")
    Select(driver.find_element(By.CSS_SELECTOR, "#tier")).select_by_visible_text("Standard")
    driver.find_element(By.CLASS_NAME, "btn-calc").click()
    driver.find_element(By.LINK_TEXT, "Fee policy")
    amount = driver.find_element(By.XPATH, "//span[@id='total-fee']").text

    assert amount == "30.00", f"expected fine 30.00, got {amount!r}"
    print(f"PASS - amount due: NPR {amount}")


def safety_gate(driver):
    """Ask for something with no analogue on the page, so the engine must refuse.

    The name matters. Before scoring candidates the engine resolves WHICH tracked
    element a broken locator meant, by string-similarity against the baseline's
    locators, and refuses outright below 40%. A probe that shares a token with a
    real element ('renew-membership-button' scores 43.8% against 'member-id')
    clears that gate and gets scored structurally, which is not what this
    demonstrates. Pick a name that shares no vocabulary with the page.
    """
    driver.get(PAGE)
    print("asking for id='printer-jam-warning' -- no such concept on this page")
    try:
        driver.find_element(By.ID, "printer-jam-warning")
        print("UNEXPECTED: an element was returned. The system guessed!")
    except NoSuchElementException as e:
        print("\nCORRECT: the system refused rather than guessing.")
        print(f"   {str(e).splitlines()[0][:140]}")


def main():
    body = safety_gate if REFUSE else calculate_a_fine

    if not HEAL:
        print("mode: plain Selenium, NO self-healing")
        driver = make_driver()
        try:
            body(driver)
        finally:
            driver.quit()
        return

    print(f"mode: self-healing ON, learning {'OFF (baseline pinned)' if not LEARN else 'ON'}")
    with selfheal.run(app="library", test="refusal" if REFUSE else "fine",
                      learn=False if REFUSE else LEARN):
        driver = make_driver()
        try:
            body(driver)
        finally:
            driver.quit()


if __name__ == "__main__":
    main()
