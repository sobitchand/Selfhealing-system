import json
import os
import re
import sys
import glob
import subprocess
import time
import urllib.request
import difflib
from datetime import datetime
import config
import dom_features
import run_context
import store

class UIHeuristicEngine:
    def __init__(self, fingerprint_path=None):
        if fingerprint_path is None:
            fingerprint_path = config.ACTIVE_FINGERPRINT_PATH
        self.fingerprint_path = fingerprint_path
        self.reload_fingerprints()

    def reload_fingerprints(self):
        """(Re)load the golden fingerprint registry from disk. Called at init and
        before each evaluation so a baseline built by Learning Mode AFTER this
        engine was constructed is picked up."""
        try:
            with open(self.fingerprint_path, "r") as f:
                self.fingerprints = json.load(f)
        except Exception:
            self.fingerprints = {}

    def calculate_similarity(self, value1, value2):
        """Calculates text similarities dynamically using Gestalt Pattern Matching."""
        if not value1 or not value2: 
            return 0.0
        return difflib.SequenceMatcher(None, str(value1).strip(), str(value2).strip()).ratio() * 100.0

    def calculate_xpath_depth_similarity(self, xpath1, xpath2):
        """R2: how similar two elements' positions in the document tree are.

        The comparison is STRUCTURAL, not positional-by-index. The previous
        implementation zipped the two paths segment by segment and required
        '/div[2]' to sit at the same offset as '/div[2]', which meant that
        inserting a single wrapper <div> -- the most ordinary change a front-end
        developer makes -- shifted every segment below it and collapsed the
        score even though the element had not moved relative to its own parent.
        A wrapper insertion took this rule from 100% to 60%.

        Three signals are combined instead:

          * Shape (55%). The index-free tag paths compared with difflib's
            sequence matcher, which is insertion- and deletion-tolerant: an
            extra <div> in the middle costs one segment rather than
            invalidating everything after it.
          * Ordinal position (25%). The fully indexed segments, compared the
            same way. Stripping indices alone would make the first and the
            third button in a row structurally identical, so sibling order is
            still worth something -- it is exactly the evidence that separates
            two similar candidates on the same page.
          * Depth agreement (20%). How close the two elements sit in nesting
            depth, so one buried far deeper than the fingerprint loses
            confidence even when its ancestry reads the same.

        Both sides are reduced by dom_features.relative_xpath, so the golden
        fingerprint and the live candidate are always compared like-for-like.
        """
        if not xpath1 or not xpath2:
            return 0.0

        full1 = [s for s in str(xpath1).split("/") if s]
        full2 = [s for s in str(xpath2).split("/") if s]
        tags1 = [t for t in dom_features.relative_xpath(xpath1).split("/") if t]
        tags2 = [t for t in dom_features.relative_xpath(xpath2).split("/") if t]
        if not tags1 or not tags2:
            return 0.0

        shape = difflib.SequenceMatcher(None, tags1, tags2).ratio()
        ordinal = difflib.SequenceMatcher(None, full1, full2).ratio()
        depth = 1.0 - (abs(len(tags1) - len(tags2)) / max(len(tags1), len(tags2)))
        return ((shape * 0.55) + (ordinal * 0.25) + (depth * 0.20)) * 100.0

    def calculate_neighbor_similarity(self, neighbors1, neighbors2):
        """R4: how similar the surrounding elements are.

        For each golden neighbor, find the best-matching candidate neighbor by
        tag + visible text, then average. Returns 0 when either side has no
        captured neighbors (it only carries 10% weight, so this is safe)."""
        if not neighbors1 or not neighbors2:
            return 0.0
        total = 0.0
        for g in neighbors2:
            g_sig = f"{str(g.get('tag_name','')).lower()} {g.get('text','')}"
            best = 0.0
            for c in neighbors1:
                c_sig = f"{str(c.get('tag_name','')).lower()} {c.get('text','')}"
                best = max(best, self.calculate_similarity(c_sig, g_sig))
            total += best
        return total / len(neighbors2)

    def _extract_broken_value(self, broken_selector):
        """Pull the raw locator value out of a broken-selector string.

        Accepts forms like "id='old-start-btn'" or "css selector='#old-start-btn'".
        Strips leading css punctuation so we compare on the bare identifier.
        """
        m = re.search(r"'([^']*)'", str(broken_selector))
        raw = m.group(1) if m else str(broken_selector)
        return raw.lstrip("#.").strip()

    @staticmethod
    def _locator_key(broken_selector):
        """Canonical "<by>::<value>" identity for a locator, or '' if unparsable.

        automation_wrapper formats the failing lookup as "id='start-btn'" /
        "css selector='.add-btn'" / "xpath='//button[1]'", which is the same
        (by, value) pair Inline Learning recorded on the passing run.
        """
        m = re.match(r"^(.*?)='(.*)'$", str(broken_selector).strip(), re.DOTALL)
        if not m:
            return ""
        return f"{m.group(1).strip()}::{m.group(2)}"

    def select_target_fingerprint(self, broken_selector, min_ratio=40.0):
        """Tie the broken locator to the fingerprint it was MEANT to find.

        Scores the broken identifier against each fingerprint's element id, key,
        and locator_value — returning the best (key, ratio) but only if it clears
        min_ratio. Below that we return (None, ratio) so the caller falls back to
        a global scan (preserves old behaviour for ids unrelated to any fingerprint).

        Matching against locator_value as well as element_id means that locators
        like By.CSS_SELECTOR("button.btn-primary") match the fingerprint captured
        from that exact locator during Learning Mode.
        """
        # --- Exact identity first (preferred) -------------------------------
        # Inline Learning records the locator the test script actually used, so
        # a Day-2 failure of that same locator is an EXACT lookup, not a guess.
        # This is what makes By.CSS_SELECTOR / By.XPATH / By.NAME / By.LINK_TEXT
        # heal as reliably as By.ID: the key is the locator itself, so nothing
        # depends on the broken string happening to resemble an element id.
        # The similarity scan below remains as a fallback for baselines captured
        # by the page scan, or for a locator never seen during learning.
        exact_key = self._locator_key(broken_selector)
        if exact_key:
            for key, golden in self.fingerprints.items():
                if golden.get("locator_key") == exact_key:
                    return key, 100.0

        broken_value = self._extract_broken_value(broken_selector)
        if not broken_value:
            return None, 0.0
        best_key, best_ratio = None, 0.0
        for key, golden in self.fingerprints.items():
            # Try element_id first, then locator_value, then key
            candidates = [
                golden.get("element_id") or "",
                str(golden.get("locator_value") or ""),
                key,
            ]
            for ident in candidates:
                if not ident:
                    continue
                # Also try stripping CSS punctuation for comparison
                stripped = ident.lstrip("#.").strip()
                ratio = max(
                    self.calculate_similarity(broken_value, ident),
                    self.calculate_similarity(broken_value, stripped),
                )
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_key = key
        return (best_key, best_ratio) if best_ratio >= min_ratio else (None, best_ratio)

    def evaluate_live_candidates(self, broken_selector, candidates):
        self.reload_fingerprints()  # pick up Learning-Mode baseline / prior self-corrections
        best_match_id = None
        highest_score = 0.0
        second_score = 0.0
        winning_metrics = {}
        best_candidate = None
        reason = ""

        # Intent-aware: resolve WHICH element this broken locator meant, so two
        # different broken locators don't both heal to the same top element.
        #
        # Safety gate: if NO baseline fingerprint resembles the broken locator, we
        # genuinely don't know what the caller was trying to find. Refuse to guess.
        target_key, _ = self.select_target_fingerprint(broken_selector)
        if not target_key:
            return None, 0.0, {}, None, "", 0.0
        search_space = {target_key: self.fingerprints[target_key]}

        for element_key, golden in search_space.items():
            scored = []
            for cand in candidates:
                # Rule-based tag handling: tag mismatch = -25% penalty, same tag = no penalty.
                golden_tag = str(golden.get("tag_name", "")).lower()
                cand_tag = str(cand.get("tag_name", "")).lower()
                tag_penalty = 0.0 if cand_tag == golden_tag else 25.0

                # R1–R4 scoring (proposal Table 3.1)
                r1 = self.calculate_similarity(cand.get("inner_text", ""), golden.get("inner_text", ""))            # R1: visible text
                r2 = self.calculate_xpath_depth_similarity(cand.get("xpath", ""), golden.get("xpath_pattern", "")) # R2: tree structure
                r3 = self.calculate_similarity(cand.get("css_class", ""), golden.get("css_class", ""))             # R3: CSS class
                r4 = self.calculate_neighbor_similarity(cand.get("neighbors", []), golden.get("neighbors", []))   # R4: surrounding elements

                # Weight normalization (report §3.3.2): "Where an attribute is
                # absent from both the Golden Fingerprint and the candidate
                # element — that rule is excluded from the calculation and the
                # remaining weights are normalized, so that the absence of an
                # attribute is not scored as a mismatch."
                weights = {"r1": 0.40, "r2": 0.30, "r3": 0.20, "r4": 0.10}
                scores = {"r1": r1, "r2": r2, "r3": r3, "r4": r4}

                golden_text = str(golden.get("inner_text", "")).strip()
                cand_text = str(cand.get("inner_text", "")).strip()
                golden_css = str(golden.get("css_class", "")).strip()
                cand_css = str(cand.get("css_class", "")).strip()
                golden_xp = str(golden.get("xpath_pattern", "")).strip()
                cand_xp = str(cand.get("xpath", "")).strip()
                golden_nb = golden.get("neighbors", [])
                cand_nb = cand.get("neighbors", [])

                if not golden_text and not cand_text:
                    weights["r1"] = 0
                if not golden_xp and not cand_xp:
                    weights["r2"] = 0
                if not golden_css and not cand_css:
                    weights["r3"] = 0
                if not golden_nb and not cand_nb:
                    weights["r4"] = 0

                total_w = sum(weights.values())
                if total_w > 0:
                    for k in weights:
                        weights[k] = weights[k] / total_w

                composite_score = (scores["r1"] * weights["r1"] +
                                   scores["r2"] * weights["r2"] +
                                   scores["r3"] * weights["r3"] +
                                   scores["r4"] * weights["r4"]) - tag_penalty
                composite_score = min(100.0, max(0.0, composite_score))

                # Identity gate. R2 and R4 describe WHERE an element sits, not
                # WHICH element it is. When a tracked element is deleted, the
                # neighbour that shifts into its place inherits its position and
                # its surroundings, and can clear the safety gate on structural
                # evidence alone -- a false heal, which is worse than no heal at
                # all because it turns a visible failure into a silent one.
                #
                # So: if the fingerprint carries any identifying attribute at all
                # (text, class, name, data-*, aria-label) and NONE of them match
                # the candidate, we have not identified anything. Refuse.
                # Attributes absent from the fingerprint are not held against the
                # candidate -- that stays the job of weight normalisation above.
                identity, identity_applicable = self._identity_evidence(golden, cand, r1, r3)
                if identity_applicable and identity < self.IDENTITY_FLOOR:
                    composite_score = 0.0

                scored.append((composite_score, cand, {
                    "R1_inner_text_40": round(r1, 2),
                    "R2_xpath_pattern_30": round(r2, 2),
                    "R3_css_class_20": round(r3, 2),
                    "R4_neighbors_10": round(r4, 2),
                }, weights, tag_penalty))

            if not scored:
                continue

            scored.sort(key=lambda x: x[0], reverse=True)
            # The penalty must come from the WINNING candidate. Reading the loop
            # variable after the loop reported whatever the last candidate
            # happened to score, which is why an unchanged <input> was explained
            # as "Tag changed from <input> to <input>".
            top_score, top_cand, top_metrics, top_weights, top_penalty = scored[0]

            if top_score > highest_score:
                highest_score = top_score
                best_match_id = element_key
                best_candidate = top_cand
                winning_metrics = top_metrics
                second_score = scored[1][0] if len(scored) > 1 else 0.0

                # Reason for repair (report §3.7): "A generated explanation stating
                # which attributes matched, which changed, and which rules
                # determined the outcome."
                reason = self._build_reason(golden, top_cand, top_metrics, top_penalty)

        return best_match_id, highest_score, winning_metrics, best_candidate, reason, second_score

    # An identifying attribute must reach this score for a candidate to count as
    # the same element. Unrelated short strings score in the 20s under Gestalt
    # matching ("Need help?" against "No ticket submitted" scored 27.6), so the
    # floor sits above that band while still tolerating a genuine rename
    # ("btn-submit" -> "btn-primary" scores 62).
    IDENTITY_FLOOR = 40.0

    # Attributes that identify an element rather than locate it. An exact match
    # on any of these is conclusive on its own.
    _IDENTITY_ATTRS = ("element_name", "aria_label", "placeholder", "input_type")

    def _identity_evidence(self, golden, candidate, r1, r3):
        """Best identifying-attribute agreement, and whether any was available.

        Returns (score, applicable). `applicable` is False when the fingerprint
        carries no identifying attribute at all -- a bare <div> with no text, no
        class and no attributes -- in which case structural evidence is all that
        exists and the gate does not apply.
        """
        best = 0.0
        applicable = False

        if str(golden.get("inner_text", "")).strip():
            applicable = True
            best = max(best, r1)
        if str(golden.get("css_class", "")).strip():
            applicable = True
            best = max(best, r3)

        for attr in self._IDENTITY_ATTRS:
            golden_val = self._field(golden, attr)
            if not golden_val:
                continue
            applicable = True
            if golden_val == self._field(candidate, attr):
                return 100.0, True

        golden_data = golden.get("data_attrs") or {}
        cand_data = candidate.get("data_attrs") or {}
        for attr, golden_val in golden_data.items():
            if not golden_val:
                continue
            applicable = True
            if cand_data.get(attr) == golden_val:
                return 100.0, True

        return best, applicable

    def _build_reason(self, golden, candidate, metrics, tag_penalty):
        """Generate a human-readable explanation of the repair decision."""
        parts = []
        golden_tag = str(golden.get("tag_name", "")).lower()
        cand_tag = str(candidate.get("tag_name", "")).lower()

        if tag_penalty > 0:
            parts.append(f"Tag changed from <{golden_tag}> to <{cand_tag}> (−{tag_penalty:.0f}%)")

        r1 = metrics.get("R1_inner_text_40", 0)
        r2 = metrics.get("R2_xpath_pattern_30", 0)
        r3 = metrics.get("R3_css_class_20", 0)
        r4 = metrics.get("R4_neighbors_10", 0)

        if r1 >= 80:
            parts.append("visible text matched")
        elif r1 > 0:
            parts.append(f"text partially matched ({r1:.0f}%)")
        elif golden.get("inner_text", "").strip():
            parts.append("text was changed")

        if r2 >= 80:
            parts.append("DOM position unchanged")
        elif r2 > 0:
            parts.append(f"XPath structurally similar ({r2:.0f}%)")

        if r3 >= 80:
            parts.append("CSS class matched")
        elif r3 > 0:
            parts.append(f"CSS class partially matched ({r3:.0f}%)")
        elif golden.get("css_class", "").strip():
            parts.append("CSS class was renamed")

        if r4 >= 80:
            parts.append("neighbouring elements matched")
        elif r4 > 0 and golden.get("neighbors"):
            parts.append(f"neighbours partially matched ({r4:.0f}%)")

        if not parts:
            return "Healed via composite heuristic similarity."
        return "; ".join(parts) + "."

    def canonical_locator(self, match_id, best_candidate=None):
        """Stable write-back token for a matched fingerprint.

        Report §3.4.3 Step 6: "extracts id, name, data-attr, aria-label, input
        type, link text and ranks them by expected stability. The highest-ranked
        attribute is expressed as the repaired locator."

        Ranking order (most stable → least stable):
        1. id            — unique, semantic, survives most refactors
        2. name          — form-field standard, stable across redesigns
        3. data-testid   — explicit test anchor, designed to be stable
        4. data-test     — same rationale
        5. data-qa       — same rationale
        6. aria-label    — accessibility anchor, semantic
        7. text           — visible label, survives class/id renames
        8. css class      — styling, renamed during redesigns but present
        9. xpath          — structural, fragile but always available
        """
        recovered = self.recover_locator(match_id, best_candidate)
        return recovered.get("token", "") if recovered else ""

    # Attribute preference order used to express a repaired locator, most stable
    # first. Each entry is (field, by, template). `field` is read from the LIVE
    # element before the golden fingerprint, because the golden value is by
    # definition the stale one that just failed to resolve.
    _RECOVERY_RANK = [
        ("element_id",   "id",            "{v}"),
        ("data-testid",  "css selector",  "[data-testid='{v}']"),
        ("data-test",    "css selector",  "[data-test='{v}']"),
        ("data-qa",      "css selector",  "[data-qa='{v}']"),
        ("data-cy",      "css selector",  "[data-cy='{v}']"),
        ("element_name", "name",          "{v}"),
        ("aria_label",   "css selector",  "[aria-label='{v}']"),
    ]

    @staticmethod
    def _field(source, field):
        """Read `field` from a fingerprint or a live candidate, including the
        nested data_attrs map, returning '' when absent."""
        if not source:
            return ""
        if field.startswith("data-"):
            return str((source.get("data_attrs") or {}).get(field, "") or "")
        return str(source.get(field, "") or "")

    def recover_locator(self, match_id, best_candidate=None):
        """Locator Recovery Engine (report §3.4.3 Step 6).

        Ranks the identifying attributes of the winning LIVE element by expected
        stability and expresses the highest-ranked one as a real locator the QA
        engineer can paste into the test script.

        Returns {by, value, token, strategy, source} -- or {} when the match is
        unknown. `source` records whether the value came from the live element
        (the repaired locator) or from the golden fingerprint (a fallback used
        only when the live element carries no identifying attribute at all).
        """
        golden = self.fingerprints.get(match_id) if match_id else None
        if not golden:
            return {}

        tag = self._field(best_candidate, "tag_name") or self._field(golden, "tag_name")

        for field, by, template in self._RECOVERY_RANK:
            for source_name, source in (("live", best_candidate), ("golden", golden)):
                value = self._field(source, field)
                if value:
                    return {
                        "by": by,
                        "value": template.format(v=value),
                        "token": value,
                        "strategy": field,
                        "source": source_name,
                    }

        # Link text: only meaningful for anchors, where it is how a human
        # identifies the element.
        if tag == "a":
            for source_name, source in (("live", best_candidate), ("golden", golden)):
                text = self._field(source, "inner_text")
                if text:
                    return {
                        "by": "link text", "value": text, "token": text,
                        "strategy": "link_text", "source": source_name,
                    }

        # CSS class: survives id renames but is itself a redesign casualty.
        for source_name, source in (("live", best_candidate), ("golden", golden)):
            css = self._field(source, "css_class")
            if css and tag:
                selector = tag + "." + ".".join(css.split())
                return {
                    "by": "css selector", "value": selector, "token": selector,
                    "strategy": "css_class", "source": source_name,
                }

        # XPath: always available, least stable. Prefer the live path -- it is
        # where the element is NOW.
        xpath = self._field(best_candidate, "xpath") or self._field(golden, "xpath_pattern")
        if xpath:
            return {
                "by": "xpath", "value": xpath, "token": xpath,
                "strategy": "xpath",
                "source": "live" if self._field(best_candidate, "xpath") else "golden",
            }

        return {}

    # Selenium By constant names, for rendering a copy-paste recommendation.
    _BY_CONSTANTS = {
        "id": "By.ID",
        "name": "By.NAME",
        "css selector": "By.CSS_SELECTOR",
        "xpath": "By.XPATH",
        "link text": "By.LINK_TEXT",
        "partial link text": "By.PARTIAL_LINK_TEXT",
        "tag name": "By.TAG_NAME",
        "class name": "By.CLASS_NAME",
    }

    def _broken_source_token(self, broken_selector):
        """Bare identifier the QA script actually used (e.g. clearBtn), so a
        source patch matches `By.ID, "clearBtn"` rather than the wrapped
        "id='clearBtn'" diagnostic form that the heal logs use."""
        return self._extract_broken_value(broken_selector)

    def generate_multi_locators(self, match_id, best_candidate=None):
        """Generate multiple locator strategies for a healed element.
        
        Returns a list of locator strategies in order of preference (report
        §3.4.3 Step 6 — ranked by stability):
        1. ID (most stable)
        2. CSS Selector (tag + class)
        3. XPath with text
        4. Live XPath from DOM scan
        5. Original locator from fingerprint
        """
        golden = self.fingerprints.get(match_id) if match_id else None
        if not golden:
            return []
        
        locators = []
        
        # Strategy 1: ID (most stable) — prefer live candidate's id
        live_id = self._field(best_candidate, "element_id")
        element_id = golden.get("element_id") or ""
        use_id = live_id or element_id
        if use_id:
            locators.append({
                "strategy": "id",
                "by": "id",
                "value": use_id,
                "confidence": 95,
                "description": "Element ID (most stable)"
            })
        
        # Strategy 2: name attribute
        live_name = self._field(best_candidate, "element_name")
        golden_name = golden.get("element_name") or ""
        use_name = live_name or golden_name
        if use_name:
            locators.append({
                "strategy": "name",
                "by": "name",
                "value": use_name,
                "confidence": 90,
                "description": "Name attribute"
            })

        # Strategy 3: CSS Selector (tag + class)
        css_class = (best_candidate or {}).get("css_class") or golden.get("css_class", "")
        tag_name = (best_candidate or {}).get("tag_name") or golden.get("tag_name", "")
        if css_class and tag_name:
            primary_class = css_class.split()[0]
            css_selector = f"{tag_name}.{primary_class}"
            locators.append({
                "strategy": "css",
                "by": "css selector",
                "value": css_selector,
                "confidence": 85,
                "description": "CSS Selector (tag + class)"
            })
        
        # Strategy 4: XPath with text (most flexible)
        inner_text = (best_candidate or {}).get("inner_text") or golden.get("inner_text", "")
        if inner_text and tag_name:
            xpath = f"//{tag_name}[text()='{inner_text}']"
            locators.append({
                "strategy": "xpath",
                "by": "xpath",
                "value": xpath,
                "confidence": 75,
                "description": "XPath with text content"
            })
        
        # Strategy 5: XPath from candidate (if available)
        if best_candidate and best_candidate.get("xpath"):
            locators.append({
                "strategy": "xpath_live",
                "by": "xpath",
                "value": best_candidate["xpath"],
                "confidence": 90,
                "description": "Live XPath from DOM scan"
            })
        
        # Strategy 6: Original locator (fallback)
        locator_value = golden.get("locator_value", "")
        locator_by = golden.get("locator_by", "")
        if locator_value and locator_by:
            locators.append({
                "strategy": "original",
                "by": locator_by,
                "value": locator_value,
                "confidence": 70,
                "description": "Original locator from fingerprint"
            })
        
        return locators

    def update_metadata_locator(self, match_id, best_candidate=None):
        """Self-Correction: persist the healed locator into the golden-fingerprint
        metadata (proposal §3.4.3 Step 6 / Fig 3.3 'Update Metadata Repository').

        Sets healed_locator_value/by on the matched fingerprint and writes the
        registry atomically (temp file -> os.replace). The healed locator is
        derived from the LIVE candidate's current id (when present) so a renamed
        element records its NEW id rather than the stale baseline id. Best-effort:
        returns the healed locator string, or '' on no-op/failure (never raises)."""
        recovered = self.recover_locator(match_id, best_candidate)
        token = recovered.get("token", "") if recovered else ""
        if not token or match_id not in self.fingerprints:
            return ""
        # Express the repaired locator in the strategy the recovery engine chose.
        # Hardcoding a '#'-prefixed css selector was wrong for every element
        # recovered by name, data attribute, aria-label, link text or xpath.
        healed_value = recovered["value"]
        try:
            self.fingerprints[match_id]["healed_locator_value"] = healed_value
            self.fingerprints[match_id]["healed_locator_by"] = recovered["by"]
            self.fingerprints[match_id]["healed_locator_strategy"] = recovered["strategy"]
            self.fingerprints[match_id]["healed_locator_source"] = recovered["source"]
            self.fingerprints[match_id]["healed_source_token"] = token
            tmp = self.fingerprint_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.fingerprints, f, indent=2)
            os.replace(tmp, self.fingerprint_path)
            return healed_value
        except Exception as e:
            print(f"⚠️ metadata self-correction failed for '{match_id}': {e}")
            return ""

    def commit_heal_to_log(self, broken_selector, match_id, score, metrics, approval_mode=False, script_path=None, line_number=None, best_candidate=None, reason="", second_score=0.0):
        """Applies confidence policies and persists the heal result (ACTIVE path).
        
        approval_mode: If True, queue the heal for human review instead of auto-applying
        script_path: Path to the QA test script (required for approval_mode)
        line_number: Line number where the broken locator appears (optional)
        best_candidate: The winning LIVE element dict; its current `id` is used as
                        the healed token so a renamed element heals to its NEW id.
        reason: Human-readable explanation of why this candidate was selected (§3.7).
        second_score: The score of the second-best candidate, used for the margin
                      check (§3.3.2: "winning candidate must exceed next-best by
                      a minimum margin").
        """
        timestamp = datetime.utcnow().isoformat() + "+00:00"

        # Margin check (report §3.3.2): "an automatic heal additionally requires
        # the winning candidate to exceed the next-best candidate by a minimum
        # margin, so that a page containing two similar elements cannot produce
        # a confident but incorrect substitution."
        MARGIN_THRESHOLD = 10.0
        margin = score - second_score
        margin_ok = margin >= MARGIN_THRESHOLD or second_score == 0.0

        if score >= config.CONFIDENCE_THRESHOLD_HIGH and margin_ok:
            policy, status, lifecycle = "AUTOMATIC HEAL", "success", "continue"
        elif score >= config.CONFIDENCE_THRESHOLD_HIGH and not margin_ok:
            # High score but narrow margin → downgrade to cautious
            policy, status, lifecycle = "CAUTIOUS HEAL", "warning", "verify"
            reason = (reason + " " if reason else "") + f"Downgraded to cautious: margin over next-best candidate is only {margin:.1f}% (threshold {MARGIN_THRESHOLD}%)."
        elif config.CONFIDENCE_THRESHOLD_LOW <= score < config.CONFIDENCE_THRESHOLD_HIGH:
            policy, status, lifecycle = "CAUTIOUS HEAL", "warning", "verify"
        else:
            policy, status, lifecycle = "CRITICAL FAULT", "failed", "halt"

        # Generate QA recommendation (report §3.7)
        recommendation = self._generate_recommendation(match_id, best_candidate, score, policy)

        # The repaired locator: a real By/value pair derived from the winning
        # LIVE element, not a descriptor rebuilt from the stale baseline. This is
        # what the dashboard shows as "New Runtime Locator" and what the QA
        # recommendation tells the engineer to paste into the script.
        recovered = self.recover_locator(match_id, best_candidate)
        recovered_val = recovered.get("value", "unknown") if recovered else "unknown"

        if status == "failed":
            refusal = {
                "timestamp": timestamp,
                **run_context.stamp(),
                "severity": "critical",
                "message": (
                    f"Recovery declined for {broken_selector}: best match scored "
                    f"{score:.1f}%, below the {config.CONFIDENCE_THRESHOLD_LOW:.0f}% "
                    f"safety gate. No element was clicked."
                ),
                "broken_selector": broken_selector,
                "confidence_score": round(score, 2),
                "source": "UIHeuristicEngine"
            }
            store.append("alerts", refusal)
            run_context.note_refusal(refusal)
        else:
            healed_locator = self.update_metadata_locator(match_id, best_candidate)

            old_token = self._broken_source_token(broken_selector)
            new_token = self.canonical_locator(match_id, best_candidate)

            heal_entry = {
                "timestamp": timestamp,
                **run_context.stamp(),
                "broken_selector": broken_selector,
                "recovered_selector": recovered_val,
                "healed_locator": healed_locator,
                "repaired_by": recovered.get("by", "") if recovered else "",
                "repaired_value": recovered.get("value", "") if recovered else "",
                "repaired_strategy": recovered.get("strategy", "") if recovered else "",
                "repaired_source": recovered.get("source", "") if recovered else "",
                "confidence_score": round(score, 2),
                "policy": policy,
                "status": status,
                "reason": reason,
                "recommendation": recommendation,
                "margin_over_second": round(margin, 2),
                "details": {"component_scores": metrics}
            }

            if approval_mode and script_path:
                from approval_workflow import workflow
                
                heal_id = workflow.queue_heal(
                    script_path=script_path,
                    old_locator=old_token,
                    new_locator=new_token,
                    confidence=score,
                    metrics=metrics,
                    line_number=line_number
                )
                
                lifecycle = "pending_approval"
                heal_entry["heal_id"] = heal_id
                heal_entry["status"] = "pending_approval"
            
            store.append("ui_heals", heal_entry)
            run_context.note_heal(heal_entry)

        return lifecycle, recovered_val, match_id

    def _generate_recommendation(self, match_id, best_candidate, score, policy):
        """Generate a QA recommendation (report §3.7).

        The useful recommendation is the concrete edit, not the advice to make
        one, so the repaired locator is rendered as the exact Selenium tuple the
        engineer can paste in place of the one that failed.
        """
        golden = self.fingerprints.get(match_id) if match_id else None
        if not golden:
            return "Review the healed locator manually."

        recs = []
        recovered = self.recover_locator(match_id, best_candidate)
        if recovered:
            by_const = self._BY_CONSTANTS.get(recovered["by"], "By.CSS_SELECTOR")
            replacement = f'({by_const}, "{recovered["value"]}")'
            if policy == "AUTOMATIC HEAL":
                recs.append(f"Update the test script to use {replacement}.")
            else:
                recs.append(f"Review before applying: {replacement}.")
            if recovered["source"] == "golden":
                recs.append(
                    "Note: the live element carries no identifying attribute, so this "
                    "locator is derived from the recorded baseline rather than the "
                    "current page."
                )
        elif policy == "AUTOMATIC HEAL":
            recs.append("Update the test script to use the repaired locator.")
        elif policy == "CAUTIOUS HEAL":
            recs.append("Review this heal in the dashboard before accepting it.")

        el_id = golden.get("element_id") or ""
        css = golden.get("css_class") or ""
        if not el_id and css:
            recs.append("Request a stable element ID from the developer — class-based locators are fragile.")
        elif not el_id:
            recs.append("Request a stable element ID from the developer.")

        if golden.get("tag_name") == "path" or golden.get("tag_name") == "svg":
            recs.append("SVG elements lack stable identifiers — consider adding a data-testid attribute.")

        if not recs:
            recs.append("No action needed — locator healed successfully.")
        return " ".join(recs)


