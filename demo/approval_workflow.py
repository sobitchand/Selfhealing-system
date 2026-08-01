"""
Approval Workflow: Safe script update with human review.

Instead of silently updating QA test scripts, this module:
1. Queues healed locators for review
2. Shows diffs in the dashboard
3. Only updates scripts after explicit approval
4. Maintains backups for rollback

This transforms the system from "silent auto-update" to "interactive approval"
which is the industry best practice (Testim, Mabl, Healenium all use this pattern).
"""

import json
import os
import re
import shutil
import time
import difflib
from datetime import datetime
from pathlib import Path

from filelock import FileLock, Timeout

import config
import store

LOCK_TIMEOUT = 10  # seconds, matching store.py

# The retried atomic swap lives in store.py, so every writer in the project
# shares one implementation rather than each rediscovering the Windows race.
_replace_with_retry = store.replace_atomic

# Selenium strategy name (as the engine reports it) -> the By.* constant a QA
# script writes. Needed because a heal may recover a MORE stable strategy than
# the one that broke, and the write-back must move the constant with the value.
_BY_CONST = {
    "id": "By.ID",
    "name": "By.NAME",
    "css selector": "By.CSS_SELECTOR",
    "xpath": "By.XPATH",
    "link text": "By.LINK_TEXT",
    "partial link text": "By.PARTIAL_LINK_TEXT",
    "class name": "By.CLASS_NAME",
    "tag name": "By.TAG_NAME",
}


def _swap_in_line(line, old_value, new_value, old_by=None, new_by=None):
    """Rewrite one source line, returning (line, changed).

    Swaps the quoted locator value, and the By.* constant too when the recovered
    strategy differs from the one the script used. Writing an id into a
    `By.NAME` lookup -- or a bare id into a `By.CSS_SELECTOR` that still carries
    a leading '.' -- produces a script that no longer resolves anything, which
    is worse than not patching at all.
    """
    updated, changed = line, False

    for quote in ('"', "'"):
        needle = quote + old_value + quote
        if needle in updated:
            out = quote if quote not in new_value else ("'" if quote == '"' else '"')
            updated = updated.replace(needle, out + new_value + out, 1)
            changed = True
            break

    if not changed:
        # Unquoted or awkwardly escaped: fall back to a word-bounded swap so a
        # stale `old-btn` never corrupts an unrelated `old-btn-wrapper`.
        pattern = re.compile(r"(?<![\w-])" + re.escape(old_value) + r"(?![\w-])")
        updated, hits = pattern.subn(new_value, updated, count=1)
        changed = bool(hits)

    if not changed:
        return line, False

    if old_by and new_by and old_by != new_by:
        old_const, new_const = _BY_CONST.get(old_by), _BY_CONST.get(new_by)
        if old_const and new_const:
            updated = re.sub(r"\b" + re.escape(old_const) + r"\b", new_const, updated, count=1)

    return updated, True


