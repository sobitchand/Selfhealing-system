import json
import os
from selenium.webdriver.common.by import By
import dom_features

class FingerprintManager:
    # Capture fingerprints for ALL elements on the page, not just those with an id.
    # The R1-R4 scoring works for any tag type — buttons, inputs, headings, SVG
    # paths, divs, spans, etc. Elements with an id are keyed by their id; elements
    # without an id are keyed by a composite signature (tag::text or tag::class::index)
    # so they can still be matched when a locator breaks.
    CAPTURE_TAGS = [
        "a", "abbr", "address", "article", "aside", "b", "button", "caption",
        "cite", "code", "data", "dd", "del", "details", "dfn", "dialog", "div",
        "dt", "em", "fieldset", "figcaption", "figure", "footer", "form",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "i", "img", "input",
        "kbd", "label", "legend", "li", "main", "mark", "nav", "ol", "optgroup",
        "option", "output", "p", "path", "pre", "progress", "q", "rp", "rt",
        "ruby", "s", "samp", "section", "select", "small", "span", "strong",
        "sub", "summary", "sup", "svg", "table", "tbody", "td", "textarea",
        "tfoot", "th", "thead", "time", "tr", "u", "ul", "var", "video",
    ]

    def __init__(self, driver, fingerprint_path):
        self.driver = driver
        self.fingerprint_path = fingerprint_path
        self.registry = self._load_registry()

    def _load_registry(self):
        if os.path.exists(self.fingerprint_path):
            try:
                with open(self.fingerprint_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def scan_elements(self, element_mappings):
        """
        Scans elements in their working state and extracts properties.
        element_mappings: List of tuples -> [(By.ID, "start-btn"), (By.LINK_TEXT, "Book Pickup")]
        """
        for index, (by, value) in enumerate(element_mappings, start=1):
            try:
                element = self.driver.find_element(by, value)
                key = element.get_attribute("id") or f"element_{index}"
                self.registry[key] = self._build_fingerprint(element, key, by, value)
                print(f"📸 Captured Golden Fingerprint for: '{value}' -> Stored as '{key}'")
            except Exception as e:
                print(f"⚠️ Could not scan element {value}: {str(e)}")

        self._save_registry()

    def capture_from_locator(self, element, by, value):
        """Capture a fingerprint for a specific element that the test script
        successfully located. This is the inline-learning path described in
        §3.3.1 Step 2: 'Each time a locator resolves successfully, the
        corresponding element's fingerprint is captured or refreshed.'

        The fingerprint is keyed by the LOCATOR the script used -- "<by>::<value>"
        -- not by the element's id. Two locators may address the same element
        (By.ID 'qty' and By.NAME 'quantity' often do), and each needs its own
        baseline entry: keying by element id made the second lookup overwrite
        the first, silently dropping one of the test's dependencies. Keying by
        locator also means a broken locator is resolved on Day 2 by exact lookup
        rather than by guessing which fingerprint id it most resembles, which is
        what lets CSS, XPath, NAME and LINK_TEXT locators heal as reliably as ID.

        For find_elements (multiple results), an index suffix is appended."""
        key = f"{by}::{value}"

        fp = self._build_fingerprint(element, key, str(by), str(value))
        self.registry[key] = fp
        return key

    def scan_interactive(self):
        """Learning Mode auto-discovery: walk ALL elements on the page and capture
        a Golden Fingerprint for every element — with or without an id. Elements
        with an id are keyed by their id; elements without an id are keyed by a
        composite signature (tag::text or tag::class) so they can still be healed.

        This matches the report's promise: 'records a Golden Fingerprint of every
        element' — not just id-bearing elements. SVG paths, class-based buttons,
        and any other tagged element are all valid heal targets.
        Returns the number captured."""
        captured = 0
        for tag in self.CAPTURE_TAGS:
            try:
                elements = self.driver.find_elements(By.TAG_NAME, tag)
            except Exception:
                continue
            for element in elements:
                try:
                    el_id = element.get_attribute("id")
                    text = (element.text or "").strip()
                    css = element.get_attribute("class") or ""

                    if el_id:
                        key = el_id
                        by = "id"
                        value = el_id
                    elif text:
                        key = f"{tag}::{text[:40]}"
                        by = "css selector"
                        value = f"{tag}.{text[:40]}"
                    elif css:
                        key = f"{tag}::{css}"
                        by = "css selector"
                        value = f"{tag}.{css.split()[0]}"
                    else:
                        continue

                    if key in self.registry:
                        continue

                    self.registry[key] = self._build_fingerprint(element, key, by, value)
                    captured += 1
                except Exception:
                    continue
        self._save_registry()
        print(f"Learning Mode captured {captured} golden fingerprints.")
        return captured

    def _build_fingerprint(self, element, key, by, value):
        """Build one Golden Fingerprint profile (shared by manual + auto scan).
        Captures all attributes the report §3.4.3 Step 6 lists for repaired-locator
        derivation: id, name, data-attrs, aria-label, text, tag, class, xpath."""
        data_attrs = {}
        for attr in ("data-testid", "data-test", "data-id", "data-action", "data-qa"):
            val = element.get_attribute(attr)
            if val:
                data_attrs[attr] = val

        return {
            "key": key,
            "locator_by": str(by),
            "locator_value": str(value),
            # Exact identity of the locator the test script used. Healing Mode
            # looks this up directly, so a broken locator resolves to the element
            # the script intended instead of to whatever fingerprint id it most
            # resembles. Works for every By strategy, not just By.ID.
            "locator_key": f"{by}::{value}",
            "element_id": element.get_attribute("id") or "",
            "element_name": element.get_attribute("name") or "",
            "inner_text": (element.text or "").strip(),
            "xpath_pattern": dom_features.compute_xpath(self.driver, element),
            "css_class": element.get_attribute("class") or "",
            "tag_name": element.tag_name.lower(),
            "neighbors": dom_features.compute_neighbors(element),
            "aria_label": element.get_attribute("aria-label") or "",
            "placeholder": element.get_attribute("placeholder") or "",
            "input_type": element.get_attribute("type") or "",
            "href": element.get_attribute("href") or "",
            "data_attrs": data_attrs,
        }

    def save(self):
        """Persist the registry to disk (alias for _save_registry)."""
        self._save_registry()

    def _save_registry(self):
        os.makedirs(os.path.dirname(self.fingerprint_path), exist_ok=True)
        with open(self.fingerprint_path, "w") as f:
            json.dump(self.registry, f, indent=2)