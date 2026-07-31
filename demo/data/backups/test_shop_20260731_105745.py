"""
An ordinary Selenium script. It knows nothing about healing beyond the single
`with selfheal.run(...)` line, and it is NOT edited between Day 1 and Day 2.

    python examples/shop/test_shop.py
"""

import glob
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import selfheal

PAGE = "file:///" + os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html").replace("\\", "/")


def make_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    cached = sorted(glob.glob(os.path.expanduser(
        "~/.wdm/drivers/chromedriver/*/*/chromedriver-win64/chromedriver.exe")))
    if cached:
        return webdriver.Chrome(service=Service(cached[-1]), options=options)
    from webdriver_manager.chrome import ChromeDriverManager
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def main():
    with selfheal.run(app="shop", test="add_to_cart"):
        driver = make_driver()
        try:
            driver.get(PAGE)

            # Five different locator strategies, on purpose.
            driver.find_element(By.ID, "qty").clear()
            driver.find_element(By.NAME, "quantity").send_keys("3")
            driver.find_element(By.CSS_SELECTOR, ".btn-main").click()
            driver.find_element(By.LINK_TEXT, "Proceed to checkout")
            count = driver.find_element(By.XPATH, "//span[@id='cart-count']").text

            assert count == "3", f"expected 3 in cart, got {count!r}"
            print(f"PASS — cart shows {count}")
        finally:
            driver.quit()


if __name__ == "__main__":
    main()
