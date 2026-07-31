"""
Shared DOM feature extraction used by both Learning Mode (FingerprintManager)
and Healing Mode (SelfHealingWebDriver). Keeping one implementation guarantees
the golden fingerprint and the live candidate are described the same way, so the
R2 (xpath) and R4 (neighbor) heuristics compare like-for-like.
"""

import re

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


# Tags treated as healable candidates when scraping the live DOM.
# Rule-based: no tag restrictions. The R1-R4 scoring handles ALL elements
# regardless of tag type. A broken <h1>, <p>, <img>, <label>, <li>, <td>
# heals the same way as a <button> or <input>.
# The only filter is a practical limit (200 elements) to keep healing fast.
CANDIDATE_TAGS = [
    "a", "abbr", "address", "article", "aside", "b", "bdi", "bdo",
    "blockquote", "body", "br", "button", "caption", "cite", "code",
    "col", "colgroup", "data", "datalist", "dd", "del", "details", "dfn",
    "dialog", "div", "dl", "dt", "em", "embed", "fieldset", "figcaption",
    "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hgroup", "hr", "i", "iframe", "img", "input", "ins",
    "kbd", "label", "legend", "li", "main", "map", "mark", "menu",
    "meter", "nav", "noscript", "object", "ol", "optgroup", "option",
    "output", "p", "picture", "pre", "progress", "q", "rp", "rt",
    "ruby", "s", "samp", "script", "section", "select", "slot", "small",
    "span", "strong", "sub", "summary", "sup", "table", "tbody", "td",
    "template", "textarea", "tfoot", "th", "thead", "time", "tr", "u",
    "ul", "var", "video", "wbr",
]

# One-shot candidate harvest. The per-element approach (tag_name + get_attribute
# x2 + a compute_xpath execute_script + a compute_neighbors find_elements, for
# every element on the page) costs ~6 WebDriver round trips per candidate, so a
# single heal on a modest page used to issue well over a thousand. This does the
# whole walk inside the browser and returns every candidate's features in ONE
# round trip. The xpath algorithm and the neighbor rule (first `limit` element
# siblings in document order, non-empty text, truncated to 50 chars) are kept
# byte-for-byte identical to compute_xpath/compute_neighbors above so golden
# fingerprints and live candidates stay like-for-like -- R2 and R4 compare the
# same shapes no matter which path produced them.
_CANDIDATES_JS = """
var tags = arguments[0], limit = arguments[1], nlimit = arguments[2];
var allowed = {};
for (var t = 0; t < tags.length; t++) { allowed[tags[t]] = true; }

function getXPath(el) {
  var parts = [];
  while (el && el.nodeType === Node.ELEMENT_NODE) {
    var siblings = 0, sibling = el.previousSibling;
    while (sibling) {
      if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === el.nodeName) { siblings++; }
      sibling = sibling.previousSibling;
    }
    parts.unshift(el.nodeName.toLowerCase() + '[' + (siblings + 1) + ']');
    el = el.parentNode;
  }
  return parts.length ? '/' + parts.join('/') : '';
}

function textOf(el) { return ((el.innerText || el.textContent) || '').trim(); }
function attrOf(el, name) { var v = el.getAttribute(name); return v ? v.trim() : ''; }

// Attributes the Locator Recovery Engine ranks by stability when it derives the
// repaired locator (report §3.4.3 Step 6). These MUST be collected here: the
// engine prefers the LIVE element's attribute over the golden one, because the
// golden value is by definition the stale one that just failed.
var DATA_ATTRS = ['data-testid', 'data-test', 'data-id', 'data-action', 'data-qa', 'data-cy'];

var out = [], all = document.querySelectorAll('*');
for (var i = 0; i < all.length && out.length < limit; i++) {
  var el = all[i], tag = el.tagName.toLowerCase();
  if (!allowed[tag]) { continue; }

  var sibs = [], parent = el.parentNode;
  if (parent && parent.children) {
    for (var j = 0; j < parent.children.length; j++) {
      if (parent.children[j] !== el) { sibs.push(parent.children[j]); }
    }
  }
  var neighbors = [];
  for (var k = 0; k < sibs.length && k < nlimit; k++) {
    var txt = textOf(sibs[k]);
    if (txt) { neighbors.push({ tag_name: sibs[k].tagName.toLowerCase(), text: txt.slice(0, 50) }); }
  }

  var dataAttrs = {};
  for (var d = 0; d < DATA_ATTRS.length; d++) {
    var dv = attrOf(el, DATA_ATTRS[d]);
    if (dv) { dataAttrs[DATA_ATTRS[d]] = dv; }
  }

  out.push({
    tag_name: tag,
    inner_text: textOf(el),
    css_class: attrOf(el, 'class'),
    xpath: getXPath(el),
    neighbors: neighbors,
    element_id: el.id || '',
    element_name: attrOf(el, 'name'),
    input_type: attrOf(el, 'type'),
    href: attrOf(el, 'href'),
    placeholder: attrOf(el, 'placeholder'),
    aria_label: attrOf(el, 'aria-label'),
    data_attrs: dataAttrs
  });
}
return out;
"""


