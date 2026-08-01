"""
Zero-touch integration: bolt the self-healing layer onto a Selenium QA suite
that was never written with healing in mind.

    import selfheal
    selfheal.install()          # <- the whole integration

    # ...your existing, unmodified test code...

Instead of asking the test author to swap their driver for a wrapper, this
patches Selenium's own lookup methods. Every driver the suite creates -- however
deep inside a fixture, a page-object factory or a third-party helper -- heals
from that point on, including:

  * driver.find_element / driver.find_elements
  * element.find_element / element.find_elements   (nested page-object lookups)
  * WebDriverWait(...).until(EC....)                (the conditions call
                                                     find_element internally, so
                                                     a heal prevents the timeout)

Restore stock Selenium with selfheal.uninstall(). Nothing else in the suite
changes -- which is the point: the QA script under test is the control, and the
only variable is whether this layer is installed.
"""

import os
from contextlib import contextmanager

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

import automation_wrapper as _wrapper
import config

_originals = {}


def is_installed():
    return bool(_originals)


def install(fingerprints=None, heal_find_elements=None):
    """Patch Selenium in-process. Idempotent.

    fingerprints: optional path to a golden-fingerprint registry, so one runner
    can heal different applications against different baselines.

    heal_find_elements: also heal find_elements when it returns an empty list.
    Off by default -- an empty list is a legitimate answer ("no error banners
    on screen"), so healing it converts every true absence into a false match.
    Enable only for a suite whose find_elements calls are all expected to match.
    """
    if _originals:
        return False

    # If caller explicitly passed True/False, respect it; otherwise use default from config
    if heal_find_elements is None:
        _wrapper.HEAL_FIND_ELEMENTS = bool(getattr(config, 'HEAL_FIND_ELEMENTS', False))
    else:
        _wrapper.HEAL_FIND_ELEMENTS = bool(heal_find_elements)

    if fingerprints:
        config.ACTIVE_FINGERPRINT_PATH = os.path.abspath(fingerprints)
        config.POMODORO_FINGERPRINTS_PATH = config.ACTIVE_FINGERPRINT_PATH
        _wrapper._engine = None  # rebuilt against the new baseline on next heal

    _originals["driver_find_element"] = WebDriver.find_element
    _originals["driver_find_elements"] = WebDriver.find_elements
    _originals["element_find_element"] = WebElement.find_element
    _originals["element_find_elements"] = WebElement.find_elements

    def driver_find_element(self, by=None, value=None):
        try:
            element = _originals["driver_find_element"](self, by, value)
            _wrapper._capture_on_success(element, by, value)
            return element
        except NoSuchElementException:
            if _wrapper.healing_in_progress():
                raise
            return _wrapper.attempt_heal(self, by, value)

    def driver_find_elements(self, by=None, value=None):
        found = _originals["driver_find_elements"](self, by, value)
        if found:
            _wrapper._capture_list_on_success(found, by, value)
        if found or _wrapper.healing_in_progress() or not _wrapper.HEAL_FIND_ELEMENTS:
            return found
        return _wrapper.attempt_heal_list(self, by, value)

    def element_find_element(self, by=None, value=None):
        try:
            element = _originals["element_find_element"](self, by, value)
            _wrapper._capture_on_success(element, by, value)
            return element
        except NoSuchElementException:
            if _wrapper.healing_in_progress():
                raise
            return _wrapper.attempt_heal(self, by, value)

    def element_find_elements(self, by=None, value=None):
        found = _originals["element_find_elements"](self, by, value)
        if found:
            _wrapper._capture_list_on_success(found, by, value)
        if found or _wrapper.healing_in_progress() or not _wrapper.HEAL_FIND_ELEMENTS:
            return found
        return _wrapper.attempt_heal_list(self, by, value)

    WebDriver.find_element = driver_find_element
    WebDriver.find_elements = driver_find_elements
    WebElement.find_element = element_find_element
    WebElement.find_elements = element_find_elements
    return True


def uninstall():
    """Restore stock Selenium."""
    if not _originals:
        return False
    WebDriver.find_element = _originals["driver_find_element"]
    WebDriver.find_elements = _originals["driver_find_elements"]
    WebElement.find_element = _originals["element_find_element"]
    WebElement.find_elements = _originals["element_find_elements"]
    _originals.clear()
    return True


# Re-exported so a runner can report what the layer did without importing the
# internals.
reset_session = _wrapper.reset_session
session_heals = _wrapper.session_heals
session_stats = _wrapper.session_stats


@contextmanager
def learning_mode(driver):
    """Context manager that enables inline learning for the duration of a block.

    Usage (report §3.4.2 — Learning Mode bound to a passing run):

        with selfheal.learning_mode(driver):
            run_tests(driver)  # every successful find_element captures a fingerprint

    Fingerprints are persisted to disk when the block exits. Healing is
    suppressed during learning so the discovery pass cannot generate heals
    of its own (report §3.4.5 safeguard).
    """
    _wrapper.enable_learning(driver)
    try:
        with _wrapper.suppressed():
            yield
    finally:
        _wrapper.disable_learning()


def learn_baseline(driver, url=None, force=False):
    """Capture / refresh the golden fingerprint baseline from a KNOWN-GOOD build.
    Real usage: point this at staging before a release, then run the suite
    against the refactored build. Never learn from a broken page -- that would
    bake the fault into the baseline.
    """
    from fingerprint_manager import FingerprintManager
    import learning_mode

    if url:
        driver.get(url)

    # Learning must never heal. The scan probes for tags that may legitimately
    # be absent, and healing those probes both invents matches and fills the
    # dashboard with heals and alerts produced by our own discovery pass.
    with _wrapper.suppressed():
        if force:
            return FingerprintManager(
                driver, fingerprint_path=config.ACTIVE_FINGERPRINT_PATH
            ).scan_interactive()
        return learning_mode.ensure_fingerprints(
            driver, config.ACTIVE_FINGERPRINT_PATH
        )
