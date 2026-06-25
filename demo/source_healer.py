"""
Source-code self-healing: write a healed locator back into the test/automation
source so a broken selector is permanently fixed after one high-confidence heal.

This is the persistent counterpart to the runtime heal in automation_wrapper.py.
The runtime heal keeps the current run alive; patch_source() makes the fix stick
so future runs need no heal at all.

Safety contract:
  * Gated     -- only runs when config.SOURCE_HEAL_ENABLED.
  * Idempotent-- a no-op once the broken token is gone (or equals the healed one).
  * Reversible-- each file gets a one-time <file>.bak before its first edit.
  * Atomic    -- write <file>.tmp then os.replace (same idiom as store.append).
  * Best-effort-- never raises into the caller; a patch failure must not crash
                 the automation run. Failures are printed and logged to alerts.
"""

import os
import re
import shutil
from datetime import datetime

import config
import store


def _now():
    return datetime.utcnow().isoformat() + "+00:00"


def _whole_token_pattern(token):
    """Match `token` only when not flanked by identifier chars, so a stale
    `old-start` never corrupts an unrelated `old-start-button`."""
    return re.compile(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])")


def patch_source(broken_token, healed_token):
    """Replace `broken_token` with `healed_token` across config.SOURCE_HEAL_TARGETS.

    Returns the number of files patched (0 on no-op / disabled / error).
    """
    if not config.SOURCE_HEAL_ENABLED:
        return 0
    if not healed_token or not broken_token or broken_token == healed_token:
        return 0  # nothing stable to write back, or already healed (idempotent)

    pattern = _whole_token_pattern(broken_token)
    files_patched = 0

    for path in config.SOURCE_HEAL_TARGETS:
        try:
            if not os.path.exists(path):
                continue

            with open(path, "r", encoding="utf-8") as f:
                original = f.read()

            new_text, count = pattern.subn(healed_token, original)
            if count == 0:
                continue  # token absent -> already healed or wrong file

            # One-time backup so the demo can be reset by restoring <file>.bak.
            bak = path + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(path, bak)

            # Atomic swap: write temp then os.replace (mirror store.append).
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(new_text)
            os.replace(tmp, path)

            files_patched += 1
            print(f"📝 Source healed: {os.path.basename(path)} "
                  f"'{broken_token}' -> '{healed_token}' ({count}x)")

            store.append("source_heals", {
                "timestamp": _now(),
                "file": os.path.basename(path),
                "broken_token": broken_token,
                "healed_token": healed_token,
                "occurrences": count,
                "status": "patched",
            })
        except Exception as e:
            print(f"❌ source_healer failed on {path}: {e}")
            store.append("alerts", {
                "timestamp": _now(),
                "severity": "warning",
                "message": f"Source write-back failed for {os.path.basename(path)}: {e}",
                "source": "SourceHealer",
            })

    return files_patched
