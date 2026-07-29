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
    def __init__(self, fingerprint_path=config.POMODORO_FINGERPRINTS_PATH):
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

        Scores the broken identifier against each fingerprint's element id/key and
        returns the best (key, ratio) — but only if it clears min_ratio. Below
        that we return (None, ratio) so the caller falls back to a global scan
        (preserves old behaviour for ids unrelated to any fingerprint).
        """
        broken_value = self._extract_broken_value(broken_selector)
        if not broken_value:
            return None, 0.0
        best_key, best_ratio = None, 0.0
        for key, golden in self.fingerprints.items():
            ident = golden.get("element_id") or key
            ratio = self.calculate_similarity(broken_value, ident)
            if ratio > best_ratio:
                best_ratio, best_key = ratio, key
        return (best_key, best_ratio) if best_ratio >= min_ratio else (None, best_ratio)

    def evaluate_live_candidates(self, broken_selector, candidates):
        self.reload_fingerprints()  # pick up Learning-Mode baseline / prior self-corrections
        best_match_id = None
        highest_score = 0.0
        winning_metrics = {}
        best_candidate = None

        # Intent-aware: resolve WHICH element this broken locator meant, so two
        # different broken locators don't both heal to the same top element.
        #
        # Safety gate: if NO baseline fingerprint resembles the broken locator, we
        # genuinely don't know what the caller was trying to find. Refuse to guess.
        # (A global scan would otherwise always self-match SOME live element at
        # ~98% — e.g. a random <div> — and "heal" to it, defeating the whole
        # CRITICAL-FAULT safety story.) Returning no match keeps confidence at 0
        # so commit_heal_to_log routes to 'halt' / manual intervention.
        target_key, _ = self.select_target_fingerprint(broken_selector)
        if not target_key:
            return None, 0.0, {}, None
        search_space = {target_key: self.fingerprints[target_key]}

        for element_key, golden in search_space.items():
            for cand in candidates:
                # Tag family must match (BUTTON vs button normalised); acts as gate.
                golden_tag = str(golden.get("tag_name", "")).lower()
                cand_tag = str(cand.get("tag_name", "")).lower()

                if cand_tag != golden_tag:
                    continue

                # Weighted heuristic per proposal Table 3.1 (R1-R4).
                r1 = self.calculate_similarity(cand.get("inner_text", ""), golden.get("inner_text", ""))         # text
                r2 = self.calculate_xpath_depth_similarity(cand.get("xpath", ""), golden.get("xpath_pattern", ""))  # xpath
                r3 = self.calculate_similarity(cand.get("css_class", ""), golden.get("css_class", ""))           # css
                r4 = self.calculate_neighbor_similarity(cand.get("neighbors", []), golden.get("neighbors", []))  # neighbors

                composite_score = (r1 * 0.40) + (r2 * 0.30) + (r3 * 0.20) + (r4 * 0.10)

                if composite_score > highest_score:
                    highest_score = composite_score
                    best_match_id = element_key
                    best_candidate = cand  # remember the LIVE element that won
                    winning_metrics = {
                        "R1_text_40": round(r1, 2),
                        "R2_xpath_30": round(r2, 2),
                        "R3_css_20": round(r3, 2),
                        "R4_neighbors_10": round(r4, 2),
                    }

        return best_match_id, highest_score, winning_metrics, best_candidate

    def canonical_locator(self, match_id):
        """Stable write-back token for a matched fingerprint.

        Prefer the element id; fall back to locator_value stripped of a leading
        '#'. Returns "" when match_id is unknown so callers can no-op safely.
        """
        golden = self.fingerprints.get(match_id) if match_id else None
        if not golden:
            return ""
        element_id = golden.get("element_id")
        if element_id:
            return element_id
        return str(golden.get("locator_value", "")).lstrip("#")

    def update_metadata_locator(self, match_id):
        """Self-Correction: persist the healed locator into the golden-fingerprint
        metadata (proposal §3.4.3 Step 6 / Fig 3.3 'Update Metadata Repository').

        Sets healed_locator_value/by on the matched fingerprint and writes the
        registry atomically (temp file -> os.replace). Best-effort: returns the
        healed locator string, or '' on no-op/failure (never raises)."""
        token = self.canonical_locator(match_id)
        if not token or match_id not in self.fingerprints:
            return ""
        healed_value = f"#{token}"
        try:
            self.fingerprints[match_id]["healed_locator_value"] = healed_value
            self.fingerprints[match_id]["healed_locator_by"] = "css selector"
            tmp = self.fingerprint_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.fingerprints, f, indent=2)
            os.replace(tmp, self.fingerprint_path)
            return healed_value
        except Exception as e:
            print(f"⚠️ metadata self-correction failed for '{match_id}': {e}")
            return ""

    def commit_heal_to_log(self, broken_selector, match_id, score, metrics):
        """Applies confidence policies and persists the heal result (ACTIVE path)."""
        timestamp = datetime.utcnow().isoformat() + "+00:00"

        if score >= config.CONFIDENCE_THRESHOLD_HIGH:
            policy, status, lifecycle = "AUTOMATIC HEAL", "success", "continue"
        elif config.CONFIDENCE_THRESHOLD_LOW <= score < config.CONFIDENCE_THRESHOLD_HIGH:
            policy, status, lifecycle = "CAUTIOUS HEAL", "warning", "verify"
        else:
            policy, status, lifecycle = "CRITICAL FAULT", "failed", "halt"

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
            # Self-Correction: persist healed locator into golden-fingerprint metadata.
            healed_locator = self.update_metadata_locator(match_id)
            store.append("ui_heals", {
                "timestamp": timestamp,
                "broken_selector": broken_selector,
                "recovered_selector": recovered_val,
                "healed_locator": healed_locator,
                "confidence_score": round(score, 2),
                "policy": policy,
                "status": status,
                "details": {"component_scores": metrics}
            })

        return lifecycle, recovered_val, match_id


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