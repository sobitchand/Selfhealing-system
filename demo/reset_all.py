"""
Full reset -- put the dashboard back to a virgin state.

    python reset_all.py              # wipe EVERYTHING (the default)
    python reset_all.py --keep-apps  # keep registered apps and their baselines
    python reset_all.py --backup     # copy data/ to data_backup_<stamp> first

After a default run the dashboard shows nothing but the apps and tests YOU
create. reset_demo.py is not a substitute: it only clears the buckets named in
config.BUCKETS, which excludes approval_queue.json, and it never touches
pending_heals.json or the application registry.
"""

import json
import os
import shutil
import sys
from datetime import datetime

import config
import store


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2)
    store.replace_atomic(tmp, path)


def backup():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(config.BASE_DIR, f"data_backup_{stamp}")
    shutil.copytree(config.DATA_DIR, dest)
    print(f"  backed up data/ -> {os.path.basename(dest)}/")


def clear_buckets():
    """Every *.json under data/buckets -- not just those in config.BUCKETS."""
    if not os.path.isdir(config.BUCKET_DIR):
        return
    for name in sorted(os.listdir(config.BUCKET_DIR)):
        if name.endswith(".json"):
            _write(os.path.join(config.BUCKET_DIR, name), [])
            print(f"  cleared bucket: {name}")


def clear_runtime_state():
    _write(os.path.join(config.DATA_DIR, "pending_heals.json"), [])
    _write(config.METRICS_HISTORY_PATH, [])
    _write(os.path.join(config.DATA_DIR, "heal_state.json"), {})
    print("  cleared pending_heals.json, metrics_history.json, heal_state.json")


def clear_stale_backups():
    backups = os.path.join(config.DATA_DIR, "backups")
    if not os.path.isdir(backups):
        return
    removed = 0
    for name in os.listdir(backups):
        if name.endswith((".py", ".bak")):
            os.remove(os.path.join(backups, name))
            removed += 1
    if removed:
        print(f"  removed {removed} stale file(s) from data/backups/")


def forget_apps():
    for sub in ("runs", "tests", "apps", "fingerprints"):
        path = os.path.join(config.DATA_DIR, sub)
        if os.path.isdir(path):
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)
        print(f"  emptied data/{sub}/")

    # Loose fingerprint files sitting directly in data/ also appear in the
    # Configuration tab: config_manager searches DATA_DIR as well as
    # FINGERPRINT_DIR when it lists profiles.
    for name in os.listdir(config.DATA_DIR):
        if "fingerprint" in name.lower() and name.endswith(".json"):
            os.remove(os.path.join(config.DATA_DIR, name))
            print(f"  removed data/{name}")

    override = os.path.join(config.DATA_DIR, "config_override.json")
    if os.path.exists(override):
        os.remove(override)
        print("  removed config_override.json (Configuration back to defaults)")


def main():
    keep_apps = "--keep-apps" in sys.argv

    print("=== RESET ===")
    if "--backup" in sys.argv:
        backup()

    clear_buckets()
    clear_runtime_state()
    clear_stale_backups()

    if keep_apps:
        print("  (kept apps, baselines and runs -- omit --keep-apps for a full wipe)")
    else:
        forget_apps()

    print("\nDone. Restart the dashboard, then hard-refresh the browser (Ctrl+Shift+R).")
    if not keep_apps:
        print("\nNothing is registered. Create your own app with:")
        print('  python cli.py register --app mystore --name "MyStore Checkout" \\')
        print('      --url "file:///D:/Selfhealing-system/demo/examples/mystore/index.html"')


if __name__ == "__main__":
    main()