class DynamicInfrastructureHealer:
    def __init__(self, history_path=config.METRICS_HISTORY_PATH):
        self.history_path = history_path
        self.data_dir = config.DATA_DIR

    def analyze_and_heal_system(self):
        """Analyzes metric snapshots to detect anomalies without hardcoded alert triggers."""
        try:
            with open(self.history_path, "r") as f:
                history = json.load(f)
        except Exception:
            return

        if not history:
            return
        
        current_state = history[-1]
        
        disk_stress = current_state.get("disk_usage_percent", 0) > 85.0
        error_rate_stress = current_state.get("error_rate_percent", 0) > 40.0
        is_down = current_state.get("service_health") == "Down" or current_state.get("http_status") == 500
        
        if is_down or (disk_stress and error_rate_stress):
            self.execute_infrastructure_heal(current_state, disk_stress, error_rate_stress)

    def _purge_temp_files(self):
        """Delete stale .tmp files left behind by interrupted atomic writes."""
        purged = 0
        for pattern in [
            os.path.join(self.data_dir, "*.tmp"),
            os.path.join(self.data_dir, "*.*.tmp"),
        ]:
            for tmp_file in glob.glob(pattern):
                try:
                    os.remove(tmp_file)
                    purged += 1
                except OSError:
                    pass
        return purged

    def _rotate_metrics_history(self, keep=20):
        """Truncate metrics_history.json to the last N entries (aggressive log rotation)."""
        try:
            with open(self.history_path, "r") as f:
                data = json.load(f)
            if len(data) <= keep:
                return 0
            trimmed = data[-keep:]
            removed = len(data) - keep
            tmp = self.history_path + ".rotating.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(trimmed, f, indent=2)
            os.replace(tmp, self.history_path)
            return removed
        except Exception:
            return 0

    def _reset_error_counters(self):
        """Write a recovery marker that signals the metrics monitor to reset its sliding window."""
        marker_path = os.path.join(self.data_dir, "recovery_marker.json")
        try:
            marker = {
                "timestamp": datetime.utcnow().isoformat() + "+00:00",
                "action": "error_counter_reset",
                "reason": "error_rate_stress_detected",
            }
            with open(marker_path, "w", encoding="utf-8") as f:
                json.dump(marker, f, indent=2)
            return True
        except Exception:
            return False

    def _restart_target_app(self):
        """Kill the stale process on the target app's port and relaunch it."""
        port = config.TARGET_APP_PORT
        killed_pid = None

        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if f":{port}" in line and "LISTENING" in line:
                        killed_pid = line.strip().split()[-1]
                        subprocess.run(
                            ["taskkill", "/F", "/PID", killed_pid],
                            capture_output=True, timeout=5
                        )
                        break
            else:
                result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True, text=True, timeout=5
                )
                for pid in result.stdout.strip().split():
                    killed_pid = pid
                    subprocess.run(
                        ["kill", "-9", pid],
                        capture_output=True, timeout=5
                    )
                    break
        except Exception as e:
            return f"Failed to kill stale process on port {port}: {e}"

        if killed_pid:
            time.sleep(0.5)

        app_script = os.path.join(config.BASE_DIR, "demo_target_app.py")
        if not os.path.exists(app_script):
            return f"Killed PID {killed_pid} but demo_target_app.py not found at {app_script}"

        try:
            creation_flags = 0
            if os.name == "nt":
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

            subprocess.Popen(
                [sys.executable, app_script, str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags if os.name == "nt" else 0,
                start_new_session=(os.name != "nt"),
            )
        except Exception as e:
            return f"Killed PID {killed_pid} but relaunch failed: {e}"

        for _ in range(10):
            time.sleep(0.5)
            try:
                req = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
                if req.status == 200:
                    return f"Killed stale PID {killed_pid}, relaunched on port {port} — verified responding"
            except Exception:
                pass

        return f"Killed PID {killed_pid}, relaunched on port {port} — not yet responding"

    def execute_infrastructure_heal(self, state, disk_stress, error_stress):
        timestamp = datetime.utcnow().isoformat() + "+00:00"
        actions_performed = []
        action_summary = ""

        if disk_stress:
            purged = self._purge_temp_files()
            rotated = self._rotate_metrics_history(keep=20)
            actions_performed.append(f"Purged {purged} temp file(s)")
            actions_performed.append(f"Rotated metrics history (removed {rotated} old entries)")
            action_summary = "Log Rotation & Temp File Purge"

        elif error_stress:
            reset = self._reset_error_counters()
            actions_performed.append(
                "Reset error counter sliding window" if reset else "Error counter reset failed"
            )
            action_summary = "Worker Pool Error Counter Reset"

        else:
            restart_result = self._restart_target_app()
            actions_performed.append(restart_result)
            action_summary = "Service Restart Attempt"

        store.append("infrastructure", {
            "timestamp": timestamp,
            "trigger_metric": f"Status: {state.get('http_status')}, Error: {state.get('error_rate_percent')}%, Disk: {state.get('disk_usage_percent')}%",
            "action_executed": action_summary,
            "actions_detail": actions_performed,
            "status": "resolved"
        })

        print(f"⚙️ Infrastructure heal: {action_summary} — {', '.join(actions_performed)}")

        if state.get("disk_usage_percent", 0) > 90.0:
            store.append("alerts", {
                "timestamp": timestamp,
                "severity": "critical",
                "message": f"Disk space critically low ({state.get('disk_usage_percent')}%). Automatic cleanup executed.",
                "source": "InfrastructureEngine"
            })