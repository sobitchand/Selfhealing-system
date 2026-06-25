"""
Shared DOM feature extraction used by both Learning Mode (FingerprintManager)
and Healing Mode (SelfHealingWebDriver). Keeping one implementation guarantees
the golden fingerprint and the live candidate are described the same way, so the
R2 (xpath) and R4 (neighbor) heuristics compare like-for-like.
"""

from selenium.webdriver.common.by import By

# JS that builds an absolute, indexed xpath for an element (matches the
# xpath_pattern stored at learning time).
_XPATH_JS = (
    "function getXPath(el) {"
    "  var parts = [];"
    "  while (el && el.nodeType === Node.ELEMENT_NODE) {"
    "    var siblings = 0; var sibling = el.previousSibling;"
    "    while (sibling) {"
    "      if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === el.nodeName) { siblings++; }"
    "      sibling = sibling.previousSibling;"
    "    }"
    "    var idx = siblings + 1;"
    "    parts.unshift(el.nodeName.toLowerCase() + '[' + idx + ']');"
    "    el = el.parentNode;"
    "  }"
    "  return parts.length ? '/' + parts.join('/') : null;"
    "}"
    "return getXPath(arguments[0]);"
)


def compute_xpath(driver, element):
    """Absolute indexed xpath for `element`, or '' on failure."""
    try:
        return driver.execute_script(_XPATH_JS, element) or ""
    except Exception:
        return ""


def compute_neighbors(element, limit=3):
    """Up to `limit` sibling elements as [{tag_name, text}], skipping empties."""
    neighbors = []
    try:
        siblings = element.find_elements(
            By.XPATH, "./preceding-sibling::* | ./following-sibling::*"
        )
        for sib in siblings[:limit]:
            text_val = (sib.text or "").strip()
            if text_val:
                neighbors.append({"tag_name": sib.tag_name.lower(), "text": text_val[:50]})
    except Exception:
        pass
    return neighbors
