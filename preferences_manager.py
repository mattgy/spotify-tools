#!/usr/bin/env python3
"""
Preferences Manager for Spotify Tools

Manages user preferences and settings for automated operations.
Provides defaults and allows customization of behavior.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import json
import time
from pathlib import Path

# Import centralized print functions
from print_utils import print_success, print_error, print_warning, print_info

# Import constants
from constants import CONFIG_DIR, PREFERENCES_FILE

# Keep for backwards compatibility
PREFERENCES_DIR = CONFIG_DIR

# Default preferences
DEFAULT_PREFERENCES = {
    "auto_like_behavior": "conservative",  # conservative, moderate, aggressive
    "filters": {
        "skip_unplayed": True,
        "skip_unfollowed_artists": True,
        "minimum_play_count": 1,
        "respect_exclusions": True,
        "skip_podcasts": True,
        "skip_unavailable": True
    },
    "cleanup": {
        "default_mode": "moderate",  # conservative, moderate, aggressive
        "always_confirm": True,
        "create_backup": True,
        "dry_run_first": False
    },
    "ui": {
        "show_progress_bars": True,
        "verbose_output": False,
        "color_output": True
    },
    "cache": {
        "auto_clear_on_errors": False,
        "max_age_days": 7,
        "duration_hours": 24  # Global cache duration: 24, 6, 1, or 0 (no cache)
    },
    "ai": {
        "enable_ai_boost": False,  # Enable AI assistance for medium-confidence matches
        "ai_service": "gemini",  # gemini, claude, gpt4, perplexity, openai
        "ai_confidence_threshold": 70,  # Minimum confidence before using AI
        "ai_batch_limit": 50,  # Maximum AI requests per batch
        "ai_auto_threshold": 85,  # Auto-accept threshold for AI-boosted matches
        "ai_only_for_no_match": False  # Only use AI when regular search finds nothing
    },
    "playlist_converter": {
        "confidence_threshold": 70,  # Manual review threshold
        "auto_threshold": 85,  # Auto-accept threshold
        "min_score": 50,  # Minimum score to show recommendations
        "duplicate_handling": "ask",  # ask, remove, keep
        "batch_mode": False,  # Default to manual review mode
        "use_ai_boost": False  # Enable AI boost by default
    },
    "metadata": {
        "created": time.time(),
        "last_modified": time.time(),
        "version": "1.0"
    }
}

def _ensure_preferences_dir():
    """Ensure the preferences directory exists."""
    os.makedirs(PREFERENCES_DIR, exist_ok=True)

def _load_preferences():
    """Load preferences from file, creating defaults if needed."""
    _ensure_preferences_dir()

    if not os.path.exists(PREFERENCES_FILE):
        # Create default preferences
        _save_preferences(DEFAULT_PREFERENCES.copy())
        return DEFAULT_PREFERENCES.copy()

    try:
        with open(PREFERENCES_FILE, "r") as f:
            data = json.load(f)

        # Merge with defaults to ensure all keys exist
        merged = DEFAULT_PREFERENCES.copy()
        _deep_merge(merged, data)

        return merged
    except (json.JSONDecodeError, IOError) as e:
        print_error(f"Error loading preferences file: {e}")
        print_info("Using default preferences")
        return DEFAULT_PREFERENCES.copy()

def _deep_merge(base, updates):
    """Recursively merge updates into base dict."""
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value

def _save_preferences(data):
    """Save preferences to file."""
    _ensure_preferences_dir()

    # Update last modified timestamp
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["last_modified"] = time.time()

    try:
        with open(PREFERENCES_FILE, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except (IOError, OSError) as e:
        print_error(f"Error saving preferences file: {e}")
        return False

def get_preference(key_path, default=None):
    """
    Get a preference value by key path.

    Args:
        key_path: Dot-separated path to preference (e.g., "filters.skip_unplayed")
        default: Default value if not found

    Returns:
        Preference value or default
    """
    prefs = _load_preferences()

    # Navigate nested dict
    keys = key_path.split(".")
    value = prefs
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value

def set_preference(key_path, value):
    """
    Set a preference value by key path.

    Args:
        key_path: Dot-separated path to preference (e.g., "filters.skip_unplayed")
        value: Value to set

    Returns:
        True if saved successfully
    """
    prefs = _load_preferences()

    # Navigate nested dict and set value
    keys = key_path.split(".")
    current = prefs
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    current[keys[-1]] = value

    if _save_preferences(prefs):
        print_success(f"Updated preference: {key_path} = {value}")
        return True
    return False

def get_all_preferences():
    """Get all preferences as a dict."""
    return _load_preferences()

def reset_preferences():
    """Reset all preferences to defaults."""
    if _save_preferences(DEFAULT_PREFERENCES.copy()):
        print_success("Reset all preferences to defaults")
        return True
    return False

def get_auto_like_mode():
    """Get the current auto-like behavior mode."""
    return get_preference("auto_like_behavior", "conservative")

def should_skip_unplayed():
    """Check if unplayed tracks should be skipped."""
    return get_preference("filters.skip_unplayed", True)

def should_skip_unfollowed_artists():
    """Check if tracks from unfollowed artists should be skipped."""
    return get_preference("filters.skip_unfollowed_artists", True)

def should_respect_exclusions():
    """Check if exclusion list should be respected."""
    return get_preference("filters.respect_exclusions", True)

def get_minimum_play_count():
    """Get minimum play count filter."""
    return get_preference("filters.minimum_play_count", 1)

def get_cleanup_mode():
    """Get the default cleanup mode."""
    return get_preference("cleanup.default_mode", "moderate")

def should_always_confirm():
    """Check if operations should always ask for confirmation."""
    return get_preference("cleanup.always_confirm", True)

def should_create_backup():
    """Check if backups should be created before destructive operations."""
    return get_preference("cleanup.create_backup", True)

def get_cache_duration_hours():
    """Get the global cache duration in hours."""
    return get_preference("cache.duration_hours", 24)

def get_cache_duration_seconds():
    """Get the global cache duration in seconds."""
    hours = get_cache_duration_hours()
    if hours == 0:
        return None  # No caching
    return hours * 60 * 60

def set_cache_duration(hours):
    """
    Set the global cache duration.

    Args:
        hours: Cache duration in hours (24, 6, 1, or 0 for no cache)

    Returns:
        True if saved successfully
    """
    valid_values = [0, 1, 6, 24]
    if hours not in valid_values:
        print_error(f"Invalid cache duration. Must be one of: {valid_values}")
        return False

    return set_preference("cache.duration_hours", hours)

def show_preferences():
    """Display current preferences in a readable format."""
    prefs = _load_preferences()

    print_info("\n" + "="*50)
    print_info("Current Preferences")
    print_info("="*50)

    print_info("\nAuto-Like Behavior:")
    print_info(f"  Mode: {prefs.get('auto_like_behavior', 'conservative')}")

    print_info("\nFilters:")
    filters = prefs.get('filters', {})
    print_info(f"  Skip unplayed tracks: {filters.get('skip_unplayed', True)}")
    print_info(f"  Skip unfollowed artists: {filters.get('skip_unfollowed_artists', True)}")
    print_info(f"  Minimum play count: {filters.get('minimum_play_count', 1)}")
    print_info(f"  Respect exclusions: {filters.get('respect_exclusions', True)}")
    print_info(f"  Skip podcasts: {filters.get('skip_podcasts', True)}")
    print_info(f"  Skip unavailable: {filters.get('skip_unavailable', True)}")

    print_info("\nCleanup:")
    cleanup = prefs.get('cleanup', {})
    print_info(f"  Default mode: {cleanup.get('default_mode', 'moderate')}")
    print_info(f"  Always confirm: {cleanup.get('always_confirm', True)}")
    print_info(f"  Create backup: {cleanup.get('create_backup', True)}")
    print_info(f"  Dry run first: {cleanup.get('dry_run_first', False)}")

    print_info("\nUI:")
    ui = prefs.get('ui', {})
    print_info(f"  Show progress bars: {ui.get('show_progress_bars', True)}")
    print_info(f"  Verbose output: {ui.get('verbose_output', False)}")
    print_info(f"  Color output: {ui.get('color_output', True)}")

    print_info("\nCache:")
    cache = prefs.get('cache', {})
    duration_hours = cache.get('duration_hours', 24)
    duration_label = "Disabled (fetch every time)" if duration_hours == 0 else f"{duration_hours} hour(s)"
    print_info(f"  Global cache duration: {duration_label}")
    print_info(f"  Auto-clear on errors: {cache.get('auto_clear_on_errors', False)}")

    print_info("\n" + "="*50 + "\n")

def configure_cache_duration():
    """
    Interactive cache duration configuration.

    Returns:
        True if changed successfully, False otherwise
    """
    print_info("\n" + "="*50)
    print_info("Cache Duration Configuration")
    print_info("="*50)

    current_hours = get_cache_duration_hours()
    current_label = "Disabled (fetch every time)" if current_hours == 0 else f"{current_hours} hour(s)"

    print_info(f"\nCurrent cache duration: {current_label}")
    print_info("\nCache determines how long data is reused before fetching fresh data from Spotify.")
    print_info("This applies to: playlists, liked songs, followed artists, recently played, etc.")

    print_info("\nAvailable options:")
    print_info("  1. 24 hours (default, recommended)")
    print_info("  2. 6 hours")
    print_info("  3. 1 hour")
    print_info("  4. Disabled (always fetch fresh data, slower)")
    print_info("  5. Cancel")

    choice = input("\nSelect cache duration (1-5): ").strip()

    duration_map = {
        "1": 24,
        "2": 6,
        "3": 1,
        "4": 0
    }

    if choice == "5":
        print_info("Cancelled")
        return False

    if choice not in duration_map:
        print_warning("Invalid choice")
        return False

    new_duration = duration_map[choice]

    if set_cache_duration(new_duration):
        new_label = "Disabled" if new_duration == 0 else f"{new_duration} hour(s)"
        print_success(f"\nCache duration set to: {new_label}")

        # Optionally clear existing cache
        clear = input("\nClear existing cache to apply immediately? (y/n): ").strip().lower()
        if clear == 'y':
            from cache_utils import clear_cache
            clear_cache()
            print_success("Cache cleared")

        return True

    return False

def configure_interactive():
    """Interactive configuration wizard."""
    print_info("\n" + "="*50)
    print_info("Preferences Configuration Wizard")
    print_info("="*50)

    prefs = _load_preferences()

    # Auto-like behavior
    print_info("\nAuto-Like Behavior:")
    print_info("  1. Conservative - Skip unplayed songs and unfollowed artists")
    print_info("  2. Moderate - Include songs with 1+ plays")
    print_info("  3. Aggressive - Add all songs from playlists")

    choice = input(f"Select mode (1-3) [current: {prefs['auto_like_behavior']}]: ").strip()
    if choice == "1":
        prefs["auto_like_behavior"] = "conservative"
    elif choice == "2":
        prefs["auto_like_behavior"] = "moderate"
    elif choice == "3":
        prefs["auto_like_behavior"] = "aggressive"

    # Cleanup mode
    print_info("\nDefault Cleanup Mode:")
    print_info("  1. Conservative - Only remove unavailable tracks")
    print_info("  2. Moderate - Remove unplayed + unavailable")
    print_info("  3. Aggressive - Remove all rarely played songs")

    choice = input(f"Select mode (1-3) [current: {prefs['cleanup']['default_mode']}]: ").strip()
    if choice == "1":
        prefs["cleanup"]["default_mode"] = "conservative"
    elif choice == "2":
        prefs["cleanup"]["default_mode"] = "moderate"
    elif choice == "3":
        prefs["cleanup"]["default_mode"] = "aggressive"

    # Confirmation
    confirm = input("\nAlways ask for confirmation before changes? (y/n) [y]: ").strip().lower()
    prefs["cleanup"]["always_confirm"] = confirm != "n"

    # Backup
    backup = input("Create backups before destructive operations? (y/n) [y]: ").strip().lower()
    prefs["cleanup"]["create_backup"] = backup != "n"

    if _save_preferences(prefs):
        print_success("\nPreferences saved successfully!")
        show_preferences()
        return True
    return False

if __name__ == "__main__":
    # Simple CLI for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python preferences_manager.py [show|configure|reset|get|set]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "show":
        show_preferences()
    elif command == "configure":
        configure_interactive()
    elif command == "reset":
        reset_preferences()
    elif command == "get" and len(sys.argv) > 2:
        key = sys.argv[2]
        value = get_preference(key)
        print(f"{key} = {value}")
    elif command == "set" and len(sys.argv) > 3:
        key = sys.argv[2]
        value = sys.argv[3]
        # Try to parse as JSON value
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass  # Use as string
        set_preference(key, value)
    else:
        print(f"Unknown command or missing arguments")
        sys.exit(1)
