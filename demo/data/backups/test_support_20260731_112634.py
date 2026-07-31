"""
An ordinary Selenium test. The only framework line is `with selfheal.run(...)`.
This file is NOT edited when the page changes.
"""

import glob
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

FRAMEWORK = r"D:\Selfhealing-system\demo"
sys.path.insert(0, FRAMEWORK)
import selfheal

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "file:///" + os.path.join(HERE, "index.html").replace("\\", "/")


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
    with selfheal.run(app="support", test="create_ticket"):
        driver = make_driver()
        try:
            driver.get(PAGE)

            driver.find_element(By.ID, "full-name").send_keys("Aayush")
            driver.find_element(By.NAME, "email").send_keys("aayush@example.com")
            driver.find_element(By.ID, "message").send_keys("Cannot log in")
            driver.find_element(By.LINK_TEXT, "Need help?")
            driver.find_element(By.CSS_SELECTOR, ".btn-submit").click()

            status = driver.find_element(By.XPATH, "//div[@id='status']").text
            assert "Ticket created for Aayush" in status, f"unexpected status: {status!r}"
            print(f"PASS - {status}")
        finally:
            driver.quit()


if __name__ == "__main__":
    main()
