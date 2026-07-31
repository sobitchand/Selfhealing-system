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
        """Compares structural tree layouts instead of looking for exact matching string tokens."""
        if not xpath1 or not xpath2:
            return 0.0
        layers1 = xpath1.split("/")
        layers2 = xpath2.split("/")
        matches = sum(1 for l1, l2 in zip(layers1, layers2) if l1 == l2)
        return (matches / max(len(layers1), len(layers2))) * 100.0

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

                scored.append((composite_score, cand, {
                    "R1_inner_text_40": round(r1, 2),
                    "R2_xpath_pattern_30": round(r2, 2),
                    "R3_css_class_20": round(r3, 2),
                    "R4_neighbors_10": round(r4, 2),
                }, weights))

            if not scored:
                continue

            scored.sort(key=lambda x: x[0], reverse=True)
            top_score, top_cand, top_metrics, top_weights = scored[0]

            if top_score > highest_score:
                highest_score = top_score
                best_match_id = element_key
                best_candidate = top_cand
                winning_metrics = top_metrics
                second_score = scored[1][0] if len(scored) > 1 else 0.0

                # Reason for repair (report §3.7): "A generated explanation stating
                # which attributes matched, which changed, and which rules
                # determined the outcome."
                reason = self._build_reason(golden, top_cand, top_metrics, tag_penalty)

        return best_match_id, highest_score, winning_metrics, best_candidate, reason, second_score

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
        golden = self.fingerprints.get(match_id) if match_id else None
        if not golden:
            return ""

        # 1. Live id (preferred — reflects the CURRENT state after refactor)
        live_id = (best_candidate or {}).get("id") or ""
        if live_id:
            return live_id

        # 2. Golden element id
        element_id = golden.get("element_id") or ""
        if element_id:
            return element_id

        # 3. name attribute
        live_name = (best_candidate or {}).get("name") or ""
        golden_name = golden.get("element_name") or ""
        if live_name:
            return live_name
        if golden_name:
            return golden_name

        # 4-6. data-* attributes
        for attr in ("data-testid", "data-test", "data-qa"):
            live_val = (best_candidate or {}).get(attr.replace("-", "_"), "")
            if not live_val:
                live_val = (best_candidate or {}).get("dataset", "")
                if isinstance(live_val, str) and attr in live_val:
                    import json as _json
                    try:
                        ds = _json.loads(live_val)
                        live_val = ds.get(attr, "")
                    except Exception:
                        live_val = ""
            golden_attrs = golden.get("data_attrs", {})
            if live_val:
                return live_val
            if golden_attrs.get(attr):
                return golden_attrs[attr]

        # 6. aria-label
        live_aria = (best_candidate or {}).get("aria_label") or ""
        golden_aria = golden.get("aria_label") or ""
        if live_aria:
            return live_aria
        if golden_aria:
            return golden_aria

        # 7. text content
        live_text = (best_candidate or {}).get("inner_text") or ""
        golden_text = golden.get("inner_text") or ""
        tag = (best_candidate or {}).get("tag_name") or golden.get("tag_name") or ""
        if live_text and tag:
            return f"{tag}[text='{live_text}']"
        if golden_text and tag:
            return f"{tag}[text='{golden_text}']"

        # 8. css class
        live_css = (best_candidate or {}).get("css_class") or ""
        golden_css = golden.get("css_class") or ""
        if live_css and tag:
            primary = live_css.split()[0]
            return f"{tag}.{primary}"
        if golden_css and tag:
            primary = golden_css.split()[0]
            return f"{tag}.{primary}"

        # 9. locator value from fingerprint
        return str(golden.get("locator_value", "")).lstrip("#")

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
        live_id = (best_candidate or {}).get("id") or ""
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
        live_name = (best_candidate or {}).get("name") or ""
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
        token = self.canonical_locator(match_id, best_candidate)
        if not token or match_id not in self.fingerprints:
            return ""
        healed_value = f"#{token}"
        try:
            self.fingerprints[match_id]["healed_locator_value"] = healed_value
            self.fingerprints[match_id]["healed_locator_by"] = "css selector"
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

        recovered_val = "unknown"
        if match_id and match_id in self.fingerprints:
            golden_el = self.fingerprints[match_id]
            css = golden_el.get("css_class", "")
            classes = css.replace(" ", ".") if css else ""
            recovered_val = f"{golden_el['tag_name']}.{classes}" if classes else golden_el['tag_name']

        if status == "failed":
            store.append("alerts", {
                "timestamp": timestamp,
                "severity": "critical",
                "message": (
                    f"Recovery declined for {broken_selector}: best match scored "
                    f"{score:.1f}%, below the {config.CONFIDENCE_THRESHOLD_LOW:.0f}% "
                    f"safety gate. No element was clicked."
                ),
                "source": "UIHeuristicEngine"
            })
        else:
            healed_locator = self.update_metadata_locator(match_id, best_candidate)

            old_token = self._broken_source_token(broken_selector)
            new_token = self.canonical_locator(match_id, best_candidate)

            if healed_locator:
                recovered_val = healed_locator

            heal_entry = {
                "timestamp": timestamp,
                "broken_selector": broken_selector,
                "recovered_selector": recovered_val,
                "healed_locator": healed_locator,
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

        return lifecycle, recovered_val, match_id

    def _generate_recommendation(self, match_id, best_candidate, score, policy):
        """Generate a QA recommendation (report §3.7)."""
        golden = self.fingerprints.get(match_id) if match_id else None
        if not golden:
            return "Review the healed locator manually."

        recs = []
        if policy == "AUTOMATIC HEAL":
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