#!/usr/bin/env python3
"""
Exclusion List Manager for Spotify Tools

Manages lists of tracks and artists that should never be auto-added/followed.
Prevents cleaned-up items from being re-added when running bulk operations.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime

# Import centralized print functions
from print_utils import print_success, print_error, print_warning, print_info

# Import constants
from constants import CONFIG_DIR, EXCLUSIONS_FILE

# Keep for backwards compatibility
EXCLUSIONS_DIR = CONFIG_DIR

def _ensure_exclusions_dir():
    """Ensure the exclusions directory exists."""
    os.makedirs(EXCLUSIONS_DIR, exist_ok=True)

def _load_exclusions():
    """Load exclusions from file."""
    _ensure_exclusions_dir()

    if not os.path.exists(EXCLUSIONS_FILE):
        # Create empty exclusions file
        return {
            "tracks": {},
            "artists": {},
            "metadata": {
                "created": time.time(),
                "last_modified": time.time(),
                "version": "1.0"
            }
        }

    try:
        with open(EXCLUSIONS_FILE, "r") as f:
            data = json.load(f)

        # Validate structure
        if not isinstance(data, dict):
            print_warning("Invalid exclusions file structure, creating new one")
            return _load_exclusions.__wrapped__()  # Start fresh

        # Ensure required keys exist
        if "tracks" not in data:
            data["tracks"] = {}
        if "artists" not in data:
            data["artists"] = {}
        if "metadata" not in data:
            data["metadata"] = {
                "created": time.time(),
                "last_modified": time.time(),
                "version": "1.0"
            }

        return data
    except (json.JSONDecodeError, IOError) as e:
        print_error(f"Error loading exclusions file: {e}")
        print_info("Creating new exclusions file")
        # Backup corrupted file
        if os.path.exists(EXCLUSIONS_FILE):
            backup_file = f"{EXCLUSIONS_FILE}.backup.{int(time.time())}"
            os.rename(EXCLUSIONS_FILE, backup_file)
            print_info(f"Backed up corrupted file to: {backup_file}")
        return _load_exclusions()  # Retry

def _save_exclusions(data):
    """Save exclusions to file."""
    _ensure_exclusions_dir()

    # Update last modified timestamp
    data["metadata"]["last_modified"] = time.time()

    try:
        # Write with pretty formatting for human readability
        with open(EXCLUSIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except (IOError, OSError) as e:
        print_error(f"Error saving exclusions file: {e}")
        return False

def add_exclusion(item_id, item_type="track", reason=None, name=None):
    """
    Add an item to the exclusion list.

    Args:
        item_id: Spotify ID of the track or artist
        item_type: "track" or "artist"
        reason: Optional reason for exclusion
        name: Optional name of the track/artist for reference

    Returns:
        True if added successfully, False otherwise
    """
    if item_type not in ["track", "artist"]:
        print_error(f"Invalid item_type: {item_type}. Must be 'track' or 'artist'")
        return False

    data = _load_exclusions()

    # Determine the correct list
    target_list = "tracks" if item_type == "track" else "artists"

    # Check if already excluded
    if item_id in data[target_list]:
        print_info(f"{item_type.capitalize()} already in exclusion list")
        return True

    # Add to exclusion list
    data[target_list][item_id] = {
        "added": time.time(),
        "added_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": reason or "User excluded",
        "name": name or "Unknown"
    }

    if _save_exclusions(data):
        print_success(f"Added {item_type} to exclusion list: {name or item_id}")
        return True
    return False

def add_bulk_exclusions(item_ids, item_type="track", reason=None):
    """
    Add multiple items to exclusion list at once.

    Args:
        item_ids: List of Spotify IDs or list of dicts with 'id' and optionally 'name'
        item_type: "track" or "artist"
        reason: Optional reason for all exclusions

    Returns:
        Number of items added
    """
    if item_type not in ["track", "artist"]:
        print_error(f"Invalid item_type: {item_type}. Must be 'track' or 'artist'")
        return 0

    data = _load_exclusions()
    target_list = "tracks" if item_type == "track" else "artists"

    added_count = 0
    for item in item_ids:
        # Handle both simple IDs and dict with id/name
        if isinstance(item, dict):
            item_id = item.get('id')
            item_name = item.get('name', 'Unknown')
        else:
            item_id = item
            item_name = 'Unknown'

        if not item_id:
            continue

        # Skip if already excluded
        if item_id in data[target_list]:
            continue

        # Add to exclusion list
        data[target_list][item_id] = {
            "added": time.time(),
            "added_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason or "Bulk exclusion",
            "name": item_name
        }
        added_count += 1

    if _save_exclusions(data):
        print_success(f"Added {added_count} {item_type}(s) to exclusion list")
        return added_count
    return 0

def remove_exclusion(item_id, item_type="track"):
    """
    Remove an item from the exclusion list.

    Args:
        item_id: Spotify ID of the track or artist
        item_type: "track" or "artist"

    Returns:
        True if removed successfully, False otherwise
    """
    if item_type not in ["track", "artist"]:
        print_error(f"Invalid item_type: {item_type}. Must be 'track' or 'artist'")
        return False

    data = _load_exclusions()
    target_list = "tracks" if item_type == "track" else "artists"

    if item_id not in data[target_list]:
        print_warning(f"{item_type.capitalize()} not in exclusion list")
        return False

    # Get name before removing
    item_info = data[target_list][item_id]
    item_name = item_info.get('name', item_id)

    # Remove from list
    del data[target_list][item_id]

    if _save_exclusions(data):
        print_success(f"Removed {item_type} from exclusion list: {item_name}")
        return True
    return False

def is_excluded(item_id, item_type="track"):
    """
    Check if an item is in the exclusion list.

    Args:
        item_id: Spotify ID of the track or artist
        item_type: "track" or "artist"

    Returns:
        True if excluded, False otherwise
    """
    if item_type not in ["track", "artist"]:
        return False

    data = _load_exclusions()
    target_list = "tracks" if item_type == "track" else "artists"

    return item_id in data[target_list]

def get_exclusions(item_type="all"):
    """
    Get all exclusions of a specific type.

    Args:
        item_type: "track", "artist", or "all"

    Returns:
        Dict or list of exclusions
    """
    data = _load_exclusions()

    if item_type == "all":
        return data
    elif item_type == "track":
        return data["tracks"]
    elif item_type == "artist":
        return data["artists"]
    else:
        print_error(f"Invalid item_type: {item_type}")
        return {}

def get_exclusion_count(item_type="all"):
    """
    Get count of exclusions.

    Args:
        item_type: "track", "artist", or "all"

    Returns:
        Count of exclusions
    """
    data = _load_exclusions()

    if item_type == "all":
        return len(data["tracks"]) + len(data["artists"])
    elif item_type == "track":
        return len(data["tracks"])
    elif item_type == "artist":
        return len(data["artists"])
    return 0

def clear_exclusions(item_type="all", confirm=True):
    """
    Clear all exclusions of a specific type.

    Args:
        item_type: "track", "artist", or "all"
        confirm: If True, requires user confirmation

    Returns:
        True if cleared, False if cancelled
    """
    if confirm:
        count = get_exclusion_count(item_type)
        response = input(f"Are you sure you want to clear {count} {item_type} exclusion(s)? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print_info("Clear cancelled")
            return False

    data = _load_exclusions()

    if item_type == "all":
        data["tracks"] = {}
        data["artists"] = {}
    elif item_type == "track":
        data["tracks"] = {}
    elif item_type == "artist":
        data["artists"] = {}
    else:
        print_error(f"Invalid item_type: {item_type}")
        return False

    if _save_exclusions(data):
        print_success(f"Cleared {item_type} exclusions")
        return True
    return False

def export_exclusions(file_path=None, format="json"):
    """
    Export exclusions to a file.

    Args:
        file_path: Path to export file (default: backups/exclusions_TIMESTAMP.json)
        format: Export format ("json" or "csv")

    Returns:
        Path to exported file or None on error
    """
    data = _load_exclusions()

    if file_path is None:
        backup_dir = os.path.join(EXCLUSIONS_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(backup_dir, f"exclusions_{timestamp}.{format}")

    try:
        if format == "json":
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
        elif format == "csv":
            import csv
            with open(file_path, "w", newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Type", "ID", "Name", "Reason", "Date Added"])

                for track_id, info in data["tracks"].items():
                    writer.writerow(["track", track_id, info.get("name", ""),
                                   info.get("reason", ""), info.get("added_date", "")])

                for artist_id, info in data["artists"].items():
                    writer.writerow(["artist", artist_id, info.get("name", ""),
                                   info.get("reason", ""), info.get("added_date", "")])
        else:
            print_error(f"Unsupported format: {format}")
            return None

        print_success(f"Exported exclusions to: {file_path}")
        return file_path
    except (IOError, OSError) as e:
        print_error(f"Error exporting exclusions: {e}")
        return None

def show_exclusion_stats():
    """Display statistics about current exclusions."""
    data = _load_exclusions()

    track_count = len(data["tracks"])
    artist_count = len(data["artists"])
    total_count = track_count + artist_count

    print_info(f"\n{'='*50}")
    print_info("Exclusion List Statistics")
    print_info(f"{'='*50}")
    print_info(f"Total exclusions: {total_count}")
    print_info(f"  Tracks: {track_count}")
    print_info(f"  Artists: {artist_count}")

    metadata = data.get("metadata", {})
    if "created" in metadata:
        created_date = datetime.fromtimestamp(metadata["created"]).strftime("%Y-%m-%d %H:%M:%S")
        print_info(f"Created: {created_date}")
    if "last_modified" in metadata:
        modified_date = datetime.fromtimestamp(metadata["last_modified"]).strftime("%Y-%m-%d %H:%M:%S")
        print_info(f"Last modified: {modified_date}")
    print_info(f"{'='*50}\n")

if __name__ == "__main__":
    # Simple CLI for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python exclusion_manager.py [stats|add|remove|list|clear|export]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "stats":
        show_exclusion_stats()
    elif command == "list":
        item_type = sys.argv[2] if len(sys.argv) > 2 else "all"
        exclusions = get_exclusions(item_type)
        print(json.dumps(exclusions, indent=2))
    elif command == "export":
        format_type = sys.argv[2] if len(sys.argv) > 2 else "json"
        export_exclusions(format=format_type)
    elif command == "clear":
        item_type = sys.argv[2] if len(sys.argv) > 2 else "all"
        clear_exclusions(item_type)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
