"""
Healing & Execution Layer -- the seam between an ordinary Selenium QA script and
the rule-based healing engine.

Three integration levels are supported, all sharing the one heal core below:

  1. Transparent proxy   driver = SelfHealingWebDriver(webdriver.Chrome())
                         Every other driver call passes straight through, so the
                         wrapper is substitutable for a real driver (waits, page
                         objects, execute_script, quit(), ...).
  2. Zero-touch patch    import selfheal; selfheal.install()
                         Patches Selenium itself, so an existing test file heals
                         with no source change at all. See selfheal.py.
  3. pytest             pytest --self-heal  (tests/conftest.py)

Explicit waits are covered for free by both 1 and 2: WebDriverWait's expected
conditions call find_element internally, so a heal inside find_element turns
what would have been a TimeoutException into a passing wait.
"""

import threading
import time
from contextlib import contextmanager

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from healing_engine import UIHeuristicEngine
from handlers import handle_active_heal
import dom_features
import feedback
import source_healer
import config


# --------------------------------------------------------------------------
# Re-entrancy guard.
#
# The heal path itself drives the browser (scrape the DOM, re-grab the winning
# element). Once Selenium is monkey-patched those calls come back through the
# interceptor, so without this a failed lookup inside a heal would recurse.
# While the guard is held, every interceptor degrades to the raw Selenium call.
# --------------------------------------------------------------------------
_local = threading.local()


def healing_in_progress():
    return getattr(_local, "active", False)


@contextmanager
def _guard():
    previous = getattr(_local, "active", False)
    _local.active = True
    try:
        yield
    finally:
        _local.active = previous


# --------------------------------------------------------------------------
# Per-process heal session: audit log + resolved-locator cache.
#
# The cache matters for real QA suites. An explicit wait polls find_element
# every ~500ms, and a page object may look the same element up in a dozen
# places; without it a single stale locator would be re-scored (and re-logged)
# on every poll. We score once, remember the live xpath the heal resolved to,
# and re-use it for the rest of the run -- re-validating on each use so a cache
# entry that goes stale falls back to a fresh heal.
# --------------------------------------------------------------------------
_session = {"heals": [], "cache": {}, "cache_hits": 0}


def reset_session():
    _session["heals"] = []
    _session["cache"] = {}
    _session["cache_hits"] = 0


def session_heals():
    """The heals scored in this process, newest last."""
    return list(_session["heals"])


def session_stats():
    return {
        "heals": len(_session["heals"]),
        "cache_hits": _session["cache_hits"],
        "healed_locators": sorted({h["locator"] for h in _session["heals"]}),
    }


_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = UIHeuristicEngine(fingerprint_path=config.POMODORO_FINGERPRINTS_PATH)
    return _engine


def _root_driver(context):
    """The WebDriver behind a driver-or-element context. WebElement.parent is
    the driver that produced it, which is what we need to scrape the DOM."""
    return getattr(context, "parent", None) or context


