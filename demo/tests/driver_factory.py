"""Browser factory shared by the pytest fixture and the standalone runner.

Supports Chrome and Firefox. Chrome is the default; Firefox can be selected
via make_driver(browser="firefox") or the --browser flag in runners.
"""

import glob
import os

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService


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


def resolve_geckodriver():
    """Prefer a cached geckodriver so a demo never depends on a live download."""
    cache_glob = os.path.expanduser(
        "~/.wdm/drivers/geckodriver/*/*/geckodriver.exe"
    )
    matches = sorted(glob.glob(cache_glob))
    if matches:
        return matches[-1]
    from webdriver_manager.firefox import GeckoDriverManager
    return GeckoDriverManager().install()


def make_driver(browser="chrome", headed=False):
    """Create a WebDriver instance for the specified browser.
    
    Args:
        browser: "chrome" or "firefox"
        headed: if True, run browser visibly; if False, run headless
    
    Returns:
        WebDriver instance
    """
    if browser == "firefox":
        options = webdriver.FirefoxOptions()
        if not headed:
            options.add_argument("--headless")
        if headed:
            options.add_argument("--width=1920")
            options.add_argument("--height=1080")
        return webdriver.Firefox(service=FirefoxService(resolve_geckodriver()), options=options)
    
    # Default: Chrome
    options = webdriver.ChromeOptions()
    if not headed:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    if headed:
        options.add_argument("--start-maximized")
    return webdriver.Chrome(service=ChromeService(resolve_chromedriver()), options=options)