class ApprovalWorkflow:
    def __init__(self, queue_path=None):
        if queue_path is None:
            queue_path = os.path.join(config.DATA_DIR, "pending_heals.json")
        self.queue_path = queue_path
        self._ensure_queue_file()

    def _ensure_queue_file(self):
        if not os.path.exists(self.queue_path):
            self._write_queue([])

    def _read_queue(self):
        try:
            with open(self.queue_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_queue(self, queue):
        """Atomically replace the queue file, under the same cross-process lock
        discipline store.py uses for the telemetry buckets.

        Without the lock this raced the dashboard, which re-reads the queue every
        three seconds: on Windows os.replace() onto a file another process has
        open fails with [WinError 5] Access is denied. That exception surfaced
        out of attempt_heal() as a NoSuchElementException, so a heal that had
        already succeeded aborted the run and looked like a healing failure --
        and it only happened when the dashboard was open, which is exactly how
        the system is demonstrated.
        """
        tmp = self.queue_path + ".tmp"
        lock_path = self.queue_path + ".lock"
        try:
            with FileLock(lock_path, timeout=LOCK_TIMEOUT):
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(queue, f, indent=2)
                _replace_with_retry(tmp, self.queue_path)
        except Timeout:
            print(f"⚠️ approval queue: timed out acquiring lock for {self.queue_path}")

    def queue_heal(self, script_path, old_locator, new_locator, confidence, metrics,
                   line_number=None, old_by=None, new_by=None, new_value=None):
        """Add a healed locator to the approval queue.

        old_by / new_by / new_value carry the locator STRATEGY alongside the
        value. Without them the write-back cannot know that, say, an XPath was
        recovered as an id, and would paste the id into a By.XPATH lookup.

        Returns the heal_id for tracking.
        """
        queue = self._read_queue()

        heal_id = f"heal_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{len(queue)}"

        backup_path = self._create_backup(script_path)

        heal_entry = {
            "heal_id": heal_id,
            "timestamp": datetime.utcnow().isoformat() + "+00:00",
            "script_path": os.path.abspath(script_path),
            "backup_path": backup_path,
            "old_locator": old_locator,
            "new_locator": new_locator,
            "old_by": old_by or "",
            "new_by": new_by or "",
            "new_value": new_value or new_locator,
            "confidence": round(confidence, 2),
            "metrics": metrics,
            "line_number": line_number,
            "status": "pending",
        }
        heal_entry["diff"] = self._generate_diff(script_path, heal_entry)

        queue.append(heal_entry)
        self._write_queue(queue)
        
        store.append("approval_queue", {
            "timestamp": heal_entry["timestamp"],
            "heal_id": heal_id,
            "script": os.path.basename(script_path),
            "confidence": heal_entry["confidence"],
            "status": "queued"
        })
        
        return heal_id

    def _create_backup(self, script_path):
        """Create a timestamped backup of the script before any changes."""
        if not os.path.exists(script_path):
            return None
        
        backup_dir = os.path.join(config.DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{Path(script_path).stem}_{timestamp}{Path(script_path).suffix}"
        backup_path = os.path.join(backup_dir, backup_name)
        
        shutil.copy2(script_path, backup_path)
        return backup_path

    def _target_line(self, lines, heal):
        """Index of the line to patch, or -1 when it cannot be pinned down.

        Prefers the line number recorded at heal time; falls back to a unique
        textual match. Refusing an ambiguous match is deliberate -- patching the
        wrong occurrence is far more damaging than declining to patch.
        """
        old_value = heal.get("old_locator") or ""
        if not old_value:
            return -1

        recorded = heal.get("line_number")
        if isinstance(recorded, int) and 1 <= recorded <= len(lines):
            if old_value in lines[recorded - 1]:
                return recorded - 1

        hits = [i for i, line in enumerate(lines) if old_value in line]
        return hits[0] if len(hits) == 1 else -1

    def _patched_lines(self, lines, heal):
        """Apply one heal to a copy of `lines`. Returns (lines, index) or (lines, -1)."""
        index = self._target_line(lines, heal)
        if index < 0:
            return lines, -1

        updated, changed = _swap_in_line(
            lines[index],
            heal.get("old_locator") or "",
            heal.get("new_value") or heal.get("new_locator") or "",
            heal.get("old_by"),
            heal.get("new_by"),
        )
        if not changed:
            return lines, -1

        patched = list(lines)
        patched[index] = updated
        return patched, index

    def _generate_diff(self, script_path, heal):
        """Unified diff of exactly what approving this heal will do."""
        if not os.path.exists(script_path):
            return "Script file not found"

        with open(script_path, "r", encoding="utf-8") as f:
            original_lines = f.readlines()

        modified_lines, index = self._patched_lines(original_lines, heal)
        if index < 0:
            return "Could not pin down the line to patch (was the script edited?)"

        # lineterm="" leaves the ---/+++/@@ headers without a trailing newline, so
        # the lines must be joined on "\n" rather than concatenated -- otherwise the
        # three headers and the first context line render as one run-on line.
        diff = difflib.unified_diff(
            [line.rstrip("\n") for line in original_lines],
            [line.rstrip("\n") for line in modified_lines],
            fromfile=f"{Path(script_path).name} (before)",
            tofile=f"{Path(script_path).name} (after)",
            lineterm=""
        )

        return "\n".join(diff)

    def get_pending_heals(self):
        """Return all heals awaiting approval."""
        queue = self._read_queue()
        return [h for h in queue if h["status"] == "pending"]

    def get_heal_by_id(self, heal_id):
        """Retrieve a specific heal entry."""
        queue = self._read_queue()
        for heal in queue:
            if heal["heal_id"] == heal_id:
                return heal
        return None

    def approve_heal(self, heal_id, create_pr=False):
        """Apply the healed locator to the script and mark as approved.
        
        create_pr: If True and git integration is enabled, create a PR for the heal.
        """
        queue = self._read_queue()
        
        for heal in queue:
            if heal["heal_id"] == heal_id and heal["status"] == "pending":
                script_path = heal["script_path"]
                
                if not os.path.exists(script_path):
                    heal["status"] = "failed"
                    heal["error"] = "Script file not found"
                    self._write_queue(queue)
                    return False, "Script file not found"
                
                try:
                    # newline="" on both ends preserves the file's existing line
                    # endings verbatim. Without it Python translates on read and
                    # re-translates on write, so a one-line fix rewrites every
                    # line ending in the file and `git diff` reports the whole
                    # script as changed -- burying the actual repair.
                    with open(script_path, "r", encoding="utf-8", newline="") as f:
                        original_lines = f.readlines()

                    patched_lines, index = self._patched_lines(original_lines, heal)
                    if index < 0:
                        heal["status"] = "failed"
                        heal["error"] = "Could not pin down the line to patch"
                        self._write_queue(queue)
                        return False, ("Could not pin down the line to patch -- the "
                                       "script may have changed since the heal was queued.")

                    tmp = script_path + ".tmp"
                    with open(tmp, "w", encoding="utf-8", newline="") as f:
                        f.writelines(patched_lines)
                    # Retried: the QA engineer almost certainly has this script
                    # open in an editor while reviewing the diff, and on Windows
                    # that alone can block the replace.
                    _replace_with_retry(tmp, script_path)

                    heal["patched_line"] = index + 1
                    heal["patched_text"] = patched_lines[index].strip()

                    heal["status"] = "approved"
                    heal["approved_at"] = datetime.utcnow().isoformat() + "+00:00"
                    
                    # Optionally create PR if git integration is enabled
                    pr_url = None
                    if create_pr and config.GIT_INTEGRATION_ENABLED:
                        try:
                            from git_integration import git_integration
                            success, result, branch = git_integration.create_pr_for_heal(
                                heal_id=heal_id,
                                script_path=script_path,
                                old_locator=heal["old_locator"],
                                new_locator=heal["new_locator"],
                                confidence=heal["confidence"]
                            )
                            if success:
                                pr_url = result
                                heal["pr_url"] = pr_url
                                heal["pr_branch"] = branch
                        except Exception as e:
                            heal["pr_error"] = str(e)
                    
                    self._write_queue(queue)
                    
                    store.append("approval_queue", {
                        "timestamp": heal["approved_at"],
                        "heal_id": heal_id,
                        "script": os.path.basename(script_path),
                        "confidence": heal["confidence"],
                        "status": "approved",
                        "pr_url": pr_url
                    })
                    
                    msg = "Script updated successfully"
                    if pr_url:
                        msg += f" | PR created: {pr_url}"
                    
                    return True, msg
                    
                except Exception as e:
                    heal["status"] = "failed"
                    heal["error"] = str(e)
                    self._write_queue(queue)
                    return False, str(e)
        
        return False, "Heal not found or already processed"

    def reject_heal(self, heal_id, reason=None):
        """Reject the heal and leave the script unchanged."""
        queue = self._read_queue()
        
        for heal in queue:
            if heal["heal_id"] == heal_id and heal["status"] == "pending":
                heal["status"] = "rejected"
                heal["rejected_at"] = datetime.utcnow().isoformat() + "+00:00"
                if reason:
                    heal["rejection_reason"] = reason
                self._write_queue(queue)
                
                store.append("approval_queue", {
                    "timestamp": heal["rejected_at"],
                    "heal_id": heal_id,
                    "script": os.path.basename(heal["script_path"]),
                    "confidence": heal["confidence"],
                    "status": "rejected"
                })
                
                return True, "Heal rejected"
        
        return False, "Heal not found or already processed"

    def rollback_heal(self, heal_id):
        """Restore the script from backup (undo an approved heal)."""
        heal = self.get_heal_by_id(heal_id)
        
        if not heal:
            return False, "Heal not found"
        
        if heal["status"] != "approved":
            return False, "Can only rollback approved heals"
        
        backup_path = heal.get("backup_path")
        if not backup_path or not os.path.exists(backup_path):
            return False, "Backup file not found"
        
        script_path = heal["script_path"]
        
        try:
            shutil.copy2(backup_path, script_path)
            
            heal["status"] = "rolled_back"
            heal["rolled_back_at"] = datetime.utcnow().isoformat() + "+00:00"
            
            queue = self._read_queue()
            for h in queue:
                if h["heal_id"] == heal_id:
                    h["status"] = "rolled_back"
                    h["rolled_back_at"] = heal["rolled_back_at"]
                    break
            self._write_queue(queue)
            
            store.append("approval_queue", {
                "timestamp": heal["rolled_back_at"],
                "heal_id": heal_id,
                "script": os.path.basename(script_path),
                "status": "rolled_back"
            })
            
            return True, "Script restored from backup"
            
        except Exception as e:
            return False, str(e)

    def get_history(self, limit=20):
        """Return recent heal history (all statuses)."""
        queue = self._read_queue()
        sorted_queue = sorted(queue, key=lambda h: h["timestamp"], reverse=True)
        return sorted_queue[:limit]

    def clear_completed(self):
        """Remove approved/rejected/rolled_back entries from queue."""
        queue = self._read_queue()
        pending = [h for h in queue if h["status"] == "pending"]
        removed = len(queue) - len(pending)
        self._write_queue(pending)
        return removed


workflow = ApprovalWorkflow()