# --------------------------------------------------------------------------
# Heal core
# --------------------------------------------------------------------------
def attempt_heal(context, by, value):
    """Recover the element `by`/`value` was meant to find.

    `context` is a WebDriver or a WebElement (nested page-object lookups).
    Returns a live WebElement, or raises NoSuchElementException when the match
    is below the safety gate -- the caller sees exactly the exception Selenium
    would have raised, so a genuinely-missing element still fails the test.
    """
    driver = _root_driver(context)
    broken_identity = f"{by}='{value}'"
    started = time.perf_counter()

    with _guard():
        # Loop guard first: a locator that already escalated is not retried, and
        # must not generate another scoring pass or another dashboard row.
        if feedback.is_locked(value):
            raise NoSuchElementException(
                f"Self-healing locked for '{value}' after repeated failures. "
                f"Manual intervention required."
            )

        # Cache: this locator was already healed in this run.
        cached_xpath = _session["cache"].get((str(by), str(value)))
        if cached_xpath:
            try:
                element = driver.find_element(By.XPATH, cached_xpath)
                _session["cache_hits"] += 1
                return element
            except NoSuchElementException:
                _session["cache"].pop((str(by), str(value)), None)  # went stale

        print(f"⚠️ Element Missing: [{broken_identity}]. Extracting DOM candidates...")

        try:
            candidates = dom_features.collect_candidates(driver, limit=200)
        except Exception as e:
            print(f"❌ Failed to parse DOM structure: {e}")
            raise NoSuchElementException(f"Self-healing aborted. DOM inaccessible: {e}")

        print(f"🔬 Scanned {len(candidates)} structural layout candidates. Evaluating heuristics...")

        # ACTIVE request path: synchronous heal that returns a decision so we can
        # keep driving the browser (see handlers.handle_active_heal).
        lifecycle, query_locator, confidence, match_id, best_candidate = handle_active_heal(
            _get_engine(), broken_identity, candidates
        )

        # Threshold routing per Table 3.1:
        #   continue (>=75%) -> automatic heal
        #   verify   (20-75%) -> cautious heal: still reroute, but flag for review
        #   halt     (<20%)  -> stop + manual intervention
        if lifecycle not in ("continue", "verify") or query_locator in (None, "unknown"):
            print(f"❌ Confidence below safety gate ({confidence}%). Manual intervention required.")
            feedback.record_failure(value)
            raise NoSuchElementException(
                f"Self-healing fallback failed. Dynamic matching score too low "
                f"({confidence}%). Manual admin intervention required."
            )

        tier = "Auto-Heal" if lifecycle == "continue" else "Cautious Heal (flagged for review)"
        print(f"✨ {tier}! Rerouting to '{query_locator}' (Confidence: {confidence}%)")

        # Re-grab the healed element. Prefer the winning LIVE candidate's freshly
        # scraped xpath: renaming a class/id/attribute does not move the element,
        # so its xpath stays valid even when the attribute the old selector used
        # is the one that changed. Fall back to the css selector built from the
        # golden fingerprint (the id-rename path).
        element = None
        live_xpath = (best_candidate or {}).get("xpath")
        if live_xpath:
            try:
                element = driver.find_element(By.XPATH, live_xpath)
            except NoSuchElementException:
                element = None
        if element is None:
            try:
                element = driver.find_element(By.CSS_SELECTOR, query_locator)
            except NoSuchElementException:
                count, escalated = feedback.record_failure(value)
                raise NoSuchElementException(
                    f"Heal candidate not found in DOM ({count} consecutive fails). "
                    f"{'Escalated.' if escalated else ''}"
                )

        # Verify (post-heal validation) + reset/track the loop counter.
        feedback.verify_and_record(value, element)

        if live_xpath:
            _session["cache"][(str(by), str(value))] = live_xpath

        _session["heals"].append({
            "locator": broken_identity,
            "resolved_to": query_locator,
            "resolved_tag": (best_candidate or {}).get("tag_name", ""),
            "resolved_text": (best_candidate or {}).get("inner_text", "")[:40],
            "confidence": round(float(confidence), 2),
            "policy": "AUTOMATIC HEAL" if lifecycle == "continue" else "CAUTIOUS HEAL",
            "match_id": match_id,
            "ms": round((time.perf_counter() - started) * 1000, 1),
        })

        # Automation-level recovery (secondary): on high-confidence heals, write
        # the corrected locator back into the test source too.
        if lifecycle == "continue":
            try:
                healed_token = _get_engine().canonical_locator(match_id)
                source_healer.patch_source(broken_token=value, healed_token=healed_token)
            except Exception as e:
                print(f"⚠️ Source write-back skipped: {e}")

        return element


def attempt_heal_list(context, by, value):
    """find_elements variant: an empty result is the failure signal (Selenium
    returns [] rather than raising). Returns [healed] or [] -- never raises, to
    keep find_elements' contract."""
    try:
        return [attempt_heal(context, by, value)]
    except NoSuchElementException:
        return []


# --------------------------------------------------------------------------
# Level 1: transparent proxy
# --------------------------------------------------------------------------
class SelfHealingWebDriver:
    """Drop-in stand-in for a Selenium WebDriver.

    Only the element-lookup calls are intercepted; everything else (get, quit,
    execute_script, current_url, switch_to, ...) is delegated untouched, so this
    object can be handed to code that has no idea healing exists -- including
    WebDriverWait and page-object classes.
    """

    def __init__(self, real_driver):
        self.driver = real_driver
        self.engine = _get_engine()

    # Anything we don't intercept belongs to the real driver.
    def __getattr__(self, name):
        try:
            real = self.__dict__["driver"]
        except KeyError:  # attribute asked for before __init__ finished
            raise AttributeError(name)
        return getattr(real, name)

    def __repr__(self):
        return f"<SelfHealingWebDriver wrapping {self.driver!r}>"

    def find_element(self, by, value):
        try:
            return self.driver.find_element(by, value)
        except NoSuchElementException:
            if healing_in_progress():
                raise
            return attempt_heal(self.driver, by, value)

    def find_elements(self, by, value):
        found = self.driver.find_elements(by, value)
        if found or healing_in_progress():
            return found
        return attempt_heal_list(self.driver, by, value)
