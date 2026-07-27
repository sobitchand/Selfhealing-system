"""
Functional QA suite for the Pomodoro timer.

Plain Selenium + Page Objects. Nothing in this file imports, configures or is
aware of the self-healing system -- it is run unchanged both with and without
the healing layer installed, which is what makes the comparison meaningful.

Run with pytest:      pytest tests/ --self-heal
Run without pytest:   python tests/runner.py --heal
"""

import time

from pages.pomodoro_page import PomodoroPage


def test_start_button_starts_the_timer(driver):
    """Clicking START begins the countdown and the button becomes PAUSE."""
    page = PomodoroPage(driver).open()
    assert page.start_button_label() == "START"

    page.start()

    page.wait_for_label("PAUSE")
    assert page.start_button_label() == "PAUSE"


def test_start_button_toggles_to_pause_and_back(driver):
    """START is a toggle: a second click pauses the run."""
    page = PomodoroPage(driver).open()

    page.start()
    page.wait_for_label("PAUSE")

    page.start()

    page.wait_for_label("START")
    assert page.start_button_label() == "START"


def test_reset_restores_the_focus_duration(driver):
    """RESET returns a running focus session to its full 25:00."""
    page = PomodoroPage(driver).open()

    page.start()
    time.sleep(1.4)  # let at least one second tick off
    assert page.time_remaining() != "25:00", "timer never counted down"

    page.reset()

    assert page.time_remaining() == "25:00"


def test_skip_increments_the_pomodoro_counter(driver):
    """Skipping a focus session still credits a completed pomodoro."""
    page = PomodoroPage(driver).open()
    assert page.pomodoro_count() == "0"

    page.skip()

    assert page.pomodoro_count() == "1"


def test_short_break_mode_sets_five_minutes(driver):
    """Switching to Short Break reloads the 5 minute duration."""
    page = PomodoroPage(driver).open()

    page.switch_to_short_break()

    assert page.time_remaining() == "05:00"
