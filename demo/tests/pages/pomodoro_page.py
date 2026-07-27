"""
Page Object for the Pomodoro timer application.

Ordinary QA code: locators in one place, explicit waits, no knowledge of the
self-healing layer whatsoever. This file is the CONTROL in the experiment -- it
is byte-identical between the baseline run and the healed run.
"""

import os

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")
TIMEOUT = float(os.environ.get("QA_TIMEOUT", "5"))


class PomodoroPage:
    # --- locators (recorded against the build QA signed off on) -------------
    START_BUTTON = (By.ID, "start-btn")
    RESET_BUTTON = (By.ID, "reset-btn")
    SKIP_BUTTON = (By.ID, "skip-btn")
    FOCUS_TAB = (By.ID, "btn-focus")
    SHORT_BREAK_TAB = (By.ID, "btn-short")
    TIME_DISPLAY = (By.ID, "time-display")
    POMODORO_COUNT = (By.ID, "stat-pomodoros")

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, TIMEOUT)

    # --- navigation ---------------------------------------------------------
    def open(self):
        self.driver.get(APP_URL)
        self.wait.until(EC.presence_of_element_located(self.TIME_DISPLAY))
        return self

    # --- actions ------------------------------------------------------------
    def _click(self, locator):
        self.wait.until(EC.element_to_be_clickable(locator)).click()

    def start(self):
        self._click(self.START_BUTTON)

    def reset(self):
        self._click(self.RESET_BUTTON)

    def skip(self):
        self._click(self.SKIP_BUTTON)

    def switch_to_short_break(self):
        self._click(self.SHORT_BREAK_TAB)

    # --- state --------------------------------------------------------------
    def start_button_label(self):
        return self.driver.find_element(*self.START_BUTTON).text.strip()

    def time_remaining(self):
        return self.driver.find_element(*self.TIME_DISPLAY).text.strip()

    def pomodoro_count(self):
        return self.driver.find_element(*self.POMODORO_COUNT).text.strip()

    def wait_for_label(self, expected):
        self.wait.until(
            lambda d: d.find_element(*self.START_BUTTON).text.strip() == expected
        )
