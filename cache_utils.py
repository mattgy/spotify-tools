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

# Import print functions from spotify_utils
from spotify_utils import print_success, print_error, print_warning, print_info

def sanitize_cache_key(cache_key):
    """Sanitize cache key to be safe for filesystem."""
    import re
    # Replace problematic characters with underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', cache_key)
    # Replace multiple underscores with single underscore
    sanitized = re.sub(r'_+', '_', sanitized)
    # Limit length to prevent filesystem issues
    if len(sanitized) > 200:
        # Keep first 100 and last 100 chars with hash in middle
        import hashlib
        middle_hash = hashlib.md5(sanitized.encode()).hexdigest()[:8]
        sanitized = sanitized[:100] + '_' + middle_hash + '_' + sanitized[-100:]
    return sanitized

def save_to_cache(data, cache_key, force_expire=False):
    """Save data to cache."""
    # Create cache directory if it doesn't exist
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # Sanitize cache key for filesystem safety
    safe_cache_key = sanitize_cache_key(cache_key)
    
    # Generate cache file path
    cache_file = os.path.join(CACHE_DIR, f"{safe_cache_key}.cache")
    
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
    # Sanitize cache key for filesystem safety
    safe_cache_key = sanitize_cache_key(cache_key)
    
    # Generate cache file path
    cache_file = os.path.join(CACHE_DIR, f"{safe_cache_key}.cache")
    
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

def clean_deprecated_caches():
    """Clean up cache files that use deprecated naming conventions."""
    caches = list_caches()
    
    # Define deprecated cache patterns that should be cleaned up
    deprecated_patterns = [
        # Old user-specific cache keys - now we use generic keys
        'user_playlists_',  # Should be just 'user_playlists'
        'saved_tracks',     # Should be 'liked_songs'
        'playlist_tracks',  # Should be 'playlist_tracks_<id>' for specific playlists
        'followed_artists_genres',
        'followed_artists_diversity',
        'followed_artists_backup',
        'followed_artists_for_autofollow',
        'user_playlists_analytics',
        'user_playlists_backup', 
        'liked_songs_timeline',
        'liked_songs_backup',
        'liked_songs_for_skip_analysis',
        'all_liked_songs',
        'all_user_playlists',
        'recently_played_extended',
        'top_artists',
        'recently_played',
        'comprehensive_listening_profile',
        # Additional old patterns that might exist
        'artist_info_',  # Old pattern, now using better keys
        'track_info_',   # Old pattern
        'album_info_',   # Old pattern
        'user_data_',    # Old generic pattern
        'spotify_data_', # Old generic pattern
        'api_response_', # Old generic pattern
        'cached_',       # Old generic pattern
        'temp_',         # Temporary files that weren't cleaned
        'test_',         # Test files that might have been left behind
        # Last.fm and MusicBrainz old patterns
        'lastfm_',       # Should be standardized with 'lastfm_'
        'musicbrainz_',  # Should be standardized with 'mb_'
        'artist_search_', # Old search pattern
        'similar_artists_search_', # Old search pattern
    ]
    
    cleaned_count = 0
    total_size_cleaned = 0
    
    for cache in caches:
        cache_name = cache['name']
        should_clean = False
        
        # Check if this cache matches any deprecated pattern
        for pattern in deprecated_patterns:
            if cache_name == pattern or cache_name.startswith(pattern):
                should_clean = True
                break
        
        if should_clean:
            try:
                os.remove(cache['path'])
                cleaned_count += 1
                total_size_cleaned += cache['size']
                print_info(f"Removed deprecated cache: {cache_name}")
            except Exception as e:
                print_warning(f"Error removing cache {cache_name}: {e}")
    
    if cleaned_count > 0:
        print_success(f"Cleaned up {cleaned_count} deprecated cache files ({total_size_cleaned / 1024:.1f} KB)")
        return True
    else:
        print_info("No deprecated cache files found")
        return False

def clean_stale_caches(max_age_days=30):
    """
    Clean up cache files that are older than specified age.
    
    Args:
        max_age_days: Maximum age in days before a cache is considered stale
    """
    import time
    
    caches = list_caches()
    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 60 * 60
    
    cleaned_count = 0
    total_size_cleaned = 0
    
    for cache in caches:
        cache_age = current_time - cache['mtime']
        
        if cache_age > max_age_seconds:
            try:
                os.remove(cache['path'])
                cleaned_count += 1
                total_size_cleaned += cache['size']
                age_days = cache_age / (24 * 60 * 60)
                print_info(f"Removed stale cache: {cache['name']} ({age_days:.1f} days old)")
            except Exception as e:
                print_warning(f"Error removing stale cache {cache['name']}: {e}")
    
    if cleaned_count > 0:
        print_success(f"Cleaned up {cleaned_count} stale cache files ({total_size_cleaned / 1024:.1f} KB)")
        return True
    else:
        print_info(f"No stale cache files older than {max_age_days} days found")
        return False

def optimize_cache_storage():
    """
    Optimize cache storage by cleaning deprecated and stale caches.
    This is a comprehensive cleanup function.
    """
    from spotify_utils import print_header
    print_header("Cache Storage Optimization")
    
    total_cleaned = False
    
    # Clean deprecated caches first
    print_info("🧹 Cleaning deprecated cache patterns...")
    deprecated_cleaned = clean_deprecated_caches()
    
    # Clean stale caches (older than 30 days)
    print_info("⏰ Cleaning stale caches...")
    stale_cleaned = clean_stale_caches(30)
    
    total_cleaned = deprecated_cleaned or stale_cleaned
    
    # Show final cache status
    info = get_cache_info()
    print_info(f"✅ Cache optimization complete")
    print_info(f"📊 Remaining: {info['count']} files, {info['total_size'] / 1024:.1f} KB")
    
    if info['count'] == 0:
        print_success("🎉 Cache directory is now empty!")
    elif info['total_size'] / 1024 < 100:  # Less than 100KB
        print_success("✨ Cache storage is now optimized!")
    else:
        print_info(f"💡 Consider running manual cache cleanup if size exceeds your preferences")
    
    return total_cleaned

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
