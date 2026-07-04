import traceback
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from healing_engine import UIHeuristicEngine
from handlers import handle_active_heal
import dom_features
import feedback
import source_healer
import config

class SelfHealingWebDriver:
    def __init__(self, real_driver):
        """
        Wraps a standard Selenium WebDriver instance to intercept failures
        and automatically apply rule-based heuristic recoveries.
        """
        self.driver = real_driver
        self.engine = UIHeuristicEngine(fingerprint_path=config.POMODORO_FINGERPRINTS_PATH)

    def find_element(self, by, value):
        """
        Intercepts find_element calls. If the element is missing, scrapes the DOM
        and evaluates candidate alternatives against golden fingerprints.
        """
        try:
            # First, attempt standard Selenium discovery
            return self.driver.find_element(by, value)
        except NoSuchElementException:
            broken_identity = f"{by}='{value}'"
            print(f"⚠️ Element Missing: [{broken_identity}]. Extracting DOM candidates...")
            
            discovered_candidates = []
            
            # Scrape active DOM elements to find a structural fallback candidate
            try:
                dom_elements = self.driver.find_elements(By.XPATH, "//*")
            except Exception as e:
                print(f"❌ Failed to parse DOM structure: {str(e)}")
                raise NoSuchElementException(f"Self-healing aborted. DOM inaccessible: {str(e)}")
            
            # Limit scan loop depth to protect run performance limits
            for element in dom_elements[:200]:
                try:
                    tag = element.tag_name
                    if tag:
                        tag = tag.lower()
                        # Target interactive structural boundaries
                        if tag in ["button", "div", "span", "a", "input"]:
                            # Pull textContent directly to grab strings invisible to headless mode
                            inner_text = element.get_attribute("textContent") or ""
                            css_class = element.get_attribute("class") or ""

                            # xpath + neighbors so R2/R4 heuristics can be computed
                            # (same extraction as Learning Mode -> like-for-like).
                            discovered_candidates.append({
                                "tag_name": tag,
                                "inner_text": inner_text.strip(),
                                "css_class": css_class.strip(),
                                "xpath": dom_features.compute_xpath(self.driver, element),
                                "neighbors": dom_features.compute_neighbors(element),
                            })
                except Exception:
                    continue  # Skip stale or unreadable elements safely
            
            print(f"🔬 Scanned {len(discovered_candidates)} structural layout candidates. Evaluating heuristics...")

            # ACTIVE request path: synchronous heal that returns a decision so we
            # can keep driving the browser (see handlers.handle_active_heal).
            lifecycle, query_locator, confidence, match_id, best_candidate = handle_active_heal(
                self.engine, broken_identity, discovered_candidates
            )

            # Loop guard: if this locator already escalated, don't keep retrying.
            if feedback.is_locked(value):
                raise NoSuchElementException(
                    f"Self-healing locked for '{value}' after repeated failures. Manual intervention required."
                )

            # Threshold routing per Table 3.1:
            #   continue (>=75%) -> automatic heal
            #   verify   (20-75%) -> cautious heal: still reroute, but flag for review
            #   halt     (<20%)  -> stop + manual intervention
            if lifecycle in ("continue", "verify") and query_locator not in (None, "unknown"):
                tier = "Auto-Heal" if lifecycle == "continue" else "Cautious Heal (flagged for review)"
                print(f"✨ {tier}! Rerouting to '{query_locator}' (Confidence: {confidence}%)")

                # Re-grab the healed element. Prefer the winning LIVE candidate's
                # freshly-scraped xpath: renaming a class/id/attribute does not move
                # the element, so its xpath stays valid even when the attribute the
                # old selector used is the one that changed. Fall back to the css
                # selector built from the golden fingerprint (the id-rename path).
                element = None
                live_xpath = (best_candidate or {}).get("xpath")
                if live_xpath:
                    try:
                        element = self.driver.find_element(By.XPATH, live_xpath)
                    except NoSuchElementException:
                        element = None
                if element is None:
                    try:
                        element = self.driver.find_element(By.CSS_SELECTOR, query_locator)
                    except NoSuchElementException:
                        # Heal pointed at nothing -> count as a failure for the loop guard.
                        count, escalated = feedback.record_failure(value)
                        raise NoSuchElementException(
                            f"Heal candidate not found in DOM ({count} consecutive fails). "
                            f"{'Escalated.' if escalated else ''}"
                        )

                # Verify (post-heal validation) + reset/track the loop counter.
                feedback.verify_and_record(value, element)

                # Automation-level recovery (secondary): on high-confidence heals,
                # write the corrected locator back into the test source too.
                if lifecycle == "continue":
                    try:
                        healed_token = self.engine.canonical_locator(match_id)
                        source_healer.patch_source(broken_token=value, healed_token=healed_token)
                    except Exception as e:
                        print(f"⚠️ Source write-back skipped: {e}")

                return element
            else:
                print(f"❌ Confidence below safety gate ({confidence}%). Manual intervention required.")
                feedback.record_failure(value)
                raise NoSuchElementException(
                    f"Self-healing fallback failed. Dynamic matching score too low ({confidence}%). Manual admin intervention required."
                )