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
import difflib
from datetime import datetime
from pathlib import Path

import config
import store


def _whole_token_pattern(token):
    """Match `token` only when not flanked by identifier chars, so a stale
    `clear` never corrupts an unrelated `clearing` and a renamed `clearBtn`
    never re-matches the healed `clrBtn`. Mirrors source_healer._whole_token_pattern
    so the approval apply and the auto source-writeback behave identically."""
    return re.compile(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])")


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
        tmp = self.queue_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)
        os.replace(tmp, self.queue_path)

    def queue_heal(self, script_path, old_locator, new_locator, confidence, metrics, line_number=None):
        """Add a healed locator to the approval queue.
        
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
            "confidence": round(confidence, 2),
            "metrics": metrics,
            "line_number": line_number,
            "status": "pending",
            "diff": self._generate_diff(script_path, old_locator, new_locator)
        }
        
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

    def _generate_diff(self, script_path, old_locator, new_locator):
        """Generate a unified diff showing what will change."""
        if not os.path.exists(script_path):
            return "Script file not found"
        
        with open(script_path, "r", encoding="utf-8") as f:
            original_lines = f.readlines()
        
        pattern = _whole_token_pattern(old_locator)
        modified_lines = [pattern.sub(new_locator, line) for line in original_lines]
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"{Path(script_path).name} (before)",
            tofile=f"{Path(script_path).name} (after)",
            lineterm=""
        )
        
        return "".join(diff)

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

    def approve_heal(self, heal_id):
        """Apply the healed locator to the script and mark as approved."""
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
                    with open(script_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    pattern = _whole_token_pattern(heal["old_locator"])
                    if not pattern.search(content):
                        heal["status"] = "failed"
                        heal["error"] = "Old locator not found in script"
                        self._write_queue(queue)
                        return False, "Old locator not found in script"
                    
                    updated_content = pattern.sub(heal["new_locator"], content)
                    
                    with open(script_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    
                    heal["status"] = "approved"
                    heal["approved_at"] = datetime.utcnow().isoformat() + "+00:00"
                    
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