_INDEX_RE = re.compile(r"\[\d+\]")


def relative_xpath(xpath):
    """The tag path with positional indices stripped: '/html/body/div/button'.

    R2 compares structure, and an absolute indexed path is not a structural
    description -- inserting one wrapper <div> renumbers every segment below it
    even though nothing moved relative to its parent. Comparing the index-free
    tag sequence lets an inserted container cost a little similarity instead of
    resetting the whole comparison. Derived in Python from the absolute path so
    the golden fingerprint and the live candidate are guaranteed to be reduced
    by identical code (see the like-for-like note above).
    """
    return _INDEX_RE.sub("", str(xpath or ""))


# Containers and non-rendered tags are skipped when reporting what a developer
# added or removed. <body> and <script> "change" whenever anything inside them
# changes, which is noise: it restates the edit rather than describing it.
SNAPSHOT_EXCLUDED_TAGS = {"html", "head", "body", "script", "style", "noscript", "template"}


def page_signature(driver, limit=400):
    """A compact description of every element on the page, for change detection.

    The Golden Fingerprint baseline holds only the locators a test depends on,
    so it cannot answer "what did the developer add?" -- everything the suite
    never touched would look new. This records the whole page as it stood on the
    day the baseline was learned, so a later comparison reports the elements
    that genuinely appeared rather than the ones that were simply never tracked.
    """
    signatures = []
    for cand in collect_candidates(driver, limit=limit):
        if cand.get("tag_name") in SNAPSHOT_EXCLUDED_TAGS:
            continue
        signatures.append({
            "tag_name": cand.get("tag_name", ""),
            "rel_xpath": relative_xpath(cand.get("xpath", "")),
            "inner_text": (cand.get("inner_text") or "")[:60],
            "element_id": cand.get("element_id", ""),
            "css_class": cand.get("css_class", ""),
        })
    return signatures


def signature_key(entry):
    """Identity used to decide whether two snapshots describe the same element.

    Deliberately ignores position: an element that merely moved is not a new
    element, and reporting it as one would bury the real addition in noise.
    """
    return (
        str(entry.get("tag_name", "")),
        str(entry.get("element_id", "")),
        str(entry.get("inner_text", "")).strip(),
        str(entry.get("css_class", "")).strip(),
    )


def collect_candidates(driver, limit=200, neighbor_limit=3):
    """Every healable candidate on the page with its R1-R4 features, in one
    round trip. Returns [] if the DOM is unreadable (caller decides how to
    escalate)."""
    return driver.execute_script(
        _CANDIDATES_JS, CANDIDATE_TAGS, int(limit), int(neighbor_limit)
    ) or []
