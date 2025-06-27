#!/usr/bin/env python3
"""
Utility functions for managing cache files.
"""

import os
import glob
import json
import time
from pathlib import Path
import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform color support
colorama.init(autoreset=True)

# Define cache directory
CACHE_DIR = os.path.join(str(Path.home()), ".spotify-tools", "cache")

def print_success(text):
    """Print a success message."""
    print(f"{Fore.GREEN}{text}")

def print_error(text):
    """Print an error message."""
    print(f"{Fore.RED}{text}")

def print_warning(text):
    """Print a warning message."""
    print(f"{Fore.YELLOW}{text}")

def print_info(text):
    """Print an info message."""
    print(f"{Fore.BLUE}{text}")

def save_to_cache(data, cache_key, force_expire=False):
    """Save data to cache."""
    # Create cache directory if it doesn't exist
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # Generate cache file path
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.cache")
    
    if force_expire:
        # Delete the cache file if it exists
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
                return True
            except Exception as e:
                print_warning(f"Error clearing cache {cache_key}: {e}")
                return False
        return True
    
    try:
        # Create cache data structure
        cache_data = {
            "timestamp": time.time(),
            "data": data
        }
        
        # Write to file
        with open(cache_file, "w") as f:
            json.dump(cache_data, f)
        
        return True
    except Exception as e:
        print_warning(f"Error saving to cache {cache_key}: {e}")
        return False

def load_from_cache(cache_key, expiration=None):
    """Load data from cache if it exists and is not expired."""
    # Generate cache file path
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.cache")
    
    # Check if cache file exists
    if not os.path.exists(cache_file):
        return None
    
    try:
        # Read from file
        with open(cache_file, "r") as f:
            cache_data = json.load(f)
        
        # Check if cache is expired
        if expiration is not None:
            timestamp = cache_data.get("timestamp", 0)
            current_time = time.time()
            
            if current_time - timestamp > expiration:
                # Cache is expired
                return None
        
        # Return data
        return cache_data.get("data")
    except Exception as e:
        print_warning(f"Error loading from cache {cache_key}: {e}")
        return None

def list_caches():
    """List all cache files with their metadata."""
    # Create cache directory if it doesn't exist
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # Find all cache files
    cache_files = glob.glob(os.path.join(CACHE_DIR, "*.cache"))
    
    caches = []
    for cache_file in cache_files:
        try:
            # Get file stats
            stats = os.stat(cache_file)
            
            # Extract cache name from filename
            cache_name = os.path.basename(cache_file).replace(".cache", "")
            
            # Add to list
            caches.append({
                "name": cache_name,
                "path": cache_file,
                "size": stats.st_size,
                "mtime": stats.st_mtime,
                "ctime": stats.st_ctime
            })
        except Exception as e:
            print_warning(f"Error processing cache file {cache_file}: {e}")
    
    return caches

def clear_cache(cache_name=None):
    """Clear a specific cache or all caches."""
    if cache_name:
        # Clear specific cache
        cache_file = os.path.join(CACHE_DIR, f"{cache_name}.cache")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
                print_success(f"Cleared cache: {cache_name}")
                return True
            except Exception as e:
                print_error(f"Error clearing cache {cache_name}: {e}")
                return False
        else:
            print_warning(f"Cache not found: {cache_name}")
            return False
    else:
        # Clear all caches
        cache_files = glob.glob(os.path.join(CACHE_DIR, "*.cache"))
        cleared = 0
        
        for cache_file in cache_files:
            try:
                os.remove(cache_file)
                cleared += 1
            except Exception as e:
                print_error(f"Error clearing cache {cache_file}: {e}")
        
        print_success(f"Cleared {cleared} cache files")
        return cleared > 0

def get_cache_info():
    """Get information about all caches."""
    caches = list_caches()
    
    if not caches:
        return {
            "count": 0,
            "total_size": 0,
            "oldest": None,
            "newest": None
        }
    
    # Calculate total size
    total_size = sum(cache["size"] for cache in caches)
    
    # Find oldest and newest
    oldest = min(caches, key=lambda x: x["mtime"])
    newest = max(caches, key=lambda x: x["mtime"])
    
    return {
        "count": len(caches),
        "total_size": total_size,
        "oldest": {
            "name": oldest["name"],
            "mtime": oldest["mtime"]
        },
        "newest": {
            "name": newest["name"],
            "mtime": newest["mtime"]
        }
    }

if __name__ == "__main__":
    # If run directly, show cache info
    info = get_cache_info()
    print_info(f"Cache Information:")
    print(f"  Total cache files: {info['count']}")
    print(f"  Total size: {info['total_size'] / 1024:.1f} KB")
    
    if info['oldest']:
        print(f"  Oldest cache: {info['oldest']['name']} ({time.ctime(info['oldest']['mtime'])})")
    
    if info['newest']:
        print(f"  Newest cache: {info['newest']['name']} ({time.ctime(info['newest']['mtime'])})")
