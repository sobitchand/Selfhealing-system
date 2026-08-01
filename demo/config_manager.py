"""
Configuration Manager — Read/write system configuration from dashboard.

Allows users to configure:
- Source heal target files
- Confidence thresholds
- Source healing enable/disable
- Infrastructure healing settings

Configuration is persisted to data/config_override.json and loaded at startup.
"""

import json
import os
import config


CONFIG_OVERRIDE_PATH = os.path.join(config.DATA_DIR, "config_override.json")


def load_override():
    """Load configuration overrides from disk."""
    if not os.path.exists(CONFIG_OVERRIDE_PATH):
        return {}
    try:
        with open(CONFIG_OVERRIDE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_override(overrides):
    """Save configuration overrides to disk."""
    os.makedirs(os.path.dirname(CONFIG_OVERRIDE_PATH), exist_ok=True)
    with open(CONFIG_OVERRIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)


def get_config():
    """Get current configuration (defaults + overrides)."""
    defaults = {
        "source_heal_enabled": config.SOURCE_HEAL_ENABLED,
        "source_heal_targets": config.SOURCE_HEAL_TARGETS,
        "confidence_threshold_high": config.CONFIDENCE_THRESHOLD_HIGH,
        "confidence_threshold_low": config.CONFIDENCE_THRESHOLD_LOW,
        "approval_mode_enabled": config.APPROVAL_MODE_ENABLED,
        "git_integration_enabled": config.GIT_INTEGRATION_ENABLED,
        "target_app_port": config.TARGET_APP_PORT,
        "bucket_limits": config.BUCKET_LIMITS,
        "active_fingerprint_path": config.ACTIVE_FINGERPRINT_PATH,
        "target_url": getattr(config, "TARGET_URL", f"http://127.0.0.1:{config.TARGET_APP_PORT}"),
        "target_html_file": getattr(config, "TARGET_HTML_FILE", ""),
    }
    
    overrides = load_override()
    defaults.update(overrides)
    
    return defaults


def update_config(key, value):
    """Update a single configuration value."""
    overrides = load_override()
    overrides[key] = value
    save_override(overrides)


def add_source_heal_target(file_path):
    """Add a file to the source heal targets list."""
    current = get_config()
    targets = current.get("source_heal_targets", [])
    
    if file_path not in targets:
        targets.append(file_path)
        update_config("source_heal_targets", targets)
        return True
    return False


def remove_source_heal_target(file_path):
    """Remove a file from the source heal targets list."""
    current = get_config()
    targets = current.get("source_heal_targets", [])
    
    if file_path in targets:
        targets.remove(file_path)
        update_config("source_heal_targets", targets)
        return True
    return False


def set_source_heal_enabled(enabled):
    """Enable or disable source code healing."""
    update_config("source_heal_enabled", enabled)


def set_approval_mode_enabled(enabled):
    """Enable or disable approval mode for script updates."""
    update_config("approval_mode_enabled", enabled)


def set_git_integration_enabled(enabled):
    """Enable or disable git integration for automatic PR creation."""
    update_config("git_integration_enabled", enabled)


def set_target_url(url):
    """Set the target application URL."""
    update_config("target_url", url)
    if hasattr(config, "TARGET_URL"):
        config.TARGET_URL = url


def set_target_html_file(file_path):
    """Set the target HTML file path."""
    update_config("target_html_file", file_path)
    if hasattr(config, "TARGET_HTML_FILE"):
        config.TARGET_HTML_FILE = file_path


def set_target_app_port(port):
    """Set the target application port."""
    update_config("target_app_port", port)
    config.TARGET_APP_PORT = port
    if hasattr(config, "TARGET_URL"):
        config.TARGET_URL = f"http://127.0.0.1:{port}"


def set_confidence_thresholds(high, low):
    """Set confidence thresholds for healing decisions."""
    update_config("confidence_threshold_high", high)
    update_config("confidence_threshold_low", low)


def reset_to_defaults():
    """Reset all configuration to defaults. Deletes override file and restores
    in-memory config module values to their built-in defaults.

    These values must track config.py exactly. APPROVAL_MODE_ENABLED in
    particular: defaulting it to False here would let one click on "Reset to
    Defaults" silently disable the human review gate, which is the one behaviour
    a QA team cannot audit.
    """
    if os.path.exists(CONFIG_OVERRIDE_PATH):
        os.remove(CONFIG_OVERRIDE_PATH)

    # Restore in-memory config module to built-in defaults
    config.SOURCE_HEAL_ENABLED = False
    config.SOURCE_HEAL_TARGETS = []
    config.CONFIDENCE_THRESHOLD_HIGH = 75.0
    config.CONFIDENCE_THRESHOLD_LOW = 20.0
    config.APPROVAL_MODE_ENABLED = True
    config.GIT_INTEGRATION_ENABLED = False
    config.TARGET_APP_PORT = int(os.environ.get("TARGET_APP_PORT", "8000"))
    config.TARGET_URL = os.environ.get("TARGET_URL", f"http://127.0.0.1:{config.TARGET_APP_PORT}")
    config.TARGET_HTML_FILE = os.environ.get("TARGET_HTML_FILE", "")
    # The baseline belongs to whichever app is registered as active, not to a
    # fixed path -- a config reset must not orphan the engine from its baseline.
    sync_active_app()


def sync_active_app():
    """Point config at the registered application marked active on disk.

    The application registry is the source of truth for which baseline the
    engine uses -- config.ACTIVE_FINGERPRINT_PATH is only a placeholder until an
    app is activated. A separately-launched process (the dashboard) has to read
    that choice back, or it reports a baseline nobody is healing against.

    Returns the active app record, or None when nothing is registered.
    """
    import app_registry

    record = app_registry.active_app()
    if not record:
        config.ACTIVE_FINGERPRINT_PATH = config.DEFAULT_FINGERPRINTS_PATH
        config.POMODORO_FINGERPRINTS_PATH = config.DEFAULT_FINGERPRINTS_PATH
        config.ACTIVE_APP_ID = ""
        return None

    config.ACTIVE_FINGERPRINT_PATH = record["fingerprint_path"]
    config.POMODORO_FINGERPRINTS_PATH = record["fingerprint_path"]
    config.ACTIVE_APP_ID = record["app_id"]
    if record.get("base_url"):
        config.TARGET_URL = record["base_url"]
    return record


def apply_overrides():
    """Apply configuration overrides to the config module.

    Call this at application startup to ensure all modules use the
    configured values instead of hardcoded defaults.
    """
    overrides = load_override()

    if "source_heal_enabled" in overrides:
        config.SOURCE_HEAL_ENABLED = overrides["source_heal_enabled"]
    
    if "source_heal_targets" in overrides:
        config.SOURCE_HEAL_TARGETS = overrides["source_heal_targets"]
    
    if "confidence_threshold_high" in overrides:
        config.CONFIDENCE_THRESHOLD_HIGH = overrides["confidence_threshold_high"]
    
    if "confidence_threshold_low" in overrides:
        config.CONFIDENCE_THRESHOLD_LOW = overrides["confidence_threshold_low"]
    
    if "approval_mode_enabled" in overrides:
        config.APPROVAL_MODE_ENABLED = overrides["approval_mode_enabled"]
    
    if "git_integration_enabled" in overrides:
        config.GIT_INTEGRATION_ENABLED = overrides["git_integration_enabled"]
    
    if "active_fingerprint_path" in overrides:
        fp_path = overrides["active_fingerprint_path"]
        if os.path.exists(fp_path):
            config.ACTIVE_FINGERPRINT_PATH = fp_path
            config.POMODORO_FINGERPRINTS_PATH = fp_path

    # Last, so the registry wins: an override written before the app was
    # re-registered would otherwise pin this process to a stale baseline while
    # the test runner heals against a different one.
    sync_active_app()

    if "target_url" in overrides:
        config.TARGET_URL = overrides["target_url"]

    if "target_html_file" in overrides:
        config.TARGET_HTML_FILE = overrides["target_html_file"]

    if "target_app_port" in overrides:
        config.TARGET_APP_PORT = overrides["target_app_port"]


def get_scan_directory():
    """Get the base directory for scanning test files."""
    return config.BASE_DIR


def scan_test_files(directory=None):
    """Scan directory for Python test files that could be source heal targets."""
    if directory is None:
        directory = get_scan_directory()
    
    test_files = []
    
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories and common non-test directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', '.git']]
        
        for file in files:
            if file.endswith('.py') and ('test' in file.lower() or 'page' in file.lower()):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, directory)
                test_files.append(rel_path)
    
    return sorted(test_files)


