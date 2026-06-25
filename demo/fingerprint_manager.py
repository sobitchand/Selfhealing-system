import json
import os
from selenium.webdriver.common.by import By
import dom_features

class FingerprintManager:
    # Tags treated as interactive/structural when auto-discovering elements.
    INTERACTIVE_TAGS = ["button", "a", "input", "select", "textarea"]

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

    def scan_interactive(self):
        """Learning Mode auto-discovery (proposal §3.4.2 / Fig 3.4): walk every
        interactive element on the page and capture a Golden Fingerprint for each
        one that has a stable id. Returns the number captured."""
        captured = 0
        for tag in self.INTERACTIVE_TAGS:
            try:
                elements = self.driver.find_elements(By.TAG_NAME, tag)
            except Exception:
                continue
            for element in elements:
                try:
                    el_id = element.get_attribute("id")
                    if not el_id:
                        continue  # need a stable key to compare against later
                    by = "id"
                    self.registry[el_id] = self._build_fingerprint(element, el_id, by, el_id)
                    captured += 1
                except Exception:
                    continue
        self._save_registry()
        print(f"📸 Learning Mode captured {captured} golden fingerprints.")
        return captured

    def _build_fingerprint(self, element, key, by, value):
        """Build one Golden Fingerprint profile (shared by manual + auto scan)."""
        return {
            "key": key,
            "locator_by": str(by),
            "locator_value": str(value),
            "element_id": element.get_attribute("id") or "",
            "inner_text": element.text.strip(),
            "xpath_pattern": dom_features.compute_xpath(self.driver, element),
            "css_class": element.get_attribute("class") or "",
            "tag_name": element.tag_name.lower(),
            "neighbors": dom_features.compute_neighbors(element),
        }

    def _save_registry(self):
        os.makedirs(os.path.dirname(self.fingerprint_path), exist_ok=True)
        with open(self.fingerprint_path, "w") as f:
            json.dump(self.registry, f, indent=2)