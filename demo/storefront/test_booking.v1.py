"""
Bistro Nova reservation test -- one ordinary Selenium script.

The only framework integration is the `with selfheal.run(...)` line. The test
body never changes: not between the learning run and the healing run, and not
when the developer renames every id and class in app.html. That is the point --
the script is the control, and the only variable is whether the healing layer
is installed.

    python storefront/test_booking.py                   learn / heal (normal)
    python storefront/test_booking.py --keep-baseline   heal without overwriting
                                                        the baseline
    python storefront/test_booking.py --no-heal         plain Selenium, no framework
    python storefront/test_booking.py --headed          watch it in a browser
    python storefront/test_booking.py --refuse          ask for an element that
                                                        exists nowhere
"""

import glob
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException

# One level up from storefront/ is the framework root. This single line is the
# only thing that has to change if the project lives at a different depth.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import selfheal

PAGE = "file:///" + os.path.join(HERE, "app.html").replace("\\", "/")

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


def book_a_table(driver):
    """The test itself. Five lookups, five different locator strategies."""
    driver.get(PAGE)

    driver.find_element(By.ID, "guests").send_keys("4")
    Select(driver.find_element(By.NAME, "slot")).select_by_visible_text("7:30 PM")
    driver.find_element(By.CSS_SELECTOR, ".btn-reserve").click()
    driver.find_element(By.LINK_TEXT, "My reservations")
    deposit = driver.find_element(By.XPATH, "//span[@id='fee']").text

    assert deposit == "1,200.00", f"expected deposit 1,200.00, got {deposit!r}"
    print(f"PASS - deposit due: NPR {deposit}")


def safety_gate(driver):
    """Ask for something with no analogue on the page. The best candidate scores
    below CONFIDENCE_THRESHOLD_LOW, so the engine must refuse rather than guess."""
    driver.get(PAGE)
    print("asking for id='wine-pairing-option' -- no such concept exists on this page")
    try:
        driver.find_element(By.ID, "wine-pairing-option")
        print("UNEXPECTED: an element was returned. The system guessed!")
    except NoSuchElementException as e:
        print("\nCORRECT: the system refused rather than guessing.")
        print(f"   {str(e).splitlines()[0][:140]}")


def main():
    body = safety_gate if REFUSE else book_a_table

    if not HEAL:
        print("mode: plain Selenium, NO self-healing")
        driver = make_driver()
        try:
            body(driver)
        finally:
            driver.quit()
        return

    print(f"mode: self-healing ON, learning {'OFF (baseline pinned)' if not LEARN else 'ON'}")
    with selfheal.run(app="bistro", test="refusal" if REFUSE else "booking",
                      learn=False if REFUSE else LEARN):
        driver = make_driver()
        try:
            body(driver)
        finally:
            driver.quit()


if __name__ == "__main__":
    main()