def get_fingerprint_files():
    """List all available fingerprint JSON files with metadata."""
    fingerprints = []
    
    search_dirs = [config.DATA_DIR, config.FINGERPRINT_DIR]
    
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        
        for filename in os.listdir(search_dir):
            if filename.endswith('_fingerprints.json') or filename.endswith('_fp.json'):
                full_path = os.path.join(search_dir, filename)
                
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    element_count = len(data) if isinstance(data, dict) else 0
                    
                    fingerprints.append({
                        'name': filename.replace('_fingerprints.json', '').replace('_fp.json', ''),
                        'filename': filename,
                        'path': full_path,
                        'element_count': element_count,
                        'is_active': full_path == config.ACTIVE_FINGERPRINT_PATH,
                    })
                except Exception:
                    fingerprints.append({
                        'name': filename.replace('_fingerprints.json', '').replace('_fp.json', ''),
                        'filename': filename,
                        'path': full_path,
                        'element_count': -1,
                        'is_active': full_path == config.ACTIVE_FINGERPRINT_PATH,
                    })
    
    return sorted(fingerprints, key=lambda x: x['name'])


def get_active_fingerprint():
    """Get the currently active fingerprint file path."""
    return config.ACTIVE_FINGERPRINT_PATH


def set_active_fingerprint(path):
    """Switch to a different fingerprint file. Returns True if successful."""
    if not os.path.exists(path):
        return False
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            json.load(f)
        
        config.ACTIVE_FINGERPRINT_PATH = path
        config.POMODORO_FINGERPRINTS_PATH = path
        
        update_config("active_fingerprint_path", path)
        
        return True
    except Exception:
        return False


