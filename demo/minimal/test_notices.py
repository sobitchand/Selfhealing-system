"""
The smallest possible self-healing demo.

`page.html` has no ids, no CSS file, no JavaScript, no form controls -- a
heading, two paragraphs and a link, identified only by class. It exists to answer
one question: does the framework need a rich page to work, or does it work on
whatever you point it at?

The five lookups use four different locator strategies, and the last one is a
NESTED lookup (element.find_element) to show that healing follows page-object
style code, not just top-level driver calls.

    python minimal/test_notices.py                   learn / heal (normal)
    python minimal/test_notices.py --keep-baseline   heal without relearning
    python minimal/test_notices.py --no-heal         plain Selenium, no framework
    python minimal/test_notices.py --headed          watch it in a browser
"""

import glob
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

# One level up from minimal/ is the framework root. This single line is the only
# thing that changes if the project lives at a different depth.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import selfheal

PAGE = "file:///" + os.path.join(HERE, "page.html").replace("\\", "/")

HEAL = "--no-heal" not in sys.argv
LEARN = "--keep-baseline" not in sys.argv
HEADED = "--headed" in sys.argv


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


def read_the_board(driver):
    """Four locator strategies, and one lookup nested inside another element."""
    driver.get(PAGE)

    heading = driver.find_element(By.CLASS_NAME, "board-title")
    board = driver.find_element(By.CSS_SELECTOR, ".notice-list")
    first = driver.find_element(By.XPATH, "//p[@class='notice-item']")
    link = driver.find_element(By.LINK_TEXT, "Older notices")

    # Nested: resolved against `board`, not against the driver. Page objects are
    # built out of calls like this one.
    nested = board.find_element(By.CLASS_NAME, "notice-item")

    assert heading.text == "Department Notice Board", f"heading was {heading.text!r}"
    assert "Library closes" in first.text, f"first notice was {first.text!r}"
    assert nested.text == first.text, "nested lookup found a different element"
    assert link.is_displayed(), "archive link not visible"

    print(f"PASS - heading: {heading.text!r}")
    print(f"       notice : {first.text!r}")


def main():
    if not HEAL:
        print("mode: plain Selenium, NO self-healing")
        driver = make_driver()
        try:
            read_the_board(driver)
        finally:
            driver.quit()
        return

    print(f"mode: self-healing ON, learning {'OFF (baseline pinned)' if not LEARN else 'ON'}")
    with selfheal.run(app="notices", test="read_board", learn=LEARN):
        driver = make_driver()
        try:
            read_the_board(driver)
        finally:
            driver.quit()


if __name__ == "__main__":
    main()
