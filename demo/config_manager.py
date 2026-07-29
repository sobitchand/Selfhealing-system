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
        "target_app_port": config.TARGET_APP_PORT,
        "bucket_limits": config.BUCKET_LIMITS,
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


def set_confidence_thresholds(high, low):
    """Set confidence thresholds for healing decisions."""
    update_config("confidence_threshold_high", high)
    update_config("confidence_threshold_low", low)


def reset_to_defaults():
    """Reset all configuration to defaults."""
    if os.path.exists(CONFIG_OVERRIDE_PATH):
        os.remove(CONFIG_OVERRIDE_PATH)


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