def create_fingerprint_file(app_name):
    """Create a new empty fingerprint file for an app."""
    if not app_name:
        return None
    
    safe_name = app_name.lower().replace(' ', '_').replace('-', '_')
    filename = f"{safe_name}_fingerprints.json"
    
    os.makedirs(config.FINGERPRINT_DIR, exist_ok=True)
    filepath = os.path.join(config.FINGERPRINT_DIR, filename)
    
    if os.path.exists(filepath):
        return filepath
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2)
        return filepath
    except Exception:
        return None


def delete_fingerprint_file(path):
    """Delete a fingerprint file. Returns True if successful."""
    if not os.path.exists(path):
        return False
    
    if path == config.ACTIVE_FINGERPRINT_PATH:
        return False
    
    try:
        os.remove(path)
        return True
    except Exception:
        return False


def get_fingerprint_preview(path, max_elements=5):
    """Get a preview of a fingerprint file's contents."""
    if not os.path.exists(path):
        return None
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            return None
        
        preview = {
            'total_elements': len(data),
            'elements': []
        }
        
        for key, fp in list(data.items())[:max_elements]:
            preview['elements'].append({
                'key': key,
                'tag': fp.get('tag_name', 'unknown'),
                'text': fp.get('inner_text', '')[:50],
                'locator_by': fp.get('locator_by', 'unknown'),
                'locator_value': fp.get('locator_value', 'unknown'),
            })
        
        return preview
    except Exception:
        return None
