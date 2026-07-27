"""Chrome factory shared by the pytest fixture and the standalone runner."""

import glob
import os

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


def resolve_chromedriver():
    """Prefer a cached chromedriver so a demo never depends on a live download."""
    cache_glob = os.path.expanduser(
        "~/.wdm/drivers/chromedriver/*/*/chromedriver-win64/chromedriver.exe"
    )
    matches = sorted(glob.glob(cache_glob))
    if matches:
        return matches[-1]
    from webdriver_manager.chrome import ChromeDriverManager
    return ChromeDriverManager().install()


def make_driver(headed=False):
    options = webdriver.ChromeOptions()
    if not headed:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    if headed:
        options.add_argument("--start-maximized")
    return webdriver.Chrome(service=Service(resolve_chromedriver()), options=options)
