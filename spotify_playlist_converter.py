#!/usr/bin/env python3
"""
Spotify Playlist Converter

This script recursively searches for playlist files (like M3U) in a specified directory
and its subdirectories, then converts them to Spotify playlists.

Features:
- Recursively scans directories for playlist files
- Supports M3U and other common playlist formats
- Uses fuzzy matching for song identification
- Confirms low-confidence matches with the user
- Updates existing Spotify playlists with missing songs
- Handles authentication with Spotify API
- Caches search results to avoid redundant API calls
"""

import os
import sys
import re
import glob
import argparse
from pathlib import Path
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from rapidfuzz import fuzz, process
import time
import logging
import json
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
from spotify_utils import optimized_track_search_strategies, consolidated_track_score
import traceback
from datetime import datetime, timedelta
import colorama
from colorama import Fore, Style
import unicodedata
from collections import defaultdict
import hashlib
import concurrent.futures
import threading
from typing import List, Dict, Tuple, Optional, Set

# Initialize colorama for cross-platform color support
colorama.init(autoreset=True)

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from credentials_manager import get_spotify_credentials, get_ai_credentials
from cache_utils import save_to_cache, load_from_cache
from constants import CACHE_EXPIRATION, CONFIDENCE_THRESHOLDS, BATCH_SIZES

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global variables for API optimization
_user_playlists_cache = None
_user_playlists_cache_time = 0
_rate_limit_delay = 0.1  # Base delay between API calls
_last_api_call_time = 0

# Constants
CONFIDENCE_THRESHOLD = 80  # Default minimum confidence score for automatic matching
# Updated scopes to ensure all playlist operations are covered
SCOPE = "playlist-read-private playlist-modify-private playlist-modify-public user-library-read"
SUPPORTED_EXTENSIONS = ['.m3u', '.m3u8', '.pls']

# Common variations mapping for normalization
COMMON_VARIATIONS = {
    'feat.': 'featuring',
    'ft.': 'featuring',
    'feat': 'featuring',
    'ft': 'featuring',
    '&': 'and',
    'vs.': 'versus',
    'vs': 'versus',
    'pt.': 'part',
    'pt': 'part',
    'vol.': 'volume',
    'vol': 'volume',
    'no.': 'number',
    'no': 'number'
}

# Global configuration for duplicate handling
DUPLICATE_CONFIG = {
    'auto_remove': True,
    'keep_all': False
}

# Track number patterns to remove
TRACK_NUMBER_PATTERNS = [
    r'^\d+[\s\-\.\)]+',  # "01 ", "01-", "01.", "01)"
    r'^\[\d+\]\s*',       # "[01] "
    r'^\(\d+\)\s*',       # "(01) "
    r'^Track\s*\d+[\s\-:]+',  # "Track 01 - "
    r'^\d+\.\s*-\s*',     # "01. - "
]

# Additional filename patterns to clean (YouTube, quality tags, disc numbers, years)
FILENAME_CLEANUP_PATTERNS = [
    # YouTube video indicators
    r'\s*[\(\[](?:Official\s+)?(?:Music\s+)?Video[\)\]]\s*',  # [Official Music Video], (Video), etc.
    r'\s*[\(\[](?:Official\s+)?(?:Audio|Lyric(?:s)?|HD)[\)\]]\s*',  # [Official Audio], [Lyrics], [HD]
    r'\s*[\(\[](?:Music\s+)?Video\s+Official[\)\]]\s*',  # [Music Video Official]
    r'\s*[\(\[]Visuali[sz]er[\)\]]\s*',  # [Visualizer]

    # Quality tags
    r'\s*[\(\[](?:\d+)?kbps[\)\]]\s*',  # [320kbps], [kbps]
    r'\s*[\(\[](?:FLAC|WAV|MP3|M4A|AAC|ALAC)[\)\]]\s*',  # [FLAC], [MP3], etc.
    r'\s*[\(\[](?:HQ|HD|High\s+Quality|Lossless)[\)\]]\s*',  # [HQ], [High Quality]
    r'\s*[\(\[](?:\d+bit|\d+kHz)[\)\]]\s*',  # [24bit], [44.1kHz]

    # Disc/CD numbers (at start or in middle)
    r'^\s*(?:CD|Disc|Disk)\s*\d+[-\s]+\d+[-\s]+',  # "CD1-01 ", "Disc 1-01 "
    r'\s*[-\s](?:CD|Disc|Disk)\s*\d+\s*$',  # " - CD1", " - Disc 1"
    r'^\s*\d+[-\.]\d+\s+',  # "01-01 ", "1.01 " (disc-track format)

    # Year patterns (but be careful not to remove artist names like "1975")
    r'\s*[\(\[]\d{4}[\)\]]\s*$',  # (2023), [2023] at end only

    # Common download/streaming tags
    r'\s*[\(\[](?:Free\s+)?Download[\)\]]\s*',  # [Download], [Free Download]
    r'\s*[\(\[]Full\s+(?:Album|Song|Track)[\)\]]\s*',  # [Full Album]
    r'\s*[\(\[](?:No\s+)?Copyright[\)\]]\s*',  # [Copyright], [No Copyright]
    r'\s*[\(\[]NCS\s+Release[\)\]]\s*',  # [NCS Release] (No Copyright Sounds)

    # Explicit/Clean tags
    r'\s*[\(\[]Explicit[\)\]]\s*',  # [Explicit]
    r'\s*[\(\[]Clean[\)\]]\s*',  # [Clean]
]

def create_decision_cache_key(track_info, match_info):
    """Create a stable, collision-free cache key for user decisions."""
    import hashlib

    # Use stable identifiers, not file paths (which can change)
    track_artist = track_info.get('artist', '').lower().strip()
    track_title = track_info.get('title', '').lower().strip()
    match_id = match_info.get('id', '') if match_info else ''

    # Create deterministic key using MD5 (stable across sessions, no collisions)
    key_parts = f"{track_artist}|{track_title}|{match_id}"
    cache_hash = hashlib.md5(key_parts.encode()).hexdigest()

    # Include version for cache invalidation if format changes
    version = "v1"
    return f"user_decision_{version}_{cache_hash}"

def create_track_only_cache_key(track_info):
    """Create a cache key for track-only lookups (no match_id)."""
    import hashlib

    track_artist = track_info.get('artist', '').lower().strip()
    track_title = track_info.get('title', '').lower().strip()

    # Create deterministic key using MD5
    key_parts = f"{track_artist}|{track_title}"
    cache_hash = hashlib.md5(key_parts.encode()).hexdigest()

    version = "v1"
    return f"track_decision_{version}_{cache_hash}"

def save_user_decision(track_info, match_info, decision, manual_search_used=False):
    """Save a user decision to cache for learning."""
    cache_key = create_decision_cache_key(track_info, match_info)
    decision_data = {
        'decision': decision,
        'track_info': {
            'path': track_info.get('path', ''),
            'artist': track_info.get('artist', ''),
            'title': track_info.get('title', ''),
            'album': track_info.get('album', '')
        },
        'match_info': {
            'id': match_info.get('id', '') if match_info else '',
            'name': match_info.get('name', '') if match_info else '',
            'artists': match_info.get('artists', []) if match_info else [],
            'album': match_info.get('album', '') if match_info else '',
            'score': match_info.get('score', 0) if match_info else 0
        },
        'manual_search_used': manual_search_used,
        'timestamp': time.time()
    }
    save_to_cache(decision_data, cache_key, force_expire=False)

    # Also save track-only decision for fast lookups without match_id
    # This prevents expensive linear scans through all cache files
    track_only_key = create_track_only_cache_key(track_info)
    save_to_cache(decision_data, track_only_key, force_expire=False)

    # Also save to learning cache for pattern analysis
    if decision == 'y' and match_info:
        save_to_learning_cache(track_info, match_info, manual_search_used)

def save_to_learning_cache(track_info, match_info, manual_search_used=False):
    """Save successful matches to learning cache for pattern recognition."""
    learning_key = "playlist_converter_learning_data"
    
    # Load existing learning data
    learning_data = load_from_cache(learning_key, 365 * 24 * 60 * 60) or {'matches': [], 'patterns': {}}
    
    # Add new match
    match_entry = {
        'original_artist': track_info.get('artist', ''),
        'original_title': track_info.get('title', ''),
        'matched_artists': match_info.get('artists', []),
        'matched_title': match_info.get('name', ''),
        'score': match_info.get('score', 0),
        'manual_search': manual_search_used,
        'timestamp': time.time()
    }
    
    learning_data['matches'].append(match_entry)
    
    # Keep only last 1000 matches
    if len(learning_data['matches']) > 1000:
        learning_data['matches'] = learning_data['matches'][-1000:]
    
    # Update patterns
    update_learning_patterns(learning_data)
    
    # Save back to cache
    save_to_cache(learning_data, learning_key)

def update_learning_patterns(learning_data):
    """Analyze matches to find common patterns."""
    patterns = learning_data.get('patterns', {})
    
    # Analyze artist name variations
    artist_variations = defaultdict(list)
    for match in learning_data['matches']:
        orig_artist = match['original_artist'].lower()
        matched_artists = [a.lower() for a in match['matched_artists']]
        
        for matched_artist in matched_artists:
            if orig_artist != matched_artist and fuzz.ratio(orig_artist, matched_artist) > 70:
                artist_variations[orig_artist].append(matched_artist)
    
    # Find most common variations
    patterns['artist_variations'] = {}
    for orig, variations in artist_variations.items():
        if variations:
            # Count occurrences
            variation_counts = defaultdict(int)
            for var in variations:
                variation_counts[var] += 1
            
            # Keep most common variation
            most_common = max(variation_counts.items(), key=lambda x: x[1])
            if most_common[1] >= 2:  # At least 2 occurrences
                patterns['artist_variations'][orig] = most_common[0]
    
    learning_data['patterns'] = patterns

def apply_learning_patterns(artist, title):
    """Apply learned patterns to improve matching."""
    learning_key = "playlist_converter_learning_data"
    learning_data = load_from_cache(learning_key, 365 * 24 * 60 * 60)
    
    if not learning_data:
        return artist, title
    
    patterns = learning_data.get('patterns', {})
    artist_variations = patterns.get('artist_variations', {})
    
    # Apply artist variations
    artist_lower = artist.lower() if artist else ""
    if artist_lower in artist_variations:
        logger.debug(f"Applying learned artist variation: {artist} -> {artist_variations[artist_lower]}")
        return artist_variations[artist_lower], title
    
    return artist, title

def get_cached_decision(track_info, match_info=None):
    """Get a previously cached user decision.
    If match_info is None, looks for any cached decision for this track.
    """
    if match_info:
        # Look for specific track/match combination
        cache_key = create_decision_cache_key(track_info, match_info)
        cached_data = load_from_cache(cache_key, 30 * 24 * 60 * 60)  # Cache for 30 days
        if cached_data:
            return cached_data
    else:
        # Use direct track-only key for O(1) lookup instead of linear scan
        track_only_key = create_track_only_cache_key(track_info)
        cached_data = load_from_cache(track_only_key, 30 * 24 * 60 * 60)
        if cached_data:
            return cached_data

    return None

def check_and_use_previous_session():
    """Check if there are previous decisions and ask user if they want to reuse them."""
    from cache_utils import list_caches
    
    # Look for user decision caches
    caches = list_caches()
    decision_caches = [c for c in caches if c['name'].startswith('user_decision_')]
    
    if not decision_caches:
        return False  # No previous decisions to use
    
    # Find most recent decision
    most_recent = max(decision_caches, key=lambda c: c['mtime'])
    age_days = (time.time() - most_recent['mtime']) / (24 * 60 * 60)
    
    print(f"\n{Fore.CYAN}Found previous session with {len(decision_caches)} saved decisions")
    print(f"{Fore.CYAN}Most recent decision was {age_days:.1f} days ago")
    print(f"\n{Fore.YELLOW}Options:")
    print(f"1. Use previous decisions (skip already reviewed tracks)")
    print(f"2. Review all tracks again (ignore previous decisions)")
    print(f"3. Clear previous decisions and start fresh")
    
    choice = input(f"\n{Fore.CYAN}Enter your choice (1-3): ").strip()
    
    if choice == '1':
        print(f"{Fore.GREEN}✅ Using previous decisions")
        return True
    elif choice == '2':
        print(f"{Fore.YELLOW}Ignoring previous decisions for this session")
        return False
    elif choice == '3':
        # Clear decision caches
        from cache_utils import clear_cache
        cleared = 0
        for cache in decision_caches:
            clear_cache(cache['name'])
            cleared += 1
        print(f"{Fore.GREEN}✅ Cleared {cleared} previous decisions")
        return True
    else:
        print(f"{Fore.YELLOW}Invalid choice, using previous decisions")
        return True

def detect_playlist_duplicates(sp, playlist_id):
    """Detect duplicate tracks in a playlist using fast basic comparison."""
    try:
        # Get all tracks in the playlist
        tracks = []
        offset = 0
        limit = 100
        
        while True:
            response = sp.playlist_items(
                playlist_id,
                fields='items(track(id,name,artists(name),duration_ms)),total',
                limit=limit,
                offset=offset
            )
            
            for item in response['items']:
                if item['track'] and item['track']['id']:
                    tracks.append({
                        'id': item['track']['id'],
                        'name': item['track']['name'].lower().strip(),
                        'artists': [a['name'].lower().strip() for a in item['track']['artists']],
                        'duration_ms': item['track'].get('duration_ms', 0),
                        'position': offset + len(tracks)
                    })
            
            if len(response['items']) < limit:
                break
            offset += limit
        
        # Fast duplicate detection using track ID and artist+title combinations
        duplicates = []
        seen_ids = set()
        seen_combinations = set()
        
        for i, track in enumerate(tracks):
            track_id = track['id']
            
            # Create a normalized combination for comparison
            artists_str = ','.join(sorted(track['artists']))
            combination = (track['name'], artists_str)
            
            # Check for exact ID duplicates
            if track_id in seen_ids:
                duplicates.append({
                    'type': 'exact_id',
                    'track': track,
                    'original_position': i
                })
            else:
                seen_ids.add(track_id)
            
            # Check for same song by different artists or slight name variations
            if combination in seen_combinations:
                duplicates.append({
                    'type': 'same_song',
                    'track': track,
                    'original_position': i
                })
            else:
                seen_combinations.add(combination)
        
        return duplicates
        
    except Exception as e:
        logger.error(f"Error detecting duplicates: {e}")
        return []

def apply_rate_limit():
    """Apply rate limiting between API calls with exponential backoff."""
    global _last_api_call_time, _rate_limit_delay
    
    current_time = time.time()
    time_since_last_call = current_time - _last_api_call_time
    
    if time_since_last_call < _rate_limit_delay:
        sleep_time = _rate_limit_delay - time_since_last_call
        time.sleep(sleep_time)
    
    _last_api_call_time = time.time()

def handle_rate_limit_error(e):
    """Handle rate limit errors with exponential backoff."""
    global _rate_limit_delay
    
    if hasattr(e, 'http_status') and e.http_status == 429:
        # Extract retry-after header if available
        retry_after = getattr(e, 'retry_after', None)
        if retry_after:
            wait_time = int(retry_after)
        else:
            wait_time = _rate_limit_delay * 2
        
        logger.warning(f"Rate limit hit. Waiting {wait_time} seconds...")
        time.sleep(wait_time)
        
        # Increase base delay for future calls
        _rate_limit_delay = min(_rate_limit_delay * 1.5, 2.0)  # Max 2 second delay
        return True
    
    return False

def bulk_search_tracks_on_spotify(sp, tracks: List[Dict], max_workers: int = 5) -> Dict[str, Optional[Dict]]:
    """
    Search for multiple tracks on Spotify in parallel using thread pool.
    Returns a dictionary mapping track keys to search results.
    """
    results = {}
    
    def search_single_track(track_data):
        """Helper function to search a single track."""
        track_key = f"{track_data.get('artist', '')}||{track_data.get('title', '')}"
        try:
            result = search_track_on_spotify(sp, track_data['artist'], track_data['title'], track_data.get('album'))
            return (track_key, result)
        except Exception as e:
            logger.error(f"Error searching for track {track_key}: {e}")
            return (track_key, None)
    
    # Use ThreadPoolExecutor for parallel searches
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all search tasks
        future_to_track = {executor.submit(search_single_track, track): track for track in tracks}
        
        # Process completed searches with progress bar
        with create_progress_bar(total=len(tracks), desc="Searching tracks", unit="track") as pbar:
            for future in concurrent.futures.as_completed(future_to_track):
                track_key, result = future.result()
                results[track_key] = result
                
                # Small delay to avoid rate limiting
                time.sleep(0.05)
                update_progress_bar(pbar)
    
    return results

def compute_playlist_hash(tracks: List[Dict]) -> str:
    """Compute a hash of playlist contents for change detection."""
    # Sort tracks by artist and title for consistent hashing
    sorted_tracks = sorted(tracks, key=lambda t: (t.get('artist', ''), t.get('title', '')))
    
    # Create a string representation of the playlist
    playlist_str = ""
    for track in sorted_tracks:
        playlist_str += f"{track.get('artist', '')}|{track.get('title', '')}|{track.get('album', '')}|"
    
    # Return SHA256 hash
    return hashlib.sha256(playlist_str.encode()).hexdigest()

def get_playlist_sync_state(playlist_path: str) -> Optional[Dict]:
    """Get the last sync state for a playlist."""
    cache_key = f"playlist_sync_state_{hashlib.md5(playlist_path.encode()).hexdigest()}"
    return load_from_cache(cache_key, 30 * 24 * 60 * 60)  # Cache for 30 days

def save_playlist_sync_state(playlist_path: str, state: Dict):
    """Save the sync state for a playlist."""
    cache_key = f"playlist_sync_state_{hashlib.md5(playlist_path.encode()).hexdigest()}"
    save_to_cache(state, cache_key)

def playlist_needs_sync(playlist_path: str, tracks: List[Dict]) -> Tuple[bool, Optional[str]]:
    """Check if a playlist needs to be synced based on its content hash."""
    current_hash = compute_playlist_hash(tracks)
    sync_state = get_playlist_sync_state(playlist_path)
    
    if not sync_state:
        return True, current_hash
    
    last_hash = sync_state.get('content_hash')
    if last_hash != current_hash:
        return True, current_hash
    
    # Check if it's been too long since last sync (force sync after 7 days)
    last_sync = sync_state.get('last_sync_time', 0)
    if time.time() - last_sync > 7 * 24 * 60 * 60:
        return True, current_hash
    
    return False, current_hash

def remove_playlist_duplicates(sp, playlist_id, duplicates):
    """Remove duplicate tracks from a playlist."""
    if not duplicates:
        return 0
    
    # Sort duplicates by position (highest first) to maintain correct indices during removal
    duplicates_sorted = sorted(duplicates, key=lambda x: x['original_position'], reverse=True)
    
    removed_count = 0
    for duplicate in duplicates_sorted:
        try:
            # Remove track by position
            sp.playlist_remove_specific_occurrences_of_items(
                playlist_id,
                [{"uri": f"spotify:track:{duplicate['track']['id']}", "positions": [duplicate['original_position']]}]
            )
            removed_count += 1
        except Exception as e:
            logger.error(f"Error removing duplicate at position {duplicate['original_position']}: {e}")
    
    return removed_count

def authenticate_spotify():
    """Authenticate with Spotify API."""
    try:
        # Get credentials from credentials manager
        client_id, client_secret, redirect_uri = get_spotify_credentials()
        
        from spotify_utils import create_spotify_client
        return create_spotify_client([SCOPE], "playlist_converter")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return None

def parse_m3u_playlist(file_path):
    """Parse an M3U playlist file and extract track information."""
    tracks = []
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    # Process extended M3U format
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines and simple comments
        if not line or (line.startswith('#') and not line.startswith('#EXTINF:')):
            i += 1
            continue
        
        # Check if this is an extended info line
        if line.startswith('#EXTINF:'):
            # Extract info from EXTINF line if possible
            extinf_line = line
            
            # Move to the next line which should be the file path
            i += 1
            if i >= len(lines):
                break
                
            file_path_line = lines[i].strip()
            
            # Skip if this is another comment or empty line
            if not file_path_line or file_path_line.startswith('#'):
                i += 1
                continue
            
            # Extract track info from both the EXTINF line and file path
            track_info = extract_track_info_from_extinf_and_path(extinf_line, file_path_line)
            tracks.append(track_info)
        else:
            # Regular M3U format - just a file path
            track_info = extract_track_info_from_path(line)
            tracks.append(track_info)
        
        i += 1
    
    return tracks

def extract_track_info_from_extinf_and_path(extinf_line, file_path):
    """
    Extract track information from both EXTINF line and file path.
    EXTINF format: #EXTINF:duration,Artist - Title
    """
    track_info = {
        'artist': '',
        'album': '',
        'title': '',
        'path': file_path
    }
    
    # First extract info from the file path
    path_info = extract_track_info_from_path(file_path)
    track_info.update(path_info)
    
    # Then try to extract from EXTINF line which might have better info
    try:
        # Format is typically: #EXTINF:duration,Artist - Title
        # or sometimes: #EXTINF:duration,Title
        extinf_parts = extinf_line.split(',', 1)
        if len(extinf_parts) > 1:
            info_part = extinf_parts[1].strip()
            
            # Check if it contains artist - title format
            if ' - ' in info_part:
                artist, title = info_part.split(' - ', 1)
                track_info['artist'] = artist.strip()
                track_info['title'] = title.strip()
            else:
                # If no separator, assume it's just the title
                track_info['title'] = info_part.strip()
    except Exception as e:
        logger.debug(f"Error parsing EXTINF line: {e}")
    
    return track_info

def extract_track_info_from_path(path):
    """
    Extract artist, album, and title information from a file path.
    Handles various common path formats including underscore-separated names,
    Windows paths, and complex track numbering patterns.
    """
    # Default values
    track_info = {
        'artist': '',
        'album': '',
        'title': '',
        'path': path,
        'original_line': path  # Store the original path
    }
    
    # Get just the filename without extension (handle both Unix and Windows paths)
    filename = path.replace('\\', '/').split('/')[-1]  # Get last part after normalizing separators
    filename_no_ext = os.path.splitext(filename)[0]
    
    # Enhanced parsing for various filename formats
    enhanced_filename = filename_no_ext
    
    # Handle directory information first (for cases like "M:\Turntables Electronics\Joshua Idehen\Routes\Joshua Idehen-03-Northern Line.mp3")
    path_parts = path.replace('\\', '/').split('/')  # Normalize path separators
    if len(path_parts) >= 3:
        # Try to extract artist from directory structure
        potential_artist = None
        potential_album = None
        
        # Look for artist in the path (prioritize matches that appear in filename)
        best_match = None
        best_score = 0
        
        for i in range(2, min(5, len(path_parts))):  # Check last 2-4 directory levels
            dir_name = path_parts[-i]
            if dir_name and not re.match(r'^[A-Z]:$', dir_name):  # Skip drive letters
                normalized_dir = dir_name.lower().replace(' ', '').replace('_', '').replace('-', '')
                normalized_filename = filename_no_ext.lower().replace(' ', '').replace('_', '').replace('-', '')
                
                score = 0
                
                # Higher score if filename starts with this directory name
                if normalized_filename.startswith(normalized_dir):
                    score = 100
                # Medium score if directory name appears anywhere in filename
                elif normalized_dir in normalized_filename:
                    score = 50
                # Low score for any directory in path structure
                else:
                    score = 10
                
                # Prefer longer matches (more specific)
                score += len(normalized_dir)
                
                if score > best_score:
                    best_score = score
                    best_match = dir_name
                    potential_album = path_parts[-2] if len(path_parts) >= 2 else None
        
        if best_match:
            potential_artist = best_match
        
        # Store potential matches for later use
        if potential_artist:
            track_info['artist'] = potential_artist
        if potential_album and potential_album != potential_artist:
            track_info['album'] = potential_album
    
    # Enhanced track number removal patterns
    enhanced_track_patterns = [
        r'^(\d+[\s\.\-_]+)',  # Basic: "01 - ", "1. ", "01_"
        r'^(\d+\.?\d*[\s\.\-_]+)',  # Decimal: "1.1 - ", "1.5_"
        r'(?:^|\s)(\d+[\s\.\-_]*-[\s\.\-_]*)',  # "Joshua Idehen-03-Northern Line" -> "Joshua Idehen - Northern Line"
        r'(\s-\s\d+[\s\.\-_]*-\s)',  # " - 03 - " -> " - "
        r'(\d{2,3}[\s\.\-_]+)',  # Track numbers at start: "003 - "
    ]
    
    # Check for underscore-based format first
    if '_-_' in enhanced_filename or '__' in enhanced_filename:
        # Replace double underscores with separators and clean up
        enhanced_filename = enhanced_filename.replace('__', ' - ')
        enhanced_filename = enhanced_filename.replace('_-_', ' - ')
        enhanced_filename = enhanced_filename.replace('_', ' ')
        
        # Handle "various artists" at the beginning
        if enhanced_filename.lower().startswith('various artists - '):
            parts = enhanced_filename[17:].split(' - ', 1)  # Remove "various artists - "
            if len(parts) >= 1:
                if len(parts) == 2:
                    track_info['artist'] = parts[0].strip()
                    track_info['title'] = parts[1].strip()
                else:
                    # If only one part after "various artists", treat it as artist - title
                    artist_title = parts[0].strip()
                    if ' - ' in artist_title:
                        artist, title = artist_title.split(' - ', 1)
                        track_info['artist'] = artist.strip()
                        track_info['title'] = title.strip()
                    else:
                        # Try to split on first space sequence as artist/title boundary
                        words = artist_title.split()
                        if len(words) >= 3:
                            # Assume first 2-3 words are artist, rest is title
                            track_info['artist'] = ' '.join(words[:2])
                            track_info['title'] = ' '.join(words[2:])
                        else:
                            track_info['title'] = artist_title
        else:
            # Regular underscore format without "various artists"
            enhanced_filename = enhanced_filename.replace('_', ' ')
    
    # Handle artist name appearing multiple times in filename (e.g., "Joshua Idehen-03-Northern Line" with Joshua Idehen as artist)
    if track_info['artist'] and track_info['artist'].lower() in enhanced_filename.lower():
        # Remove redundant artist name from filename for cleaner parsing
        artist_pattern = re.escape(track_info['artist'])
        # Remove artist name if it appears at the beginning
        enhanced_filename = re.sub(f'^{artist_pattern}[-_\\s]*', '', enhanced_filename, flags=re.IGNORECASE)
    
    # Apply enhanced track number removal
    for pattern in enhanced_track_patterns:
        enhanced_filename = re.sub(pattern, '', enhanced_filename).strip()
        if enhanced_filename.startswith('- '):
            enhanced_filename = enhanced_filename[2:].strip()
    
    # If we haven't extracted info yet, try enhanced patterns
    if not track_info['title']:  # We might have artist from directory parsing
        # Try enhanced parsing for complex patterns like:
        # "Mark Ronson - Captain's Crate - Pretty Green feat. Santo Gold"
        # "Various - DArcy Xmas 08 - Pretty Green feat. Santo Gold"
        # "Cee-Lo - Closet Freak - The Best of Cee-Lo Green the Soul Machine - Gettin' Grown"
        # "Xplastaz - Maasai Hip Hop - Msimu Kwa Msimu"
        
        test_filename = enhanced_filename
        
        # Smart split that doesn't split on dashes inside parentheses
        # Use a more sophisticated approach to avoid splitting "(Re-Imagined)" type content
        parts = []
        current_part = ""
        paren_depth = 0
        i = 0
        
        while i < len(test_filename):
            char = test_filename[i]
            
            if char == '(':
                paren_depth += 1
                current_part += char
            elif char == ')':
                paren_depth -= 1
                current_part += char
            elif char == '-' and paren_depth == 0:
                # Only split on dashes outside parentheses
                # Look for surrounding whitespace
                if (i > 0 and test_filename[i-1].isspace()) or (i < len(test_filename)-1 and test_filename[i+1].isspace()):
                    parts.append(current_part.strip())
                    current_part = ""
                    # Skip whitespace after dash
                    i += 1
                    while i < len(test_filename) and test_filename[i].isspace():
                        i += 1
                    continue
                else:
                    current_part += char
            else:
                current_part += char
            
            i += 1
        
        if current_part.strip():
            parts.append(current_part.strip())
        
        if len(parts) >= 3:
            # Complex pattern with multiple dashes
            # Examples:
            # "Xplastaz - Maasai Hip Hop - Msimu Kwa Msimu"
            # "Black Spade - To Serve With Love - Black_Spade_5_She_s_The_One" 
            # "EMC - The Show - INCOMPLETE - EMC_Make_It_Better"  
            # "Various - DArcy Xmas 08 - Pretty Green feat. Santo Gold"
            # "25Th Anniversary Hall Of Fame Disc 1 - Papa Was A Rollin' Stone - Gladys Knight & The Pips"
            
            potential_artist = parts[0].strip()
            potential_album = parts[1].strip() 
            potential_title = parts[-1].strip()  # Last part is usually the title
            
            # Check for "Various" artists first - special handling
            if potential_artist.lower() in ['various', 'various artists', 'va']:
                # For "Various - Album - Artist Title" format
                # Try to extract real artist and title from the last part
                if ' - ' in potential_title or ' by ' in potential_title.lower():
                    # Title might contain artist info: "Artist - Title" or "Title by Artist"
                    title_parts = re.split(r' - | by ', potential_title, maxsplit=1, flags=re.IGNORECASE)
                    if len(title_parts) == 2:
                        track_info['artist'] = title_parts[0].strip()
                        track_info['title'] = title_parts[1].strip()
                        track_info['album'] = potential_album
                    else:
                        # Just use the title as-is, Various as artist
                        track_info['artist'] = 'Various Artists'
                        track_info['title'] = potential_title
                        track_info['album'] = potential_album
                else:
                    # Try to guess where artist ends and title begins
                    title_words = potential_title.split()
                    if len(title_words) >= 4:
                        # Look for featuring patterns or common breakpoint words
                        feat_pattern = r'\b(feat\.?|featuring|ft\.?|with)\b'
                        feat_match = re.search(feat_pattern, potential_title, re.IGNORECASE)
                        if feat_match:
                            # Split at featuring
                            before_feat = potential_title[:feat_match.start()].strip()
                            track_info['artist'] = 'Various Artists'
                            track_info['title'] = before_feat if before_feat else potential_title
                        else:
                            # Default: first few words might be artist, rest is title
                            track_info['artist'] = ' '.join(title_words[:2])  # First 2 words as artist guess
                            track_info['title'] = ' '.join(title_words[2:])   # Rest as title
                    else:
                        track_info['artist'] = 'Various Artists'
                        track_info['title'] = potential_title
                    track_info['album'] = potential_album
            
            # Check for compilation patterns (long first part with specific keywords)
            elif (len(parts) == 3 and (
                'anniversary' in potential_artist.lower() or
                'hall of fame' in potential_artist.lower() or 
                'jukebox' in potential_artist.lower() or
                'best of' in potential_artist.lower() or
                'collection' in potential_artist.lower() or
                'compilation' in potential_artist.lower() or
                len(potential_artist.split()) > 4  # Very long first part suggests compilation
            )):
                # This is likely a compilation: "Collection Name - Track Title - Artist Name"
                # So parts[1] is the track title, parts[2] is the artist
                track_info['artist'] = clean_complex_title(potential_title, '')  # parts[2] is artist
                track_info['title'] = potential_album  # parts[1] is actually the title
                track_info['album'] = potential_artist  # parts[0] is the compilation name
            
            else:
                # Regular multi-part pattern: Artist - Album - Title
                # Enhanced cleaning for complex filenames
                potential_artist = normalize_artist_name(potential_artist)
                potential_title = clean_complex_title(potential_title, potential_artist)
                potential_album = filter_album_name(potential_album)
                
                track_info['artist'] = potential_artist
                track_info['title'] = potential_title
                if potential_album:  # Only set album if it passed filtering
                    track_info['album'] = potential_album
                    
        elif len(parts) == 2:
            # Standard Artist - Title pattern
            if not track_info['artist']:
                track_info['artist'] = parts[0].strip()
            track_info['title'] = parts[1].strip()
        else:
            # If no dash separator found, use the whole thing as title
            track_info['title'] = test_filename.strip()
    
    # Clean up the extracted information
    if track_info['artist']:
        track_info['artist'] = ' '.join(track_info['artist'].split())  # Normalize whitespace
    if track_info['title']:
        track_info['title'] = ' '.join(track_info['title'].split())  # Normalize whitespace
    
    # Now try to extract album info from the directory structure
    # Common patterns:
    # 1. /path/to/Artist/Album/01 - Title.mp3
    # 2. /path/to/Artist - Album/01 - Title.mp3
    # 3. /path/to/Music/Genre/Artist/Album/01 - Title.mp3
    # 4. /path/to/Music/Genre/Artist - Album/01 - Title.mp3
    
    path_parts = path.split('/')
    if len(path_parts) >= 3:  # Need at least 3 parts for meaningful extraction
        # Try to find album from the directory containing the file
        dir_name = path_parts[-2]
        
        # Special case: If directory name contains track numbers, it's probably not an album name
        if re.match(r'^(\d+[\s\.\-_]+)', dir_name):
            # This might be a compilation or soundtrack, check the parent directory
            if len(path_parts) >= 4:
                potential_album_dir = path_parts[-3]
                if not re.match(r'^(\d+[\s\.\-_]+)', potential_album_dir):
                    track_info['album'] = clean_metadata_field(potential_album_dir)
        else:
            # Check if the directory name contains the artist name
            if track_info['artist'] and dir_name.startswith(track_info['artist']):
                # Format might be "Artist - Album"
                album_parts = dir_name.split(' - ', 1)
                if len(album_parts) > 1:
                    track_info['album'] = album_parts[1].strip()
                else:
                    # If it's just the artist name, look at parent directory for album
                    if len(path_parts) >= 4:
                        potential_album_dir = path_parts[-3]
                        if not re.match(r'^(\d+[\s\.\-_]+)', potential_album_dir):
                            track_info['album'] = clean_metadata_field(potential_album_dir)
            else:
                # Directory might just be the album name
                # Check if the parent directory might be the artist
                if len(path_parts) >= 4:
                    potential_artist_dir = path_parts[-3]
                    
                    # If we don't have an artist yet, or the directory matches our artist
                    if (not track_info['artist'] or 
                        potential_artist_dir.lower() == track_info['artist'].lower()):
                        track_info['artist'] = potential_artist_dir
                        track_info['album'] = dir_name
                    else:
                        # Just use the directory as the album name
                        track_info['album'] = dir_name
                else:
                    # Just use the directory as the album name
                    track_info['album'] = dir_name
    
    # Special case for paths like "/path/to/Artist - Album/01 - Title.mp3"
    # where we need to split the directory name to get artist and album
    if not track_info['album'] and len(path_parts) >= 2:
        dir_name = path_parts[-2]
        if ' - ' in dir_name:
            dir_parts = dir_name.split(' - ', 1)
            if len(dir_parts) == 2:
                # Only use this if we don't already have an artist or if it matches
                if not track_info['artist'] or dir_parts[0].strip() == track_info['artist']:
                    track_info['artist'] = dir_parts[0].strip()
                    track_info['album'] = dir_parts[1].strip()
    
    # Clean up the extracted information
    # Remove common prefixes/suffixes and clean up whitespace
    if track_info['artist']:
        track_info['artist'] = clean_metadata_field(track_info['artist'])
    
    if track_info['album']:
        track_info['album'] = clean_metadata_field(track_info['album'])
    
    if track_info['title']:
        track_info['title'] = clean_metadata_field(track_info['title'])
    
    return track_info

def clean_metadata_field(text):
    """Clean up metadata fields by removing common prefixes, brackets, etc."""
    # Remove track numbers from the beginning
    text = remove_track_numbers(text)
    
    # Remove common file extensions
    text = re.sub(r'\.mp3$|\.flac$|\.wav$|\.m4a$|\.ogg$|\.wma$|\.aac$|\.opus$', '', text, flags=re.IGNORECASE)
    
    # Remove brackets and their contents if they appear to be technical info
    text = re.sub(r'\([^\)]*(?:kbps|khz|kHz|mp3|flac|wav)[^\)]*\)|\[[^\]]*(?:kbps|khz|kHz|mp3|flac|wav)[^\]]*\]', '', text, flags=re.IGNORECASE)
    
    # Remove CD rip info
    text = re.sub(r'\[?(?:EAC|FLAC|Rip|CDRip|CD\s*Rip)\]?', '', text, flags=re.IGNORECASE)
    
    # Clean up whitespace
    text = ' '.join(text.split())
    
    return text

def parse_pls_playlist(file_path):
    """Parse a PLS playlist file and extract track information."""
    tracks = []
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    title_pattern = re.compile(r'Title\d+=(.+)')
    file_pattern = re.compile(r'File\d+=(.+)')
    
    titles = {}
    files = {}
    
    for line in lines:
        line = line.strip()
        
        title_match = title_pattern.match(line)
        if title_match:
            index = int(re.search(r'Title(\d+)', line).group(1))
            titles[index] = title_match.group(1)
            continue
        
        file_match = file_pattern.match(line)
        if file_match:
            index = int(re.search(r'File(\d+)', line).group(1))
            files[index] = file_match.group(1)
            continue
    
    for index in sorted(files.keys()):
        file_path = files[index]
        
        # Extract track info from the file path
        track_info = extract_track_info_from_path(file_path)
        
        # If we have a title entry, use it to enhance the track info
        if index in titles:
            title_value = titles[index]
            parts = re.split(r' - ', title_value, maxsplit=1)
            
            if len(parts) > 1:
                # If the title entry has artist - title format, use it
                track_info['artist'] = parts[0].strip()
                track_info['title'] = parts[1].strip()
            else:
                # Otherwise just use it as the title
                track_info['title'] = title_value.strip()
        
        tracks.append(track_info)
    
    return tracks

def is_text_playlist_file(file_path):
    """Check if a file contains playlist data in text format (artist - song pairs)."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[:10]  # Check first 10 lines
        
        if len(lines) < 2:
            return False
            
        # Look for patterns like "Artist - Song" or "Artist: Song"
        valid_lines = 0
        for line in lines:
            line = line.strip()
            if not line:  # Skip empty lines
                continue
            # Check for common playlist patterns
            if (' - ' in line or ' – ' in line or ' — ' in line or 
                ': ' in line or ' :: ' in line or '\t' in line):
                valid_lines += 1
            elif len(line.split()) >= 2:  # At least two words, could be artist song
                valid_lines += 1
        
        # If at least 50% of non-empty lines look like playlist entries
        non_empty_lines = [l for l in lines if l.strip()]
        return valid_lines >= len(non_empty_lines) * 0.5 if non_empty_lines else False
    except:
        return False

def parse_text_playlist_file(file_path):
    """Parse a text file containing artist/song pairs."""
    tracks = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line:  # Skip empty lines
                continue
            
            # Store original line for display
            original_line = line
            
            # Try different separator patterns
            separators = [' - ', ' – ', ' — ', ' : ', ' :: ', '\t']
            artist = None
            title = None
            
            for sep in separators:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2:
                        artist = parts[0].strip()
                        title = parts[1].strip()
                        break
            
            # Handle special cases before falling back to space-separated
            if not artist:
                # Check for "Various -" or "- Track X" patterns
                if line.startswith('Various -') or line.startswith('Various Artists -'):
                    artist = 'Various Artists'
                    title = line.split('-', 1)[1].strip() if '-' in line else line
                elif line.startswith('- '):
                    # Just a title, no artist
                    artist = 'Unknown Artist'
                    title = line[2:].strip()
                # Check for album info in the line (e.g., "Album Name - Artist - Title")
                elif line.count(' - ') >= 2:
                    parts = line.split(' - ')
                    # Could be Album - Artist - Title or Artist - Album - Title
                    # Try to guess based on common patterns
                    if len(parts) >= 3:
                        # Assume first part is less likely to be artist if it has 'disc', 'album', 'vol' etc
                        first_lower = parts[0].lower()
                        if any(word in first_lower for word in ['disc', 'album', 'vol', 'collection', 'anniversary']):
                            # Likely Album - Artist - Title
                            artist = parts[1].strip()
                            title = parts[2].strip()
                        else:
                            # Likely Artist - Album - Title or Artist - Title - Extra
                            artist = parts[0].strip()
                            title = parts[1].strip()  # Use second part as title
                # Handle file path entries (extract from filename)
                elif '/' in line or '\\' in line:
                    # Extract just the filename
                    filename = os.path.basename(line)
                    filename = os.path.splitext(filename)[0]  # Remove extension
                    # Now parse the filename
                    if ' - ' in filename:
                        parts = filename.split(' - ', 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    else:
                        artist = 'Unknown Artist'
                        title = filename
                # Default space-separated fallback
                elif len(line.split()) >= 2:
                    words = line.split()
                    # Simple heuristic: first 1-2 words are artist, rest is title
                    if len(words) > 4:
                        artist = ' '.join(words[:2])
                        title = ' '.join(words[2:])
                    else:
                        artist = words[0]
                        title = ' '.join(words[1:])
                else:
                    # Single word or unrecognized format
                    artist = 'Unknown Artist'
                    title = line
            
            if artist and title:
                # Clean up common issues
                # Remove track numbers from beginning
                title = remove_track_numbers(title)
                artist = remove_track_numbers(artist)
                
                # Remove file extensions that might have been included
                for ext in ['.mp3', '.m4a', '.flac', '.wav', '.ogg', '.wma']:
                    if title.lower().endswith(ext):
                        title = title[:-len(ext)]
                    if artist.lower().endswith(ext):
                        artist = artist[:-len(ext)]
                
                # Handle accented characters and special encoding
                # Common replacements
                replacements = {
                    '%B4': "'",  # Apostrophe
                    '%E9': 'é',   # e acute
                    '%E8': 'è',   # e grave
                    '%E0': 'à',   # a grave
                    '%F4': 'ô',   # o circumflex
                    '%20': ' ',   # Space
                }
                
                for old, new in replacements.items():
                    artist = artist.replace(old, new)
                    title = title.replace(old, new)
                
                tracks.append({
                    'artist': artist.strip(),
                    'title': title.strip(),
                    'album': None,
                    'duration': None,
                    'path': file_path,
                    'original_line': original_line
                })
    
    except Exception as e:
        logger.error(f"Error parsing text playlist file {file_path}: {e}")
    
    return tracks

def parse_playlist_file(file_path):
    """Parse a playlist file based on its extension or content."""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in ['.m3u', '.m3u8']:
        return parse_m3u_playlist(file_path)
    elif ext == '.pls':
        return parse_pls_playlist(file_path)
    else:
        # Check if it's a text playlist file
        if is_text_playlist_file(file_path):
            logger.info(f"Detected text playlist file: {file_path}")
            return parse_text_playlist_file(file_path)
        else:
            logger.warning(f"Unsupported playlist format: {ext}")
            return []

def normalize_artist_name(artist_name):
    """Normalize artist names for better matching."""
    if not artist_name:
        return artist_name
    
    normalized = artist_name.strip()
    
    # Handle specific artist name variations
    artist_variations = {
        'xplastaz': 'X Plastaz',
        'x-plastaz': 'X Plastaz',
        # Add more variations as needed
    }
    
    # Check for exact matches (case insensitive)
    normalized_lower = normalized.lower()
    for old, new in artist_variations.items():
        if normalized_lower == old:
            return new
    
    # Clean up spacing and formatting
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized.strip()

def clean_complex_title(title, artist_name):
    """Clean complex titles with artist prefixes, underscores, and status words."""
    if not title:
        return title
    
    cleaned = title
    
    # Remove file extensions if present
    cleaned = re.sub(r'\.(mp3|flac|wav|m4a|aac|ogg)$', '', cleaned, flags=re.IGNORECASE)
    
    # Remove redundant artist prefixes from filename
    # Examples: "Black_Spade_5_She_s_The_One" -> "She_s_The_One" (if artist is "Black Spade")
    if artist_name:
        # Create pattern for artist name with optional numbers/separators
        artist_clean = re.escape(artist_name.replace(' ', '_').lower())
        # Match: ArtistName_Number_ or ArtistName_ at start
        pattern = f'^{artist_clean}(_\\d+)?_'
        cleaned = re.sub(pattern, '', cleaned.lower(), flags=re.IGNORECASE)
        
        # Also try with spaces
        artist_spaced = re.escape(artist_name.lower())
        pattern = f'^{artist_spaced}(\\s*\\d+)?\\s*[-_]\\s*'
        cleaned = re.sub(pattern, '', cleaned.lower(), flags=re.IGNORECASE)
    
    # Convert underscores to spaces and clean up
    cleaned = cleaned.replace('_', ' ')
    
    # Handle apostrophes and contractions - be more careful to avoid double apostrophes
    cleaned = cleaned.replace(' s ', "'s ")
    # Only convert standalone 's' that isn't already preceded by an apostrophe
    cleaned = re.sub(r'(?<!\')(\s|^)s\b', r"\1's", cleaned)  # Convert standalone 's' to "'s"
    
    # Remove status/quality indicators that appear in filenames
    status_patterns = [
        r'\b(incomplete|demo|rough|draft|wip|work in progress)\b',
        r'\b(remaster|remastered|remix|extended|radio edit)\b',
        r'\b(320|256|192|128)kbps?\b',
        r'\b(mp3|flac|wav)\b',
        r'\b\d+\b'  # Remove standalone numbers
    ]
    
    for pattern in status_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up multiple spaces and dashes
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'^[-\s]+|[-\s]+$', '', cleaned)
    
    # Apply proper title case
    cleaned = cleaned.title()
    
    # Fix common title case issues
    cleaned = re.sub(r"'S\b", "'s", cleaned)  # Fix 's after title case
    cleaned = re.sub(r'\bA\b', 'a', cleaned)  # Fix articles
    cleaned = re.sub(r'\bAn\b', 'an', cleaned)
    cleaned = re.sub(r'\bThe\b', 'the', cleaned)
    cleaned = re.sub(r'\bOf\b', 'of', cleaned)
    cleaned = re.sub(r'\bIn\b', 'in', cleaned)
    cleaned = re.sub(r'\bOn\b', 'on', cleaned)
    cleaned = re.sub(r'\bAt\b', 'at', cleaned)
    cleaned = re.sub(r'\bTo\b', 'to', cleaned)
    cleaned = re.sub(r'\bFor\b', 'for', cleaned)
    cleaned = re.sub(r'\bWith\b', 'with', cleaned)
    cleaned = re.sub(r'\bBy\b', 'by', cleaned)
    
    # Capitalize first word
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
    
    return cleaned.strip()

def filter_album_name(album_name):
    """Filter out non-album content from potential album names."""
    if not album_name:
        return album_name
    
    album_lower = album_name.lower().strip()
    
    # Filter out parts that are likely not album names
    non_album_indicators = [
        'incomplete', 'demo', 'rough', 'draft', 'wip',
        'the show', 'the album', 'the ep', 'the single',
        'live', 'acoustic', 'unplugged', 'studio'
    ]
    
    # If it matches a non-album indicator, don't use it as album
    for indicator in non_album_indicators:
        if indicator in album_lower:
            return ''
    
    # If it's very short, likely not a real album name
    if len(album_name.strip()) < 3:
        return ''
    
    return album_name.strip()

def normalize_string(s):
    """
    Normalize string for better matching.
    Handles unicode, accents, and preserves important punctuation.
    """
    if not s:
        return ""

    import unicodedata

    # Step 1: Normalize unicode (composed vs decomposed characters)
    # NFC = Canonical Composition (é stays as single character)
    s = unicodedata.normalize('NFC', s)

    # Step 2: Fold accents for better matching (José → Jose, Beyoncé → Beyonce)
    # This helps match international artists when spelled without accents
    try:
        # Try using unidecode if available
        from unidecode import unidecode
        # Keep original for comparison, fold for matching
        s_folded = unidecode(s)
    except ImportError:
        # Fallback: manual accent folding using NFD decomposition
        s_folded = ''.join(
            char for char in unicodedata.normalize('NFD', s)
            if unicodedata.category(char) != 'Mn'  # Remove combining marks (accents)
        )

    # Step 3: Convert to lowercase
    s = s_folded.lower()

    # Step 4: Standardize ampersand and "and"
    s = s.replace(' & ', ' and ')
    s = s.replace('&', ' and ')

    # Step 5: Remove extra whitespace and normalize spaces
    s = re.sub(r'\s+', ' ', s).strip()

    # Step 6: Remove punctuation BUT preserve hyphens in words (Jay-Z, X-Ray)
    # Also preserve letters, numbers, spaces, and Unicode characters
    # Remove: quotes, parentheses, brackets, periods, commas, etc.
    # Keep: hyphens when between word characters
    s = re.sub(r'[^\w\s\-\u4e00-\u9fff\u0600-\u06ff\u0400-\u04ff]', '', s)

    # Step 7: Clean up standalone hyphens (not between words)
    s = re.sub(r'\s+-\s+', ' ', s)  # " - " → " "
    s = re.sub(r'^-+|-+$', '', s)   # Leading/trailing hyphens

    # Step 8: Remove common filler words but KEEP "the" for matching
    # (Important for "The XX", "The Beatles" vs "Beatles")
    # Only remove truly meaningless words
    if re.search(r'[a-z]', s):  # Contains English letters
        filler_words = ['a', 'an', 'feat', 'featuring', 'ft']
        words = s.split()
        words = [w for w in words if w not in filler_words]
        s = ' '.join(words)

    # Final cleanup
    s = re.sub(r'\s+', ' ', s).strip()

    return s

def normalize_unicode(text):
    """Normalize Unicode characters to ASCII equivalents."""
    import unicodedata

    if not text:
        return text

    # Decompose accented characters (NFD normalization)
    nfd = unicodedata.normalize('NFD', text)
    # Remove combining marks (accents)
    result = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')

    # Replace special dashes with regular hyphen
    result = result.replace('–', '-').replace('—', '-')  # en-dash, em-dash
    result = result.replace('‐', '-').replace('‑', '-')  # hyphen, non-breaking hyphen

    # Remove emoji (characters in emoji ranges)
    result = ''.join(c for c in result if ord(c) < 0x1F600 or ord(c) > 0x1F64F)

    return result

def normalize_for_variations(text):
    """Apply common variations normalization with Unicode handling."""
    if not text:
        return ""

    # Normalize Unicode characters first
    text = normalize_unicode(text)

    # Convert to lowercase
    text = text.lower()

    # Apply common variations
    for variant, normalized in COMMON_VARIATIONS.items():
        # Use word boundaries to avoid partial replacements
        pattern = r'\b' + re.escape(variant) + r'\b'
        text = re.sub(pattern, normalized, text)

    return text

def remove_track_numbers(text):
    """Remove common track number patterns from text."""
    for pattern in TRACK_NUMBER_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return text.strip()

def clean_filename_tags(text):
    """Remove YouTube, quality tags, disc numbers, and other filename artifacts."""
    for pattern in FILENAME_CLEANUP_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return text.strip()

def strip_remaster_tags(text):
    """Remove remaster tags but keep remix tags."""
    # Remove remaster tags but keep remix
    remaster_patterns = [
        r'\s*[\(\[]\s*remaster(?:ed)?\s*(?:\d{4})?\s*[\)\]]\s*',
        r'\s*-\s*remaster(?:ed)?\s*(?:\d{4})?\s*$',
        r'\s*[\(\[]\s*\d{4}\s*remaster\s*[\)\]]\s*',
        r'\s*[\(\[]\s*anniversary\s*edition\s*[\)\]]\s*',
        r'\s*[\(\[]\s*deluxe\s*edition\s*[\)\]]\s*',
        r'\s*[\(\[]\s*expanded\s*edition\s*[\)\]]\s*'
    ]
    
    for pattern in remaster_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text.strip()

def phonetic_match(s1, s2, threshold=85):
    """Check if two strings are phonetically similar."""
    try:
        import metaphone
        # Get primary metaphone codes
        meta1 = metaphone.doublemetaphone(s1)[0]
        meta2 = metaphone.doublemetaphone(s2)[0]
        
        if meta1 and meta2:
            # If metaphones match exactly, high confidence
            if meta1 == meta2:
                return 95
            # Otherwise use fuzzy matching on metaphones
            return fuzz.ratio(meta1, meta2)
    except ImportError:
        # Fallback to soundex-like simple phonetic comparison
        # Remove vowels except first letter and compare
        def simple_phonetic(s):
            if not s:
                return ""
            s = s.lower()
            # Keep first letter, remove subsequent vowels
            result = s[0]
            for c in s[1:]:
                if c not in 'aeiou':
                    result += c
            return result
        
        p1 = simple_phonetic(s1)
        p2 = simple_phonetic(s2)
        
        if p1 == p2:
            return 90
        return fuzz.ratio(p1, p2)

def extract_featuring_info(text):
    """Extract main artist and featuring artists from a string."""
    # Look for featuring patterns
    feat_patterns = [
        r'\s+[\[\(](?:feat\.?|featuring|ft\.?)\s+([^\]\)]+)[\]\)]',  # [feat. X] or (feat. X)
        r'\s+(?:feat\.?|featuring|ft\.?)\s+(.+?)(?:\s*[\[\(]|$)',  # feat. X (before bracket or end)
        r'\s+[\[\(](?:with|w\/)\s+([^\]\)]+)[\]\)]',  # [with X] or (with X)
    ]
    
    main_text = text
    featuring = ""
    
    for pattern in feat_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            featuring = match.group(1).strip()
            main_text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
            break
    
    return main_text, featuring

def process_search_results(results, search_artist, search_title, search_album, candidates, weight=1.0):
    """Process search results and add candidates with scores."""
    if not results or 'tracks' not in results or not results['tracks']['items']:
        return
    
    for track in results['tracks']['items']:
        if not track:
            continue
            
        result_artists = ', '.join([artist['name'] for artist in track['artists']])
        result_title = track['name']
        result_album = track['album']['name'] if track['album'] else ""

        # Calculate match score using consolidated scoring function
        score = consolidated_track_score(
            search_artist=search_artist or "",
            search_title=search_title or "",
            result_artist=result_artists,
            result_title=result_title,
            result_album=result_album,
            search_album=search_album or ""
        )
        
        # Apply weight and check if it's a meaningful match
        weighted_score = score * weight
        
        if weighted_score > 30:  # Only consider reasonably good matches
            candidate = {
                'track': track,
                'score': weighted_score,
                'artist_match': result_artists,
                'title_match': result_title,
                'album_match': result_album
            }
            candidates.append(candidate)

def search_track_on_spotify(sp, artist, title, album=None):
    """
    Search for a track on Spotify with enhanced fuzzy matching.
    Uses caching to avoid redundant API calls.
    """
    from spotify_utils import optimized_track_search_strategies, strip_remix_tags

    if not title:
        return None

    # Create a cache key based on artist, album and title using MD5 hash
    # This prevents issues with long names, special characters, and URL encoding
    import hashlib

    # Normalize the components for consistent caching
    clean_artist = normalize_for_variations(artist) if artist else "none"
    clean_title = normalize_for_variations(title) if title else "none"
    clean_album = normalize_for_variations(album) if album else "none"

    # Extract version info for version-aware caching
    # This prevents "Song" and "Song (Remix)" from colliding in cache
    version_keywords = ['remix', 'rmx', 'mix', 'live', 'acoustic', 'demo', 'radio edit', 'extended', 'vip', 'bootleg', 'mashup']
    title_lower = title.lower() if title else ""
    version_type = next((kw for kw in version_keywords if kw in title_lower), "none")

    # Create a stable string representation with version info
    cache_string = f"{clean_artist}|{clean_title}|{clean_album}|{version_type}"

    # Hash it for a short, safe cache key
    # Use MD5 (fast, good enough for cache keys, not security)
    # Take first 16 chars of hex digest for short keys
    cache_hash = hashlib.md5(cache_string.encode('utf-8')).hexdigest()[:16]

    # Include version in key so algorithm improvements invalidate old cache
    algorithm_version = "v2"  # Increment when scoring/matching logic changes
    cache_key = f"track_search_{algorithm_version}_{cache_hash}"

    # Try to load from cache first
    # Use 'long' expiration (7 days) for track searches since:
    # - Track metadata doesn't change often (positive cache)
    # - Negative results might become available later (7-day retry window)
    cached_result = load_from_cache(cache_key, CACHE_EXPIRATION['long'])
    if cached_result:
        # Check if this is a negative cache entry (track not found)
        # Handle corrupted cache gracefully - negative cache entries must be dicts
        if isinstance(cached_result, dict) and cached_result.get('__negative_cache__'):
            logger.debug(f"Using cached negative result (not found) for '{artist} - {title}' (version: {cached_result.get('version_type', 'unknown')})")
            return None
        # Validate cache entry is a dict (not corrupted string data)
        if not isinstance(cached_result, dict):
            logger.warning(f"Corrupted cache entry for '{artist} - {title}', ignoring")
        else:
            logger.debug(f"Using cached result for '{artist} - {title}'")
            return cached_result
    
    # Clean up the title and artist while preserving Unicode characters
    # Remove common file extensions and numbering
    title = re.sub(r'\.mp3$|\.flac$|\.wav$|\.m4a$|\.ogg$|\.wma$|\.aac$|\.opus$', '', title, flags=re.IGNORECASE)
    title = remove_track_numbers(title)
    # Remove YouTube, quality tags, and other filename artifacts
    title = clean_filename_tags(title)
    if artist:
        artist = clean_filename_tags(artist)

    # Ensure proper Unicode handling
    if isinstance(title, bytes):
        title = title.decode('utf-8', errors='ignore')
    if isinstance(artist, bytes):
        artist = artist.decode('utf-8', errors='ignore')
    
    # Handle cases where artist might be in the title
    if not artist and " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()
    
    # Also check if we have title - artist format (reversed)
    elif artist and not title and " - " in artist:
        parts = artist.split(" - ", 1)
        title = parts[0].strip()
        artist = parts[1].strip()
    
    # Extract and clean featuring info for better searching
    artist_main, artist_feat = extract_featuring_info(artist) if artist else ("", "")
    title_main, title_feat = extract_featuring_info(title) if title else ("", "")
    
    # Use cleaned versions for search
    if artist_main:
        artist = artist_main
    if title_main:
        title = title_main

    # Apply learned patterns to improve matching
    artist, title = apply_learning_patterns(artist, title)

    # Log the search parameters
    logger.debug(f"Searching for: Artist='{artist}', Album='{album}', Title='{title}'")

    # Use optimized search strategies - much faster than 13 individual searches
    try:
        result = optimized_track_search_strategies(sp, artist, title, album, max_strategies=7)

        if result:
            logger.debug(f"Optimized search found: {result['name']} by {result['artists']} (Score: {result['score']:.1f})")
            save_to_cache(result, cache_key)
            return result
    except Exception as e:
        logger.error(f"Error in optimized search: {e}")
        # Continue to fallback strategies

    # Fallback to original complex strategies for edge cases
    candidates = []
    
    # Strategy 8a: Try removing parenthetical content as backup
    # For cases like "Ada - The Jazz Singer (Re-Imagined By Ada)" -> try "Ada - The Jazz Singer"
    simple_title = re.sub(r'\s*[\(\[].*?[\)\]]\s*', '', title).strip()
    if simple_title != title and simple_title:
        query8a = f"artist:\"{artist}\" track:\"{simple_title}\"" if artist else f"\"{simple_title}\""
        logger.debug(f"Strategy 8a (simplified title): {query8a}")
        try:
            results8a = sp.search(q=query8a, type='track', limit=10)
            # Give these results a higher weight since simplified titles often match better
            process_search_results(results8a, artist, simple_title, album, candidates, weight=1.1)
        except Exception as e:
            logger.error(f"Error in search strategy 8a: {e}")
    
    # Strategy 8b: Try swapping artist and title (common in some playlists)
    if artist and title and ' - ' not in artist:  # Only swap if artist doesn't contain ' - '
        query8b = f"artist:\"{title}\" track:\"{artist}\""
        logger.debug(f"Strategy 8b (swapped artist/title): {query8b}")
        try:
            results8b = sp.search(q=query8b, type='track', limit=10)
            # Process results with swapped expectations
            if results8b['tracks']['items']:
                for track in results8b['tracks']['items']:
                    track_artists = ', '.join([a['name'] for a in track['artists']])
                    track_title = track['name']
                    
                    # Check if this looks like a swap (title matches our artist, artist matches our title)
                    title_to_artist_score = fuzz.ratio(title.lower(), track_artists.lower())
                    artist_to_title_score = fuzz.ratio(artist.lower(), track_title.lower())
                    
                    if title_to_artist_score > 70 and artist_to_title_score > 70:
                        # This is likely a swapped match
                        candidates.append({
                            'track': track,
                            'score': (title_to_artist_score + artist_to_title_score) / 2 * 0.9,  # Slight penalty for swap
                            'artist_match': track_artists,
                            'title_match': track_title,
                            'album_match': track['album']['name'] if track['album'] else "",
                            'swapped': True
                        })
        except Exception as e:
            logger.error(f"Error in search strategy 8b: {e}")
    
    # Strategy 8c: Try title-only search but check if artist matches
    if artist:
        query8c = f"\"{title}\""
        logger.debug(f"Strategy 8c (title only, verify artist): {query8c}")
        try:
            results8c = sp.search(q=query8c, type='track', limit=20)
            if results8c['tracks']['items']:
                for track in results8c['tracks']['items']:
                    track_artists = ', '.join([a['name'] for a in track['artists']])
                    # Check if any artist name is similar to our search
                    artist_match = False
                    best_artist_score = 0
                    for a in track['artists']:
                        score = fuzz.ratio(artist.lower(), a['name'].lower())
                        if score > best_artist_score:
                            best_artist_score = score
                        if score > 70:
                            artist_match = True
                    
                    if artist_match:
                        # Calculate score based on how well artist matches
                        candidates.append({
                            'track': track,
                            'score': min(95, 60 + best_artist_score * 0.35),  # Score 60-95 based on artist match
                            'artist_match': track_artists,
                            'title_match': track['name'],
                            'album_match': track['album']['name'] if track['album'] else ""
                        })
        except Exception as e:
            logger.error(f"Error in search strategy 8c: {e}")
    
    # Strategy 8d: Search for just our artist name and see if any results have our title as artist
    if artist and title:
        query8d = f"\"{artist}\""
        logger.debug(f"Strategy 8d (artist only, check for title as artist): {query8d}")
        try:
            results8d = sp.search(q=query8d, type='track', limit=20)
            if results8d['tracks']['items']:
                for track in results8d['tracks']['items']:
                    track_title = track['name']
                    track_artists_str = ', '.join([a['name'] for a in track['artists']])
                    
                    # Check if our title matches any of the artists
                    title_matches_artist = False
                    for a in track['artists']:
                        if fuzz.ratio(title.lower(), a['name'].lower()) > 80:
                            title_matches_artist = True
                            break
                    
                    # Check if track title matches our artist
                    artist_matches_title = fuzz.ratio(artist.lower(), track_title.lower()) > 80
                    
                    if title_matches_artist and artist_matches_title:
                        # Strong indication of a swap
                        candidates.append({
                            'track': track,
                            'score': 88,  # High score for confirmed swap
                            'artist_match': track_artists_str,
                            'title_match': track_title,
                            'album_match': track['album']['name'] if track['album'] else "",
                            'swapped': True
                        })
        except Exception as e:
            logger.error(f"Error in search strategy 8d: {e}")

    # Strategy 9: Handle "Various Artists" cases by searching title + album
    if artist and artist.lower() in ['various', 'various artists', 'va'] and album:
        # Search for the title in the specific album/compilation
        query9 = f"album:\"{album}\" \"{title}\""
        logger.debug(f"Strategy 9 (Various Artists): {query9}")
        try:
            apply_rate_limit()
            results9 = sp.search(q=query9, type='track', limit=20)
            process_search_results(results9, artist, title, album, candidates, weight=1.3)
        except Exception as e:
            logger.error(f"Error in search strategy 9: {e}")

    # Strategy 10: Title-only search for Various Artists compilations
    if artist and artist.lower() in ['various', 'various artists', 'va']:
        # Just search the title and let fuzzy matching handle the artist detection
        query10 = f"\"{title}\""
        logger.debug(f"Strategy 10 (Various Artists title-only): {query10}")
        try:
            apply_rate_limit()
            results10 = sp.search(q=query10, type='track', limit=25)
            process_search_results(results10, None, title, album, candidates, weight=1.1)
        except Exception as e:
            logger.error(f"Error in search strategy 10: {e}")

    # Strategy 11: Try variations of artist names (handle common misspellings)
    if artist:
        artist_variations = []
        # Handle common variations like "Cee-Lo" vs "CeeLo"
        if '-' in artist:
            artist_variations.append(artist.replace('-', ''))
            artist_variations.append(artist.replace('-', ' '))
        # Handle "X Plastaz" vs "Xplastaz"
        if ' ' in artist:
            artist_variations.append(artist.replace(' ', ''))

        for alt_artist in artist_variations:
            if alt_artist != artist:
                query11 = f"artist:\"{alt_artist}\" \"{title}\""
                logger.debug(f"Strategy 11 (artist variation): {query11}")
                try:
                    apply_rate_limit()
                    results11 = sp.search(q=query11, type='track', limit=10)
                    process_search_results(results11, alt_artist, title, album, candidates, weight=1.15)
                except Exception as e:
                    logger.error(f"Error in search strategy 11: {e}")
                break  # Only try one variation to avoid too many API calls
    
    # If we have no candidates, cache the negative result and return None
    if not candidates:
        logger.debug("No candidates found for this track")

        # Remix fallback: if this is a remix and we can't find it, try the original
        remix_keywords = ['remix', 'rmx', 'mix', 'edit', 'rework', 'bootleg', 'mashup', 'vip', 'dub']
        is_remix = any(keyword in title.lower() for keyword in remix_keywords)

        if is_remix:
            original_title = strip_remix_tags(title)

            # Only try if we actually stripped something
            if original_title != title and original_title:
                logger.debug(f"Remix not found, trying original version: {original_title}")

                # Recursively search for the original (but prevent infinite loops with a flag)
                # We'll use a simple approach: search directly without recursive call
                try:
                    original_match = optimized_track_search_strategies(sp, artist, original_title, album, max_strategies=7)

                    if original_match and original_match.get('score', 0) >= 60:
                        # Found the original version
                        original_match['remix_fallback'] = True
                        original_match['original_search_title'] = title  # Store what user searched for
                        logger.info(f"Found original version as fallback: {original_match['name']} (Score: {original_match['score']:.1f})")
                        # Don't cache this since it's a fallback, user needs to decide
                        return original_match
                except Exception as e:
                    logger.debug(f"Error searching for original version: {e}")

        # Save negative cache entry to prevent retry spam for tracks that don't exist
        # Uses a marker so we can distinguish negative results from positive ones
        # Auto-expires after 7 days (via CACHE_EXPIRATION['long']) in case track becomes available later
        negative_cache_entry = {
            '__negative_cache__': True,
            'timestamp': time.time(),
            'search_params': {'artist': artist, 'title': title, 'album': album},
            'version_type': version_type  # Track which version this was for (remix, live, etc.)
        }
        save_to_cache(negative_cache_entry, cache_key)
        logger.debug(f"Cached negative result for '{artist} - {title}' (version: {version_type}, expires in 7 days)")
        return None
    
    # Remove duplicates (same track ID)
    unique_candidates = {}
    for candidate in candidates:
        track_id = candidate['track']['id']
        if track_id not in unique_candidates or candidate['score'] > unique_candidates[track_id]['score']:
            unique_candidates[track_id] = candidate
    
    # Sort by score
    sorted_candidates = sorted(unique_candidates.values(), key=lambda x: x['score'], reverse=True)
    
    # Log the top candidates for debugging
    for i, candidate in enumerate(sorted_candidates[:3]):
        logger.debug(f"Candidate {i+1}: {', '.join([a['name'] for a in candidate['track']['artists']])} - "
                    f"{candidate['track']['name']} (Album: {candidate['track']['album']['name']}) "
                    f"Score: {candidate['score']:.1f}")
    
    best_match = sorted_candidates[0]
    
    result = {
        'id': best_match['track']['id'],
        'name': best_match['track']['name'],
        'artists': [artist['name'] for artist in best_match['track']['artists']],
        'album': best_match['track']['album']['name'],
        'score': best_match['score'],
        'uri': best_match['track']['uri']
    }
    
    # Save to cache
    save_to_cache(result, cache_key)
    
    return result

def get_user_playlists(sp, user_id):
    """
    Get all playlists for the current user.
    Uses session-level caching and disk caching to avoid redundant API calls.
    """
    global _user_playlists_cache, _user_playlists_cache_time
    
    # Check session-level cache first (valid for 10 minutes)
    if _user_playlists_cache and (time.time() - _user_playlists_cache_time) < 600:
        logger.debug("Using session-cached user playlists")
        return _user_playlists_cache
    
    cache_key = f"user_playlists_{user_id}"
    
    # Try to load from disk cache
    cached_playlists = load_from_cache(cache_key, 60 * 60)  # Cache for 1 hour
    if cached_playlists is not None:
        # Check if cache returned an empty list (which would be a problem)
        if isinstance(cached_playlists, list) and len(cached_playlists) == 0:
            logger.warning("Disk cache returned empty playlist list - fetching fresh data")
        else:
            logger.debug(f"Using disk-cached user playlists ({len(cached_playlists)} playlists)")
            _user_playlists_cache = cached_playlists
            _user_playlists_cache_time = time.time()
            return cached_playlists
    
    playlists = []
    offset = 0
    limit = 50
    
    while True:
        response = sp.current_user_playlists(limit=limit, offset=offset)
        playlists.extend(response['items'])
        
        logger.debug(f"Fetched {len(response['items'])} playlists at offset {offset}")
        
        if len(response['items']) < limit:
            break
        
        offset += limit
    
    logger.info(f"Fetched total of {len(playlists)} playlists from Spotify API")
    
    # Save to caches
    save_to_cache(playlists, cache_key)
    _user_playlists_cache = playlists
    _user_playlists_cache_time = time.time()
    
    return playlists

def get_playlist_tracks(sp, playlist_id):
    """
    Get all tracks in a playlist.
    Uses caching to avoid redundant API calls.
    """
    cache_key = f"playlist_tracks_{playlist_id}"
    
    # Try to load from cache first
    cached_tracks = load_from_cache(cache_key, 60 * 60)  # Cache for 1 hour
    if cached_tracks:
        logger.debug(f"Using cached tracks for playlist {playlist_id}")
        return cached_tracks
    
    tracks = []
    offset = 0
    limit = 100
    
    while True:
        response = sp.playlist_items(
            playlist_id, 
            fields='items(track(uri)),total',
            limit=limit,
            offset=offset
        )
        
        tracks.extend([item['track']['uri'] for item in response['items'] if item['track']])
        
        if len(response['items']) < limit:
            break
        
        offset += limit
    
    # Save to cache
    save_to_cache(tracks, cache_key)
    
    return tracks

def check_for_duplicate_playlists(sp, playlist_name, track_uris, user_id):
    """Check for existing playlists that might be duplicates based on name similarity and content."""
    playlists = get_user_playlists(sp, user_id)
    
    # Clean the playlist name - remove common file extensions
    clean_name = playlist_name
    for ext in ['.m3u', '.m3u8', '.pls', '.txt']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break
    
    # Look for exact name matches (including with/without extensions)
    exact_matches = []
    suffix_matches = []  # Playlists that match when ignoring file extensions
    
    for playlist in playlists:
        if playlist['name'] == playlist_name:
            exact_matches.append(playlist)
        elif playlist['name'] == clean_name or playlist['name'].startswith(clean_name + '.'):
            # Check if it's the same name with just a file extension difference
            suffix_matches.append(playlist)
    
    # Look for similar name matches
    similar_matches = []
    norm_target_name = normalize_string(clean_name).lower()
    
    for playlist in playlists:
        if playlist['name'] != playlist_name and playlist not in suffix_matches:  # Skip exact and suffix matches
            norm_playlist_name = normalize_string(playlist['name']).lower()
            # Also check without extensions
            clean_playlist_name = playlist['name']
            for ext in ['.m3u', '.m3u8', '.pls', '.txt']:
                if clean_playlist_name.lower().endswith(ext):
                    clean_playlist_name = clean_playlist_name[:-len(ext)]
                    break
            norm_clean_playlist_name = normalize_string(clean_playlist_name).lower()
            
            # Check similarity with both original and cleaned names
            similarity = max(
                fuzz.ratio(norm_target_name, norm_playlist_name),
                fuzz.ratio(norm_target_name, norm_clean_playlist_name)
            )
            
            # Consider names similar if they have >80% similarity
            if similarity > 80:
                similar_matches.append({
                    'playlist': playlist,
                    'similarity': similarity
                })
    
    # Sort matches by track count (keep the one with most tracks)
    exact_matches.sort(key=lambda p: p['tracks']['total'], reverse=True)
    suffix_matches.sort(key=lambda p: p['tracks']['total'], reverse=True)
    similar_matches.sort(key=lambda x: (x['similarity'], x['playlist']['tracks']['total']), reverse=True)
    
    return exact_matches, suffix_matches, similar_matches

def create_or_update_spotify_playlist(sp, playlist_name, track_uris, user_id):
    """Create a new Spotify playlist or update an existing one."""
    # Check for duplicate playlists first
    exact_matches, suffix_matches, similar_matches = check_for_duplicate_playlists(sp, playlist_name, track_uris, user_id)
    
    # Handle suffix matches (e.g., "Playlist" vs "Playlist.m3u")
    if suffix_matches:
        print(f"\n{Fore.YELLOW}⚠️  Found duplicate playlists with file extensions:")
        all_suffix_playlists = suffix_matches + exact_matches
        all_suffix_playlists.sort(key=lambda p: p['tracks']['total'], reverse=True)
        
        for i, playlist in enumerate(all_suffix_playlists[:5], 1):  # Show top 5
            suffix_indicator = " (current name)" if playlist['name'] == playlist_name else ""
            print(f"{i}. {playlist['name']} ({playlist['tracks']['total']} tracks){suffix_indicator}")
        
        print(f"\n{Fore.CYAN}These appear to be the same playlist with different file extensions.")
        print(f"Options:")
        print(f"1. Keep the playlist with most tracks and remove others")
        print(f"2. Update the playlist with most tracks (add missing songs)")
        print(f"3. Keep all playlists as separate")
        
        choice = input(f"\n{Fore.CYAN}Choose option (1-3): ").strip()
        
        if choice == "1":
            # Keep playlist with most tracks, delete others
            keeper = all_suffix_playlists[0]
            for playlist in all_suffix_playlists[1:]:
                try:
                    sp.current_user_unfollow_playlist(playlist['id'])
                    print(f"{Fore.GREEN}✓ Removed duplicate: {playlist['name']}")
                except Exception as e:
                    print(f"{Fore.RED}✗ Failed to remove {playlist['name']}: {e}")
            
            exact_matches = [keeper]
            print(f"{Fore.GREEN}✓ Keeping: {keeper['name']} ({keeper['tracks']['total']} tracks)")
            
        elif choice == "2":
            # Use the one with most tracks
            exact_matches = [all_suffix_playlists[0]]
            print(f"{Fore.GREEN}✓ Will update: {exact_matches[0]['name']}")
            
        # For option 3, continue as normal (create new playlist)
    
    # Handle similar matches - ask user if they want to use existing playlist
    elif similar_matches and not exact_matches:
        print(f"\n{Fore.YELLOW}⚠️  Found similar playlists that might be duplicates:")
        for i, match in enumerate(similar_matches[:3], 1):  # Show top 3 matches
            playlist = match['playlist']
            similarity = match['similarity']
            print(f"{i}. {playlist['name']} ({similarity:.0f}% similar, {playlist['tracks']['total']} tracks)")
        
        print(f"\n{Fore.CYAN}Options:")
        print(f"1. Use existing similar playlist (will add new tracks)")
        print(f"2. Create new playlist '{playlist_name}'")
        
        choice = input(f"\n{Fore.CYAN}Choose option (1-2): ").strip()
        
        if choice == "1":
            # Ask which playlist to use
            if len(similar_matches) == 1:
                exact_matches = [similar_matches[0]['playlist']]
            else:
                playlist_choice = input(f"\n{Fore.CYAN}Which playlist to use? (1-{min(len(similar_matches), 3)}): ").strip()
                try:
                    idx = int(playlist_choice) - 1
                    if 0 <= idx < len(similar_matches):
                        exact_matches = [similar_matches[idx]['playlist']]
                except ValueError:
                    print(f"{Fore.YELLOW}Invalid choice, creating new playlist.")
    
    # Handle exact matches or selected similar playlist
    existing_playlist = None
    if exact_matches:
        existing_playlist = exact_matches[0]  # Use the first exact match
    
    if existing_playlist:
        logger.info(f"Found existing playlist: {playlist_name}")
        playlist_id = existing_playlist['id']
        
        # Get existing tracks
        existing_tracks = get_playlist_tracks(sp, playlist_id)
        logger.info(f"Existing playlist has {len(existing_tracks)} tracks")

        # Find orphaned tracks (in Spotify but not in local playlist)
        orphaned_tracks = [uri for uri in existing_tracks if uri not in track_uris]

        if orphaned_tracks:
            print(f"\n{Fore.YELLOW}⚠️  Found {len(orphaned_tracks)} track(s) in Spotify playlist '{playlist_name}' that are NOT in the local playlist file:")

            # Get track details for orphaned tracks
            orphaned_details = []
            for uri in orphaned_tracks[:10]:  # Show first 10
                try:
                    track_id = uri.split(':')[-1]
                    track = sp.track(track_id)
                    orphaned_details.append(track)
                    artists = ', '.join([a['name'] for a in track['artists']])
                    print(f"  • {track['name']} by {artists}")
                except:
                    pass

            if len(orphaned_tracks) > 10:
                print(f"  ... and {len(orphaned_tracks) - 10} more")

            print(f"\n{Fore.CYAN}These tracks exist in your Spotify playlist but are not in your local playlist file.")
            print(f"Options:")
            print(f"1. Remove these tracks from Spotify playlist (sync with local)")
            print(f"2. Keep them (they might have been added manually)")

            choice = input(f"\n{Fore.CYAN}Choose option (1-2): ").strip()

            if choice == "1":
                # Remove orphaned tracks
                print(f"{Fore.YELLOW}Removing {len(orphaned_tracks)} orphaned track(s)...")
                try:
                    # Remove in batches of 100 (Spotify API limit)
                    for i in range(0, len(orphaned_tracks), 100):
                        batch = orphaned_tracks[i:i+100]
                        # Create snapshot with positions for removal
                        sp.playlist_remove_all_occurrences_of_items(playlist_id, batch)

                    print(f"{Fore.GREEN}✅ Removed {len(orphaned_tracks)} track(s) from Spotify playlist")

                    # Update existing_tracks list
                    existing_tracks = [uri for uri in existing_tracks if uri not in orphaned_tracks]
                    logger.info(f"Updated playlist now has {len(existing_tracks)} tracks")
                except Exception as e:
                    print(f"{Fore.RED}✗ Error removing tracks: {e}")
            else:
                print(f"{Fore.YELLOW}Keeping orphaned tracks in Spotify playlist")

        # Find tracks to add (tracks in track_uris but not in existing_tracks)
        tracks_to_add = [uri for uri in track_uris if uri not in existing_tracks]
        duplicates_skipped = len(track_uris) - len(tracks_to_add)
        
        if duplicates_skipped > 0:
            logger.info(f"Skipping {duplicates_skipped} duplicate tracks already in playlist")
        
        if tracks_to_add:
            logger.info(f"Adding {len(tracks_to_add)} new tracks to playlist '{playlist_name}'")
            
            # Add tracks in batches of 100 (Spotify API limit)
            for i in range(0, len(tracks_to_add), 100):
                batch = tracks_to_add[i:i+100]
                try:
                    sp.playlist_add_items(playlist_id, batch)
                except Exception as e:
                    if "insufficient client scope" in str(e).lower():
                        logger.error("Insufficient permissions to modify playlists. Please re-authenticate with proper scopes.")
                        logger.error("Go to menu option 10 to re-enter your Spotify credentials.")
                        raise Exception("Spotify authentication needs to be refreshed with playlist modification permissions.")
                    else:
                        raise e
            
            # Update the cache for this playlist's tracks
            cache_key = f"playlist_tracks_{playlist_id}"
            save_to_cache(existing_tracks + tracks_to_add, cache_key)
            
            logger.info(f"✅ Successfully updated playlist '{playlist_name}' - now has {len(existing_tracks) + len(tracks_to_add)} total tracks")
            
            # Check for duplicates after adding tracks
            if len(tracks_to_add) > 0:
                print(f"\n{Fore.CYAN}🔍 Checking for duplicates in updated playlist...")
                duplicates = detect_playlist_duplicates(sp, playlist_id)
                if duplicates:
                    print(f"Found {len(duplicates)} potential duplicates:")
                    for i, dup in enumerate(duplicates[:5], 1):  # Show first 5
                        track = dup['track']
                        print(f"  {i}. {track['name']} by {', '.join(track['artists'])} ({dup['type']})")
                    if len(duplicates) > 5:
                        print(f"  ... and {len(duplicates) - 5} more")
                    
                    # Handle duplicates based on user preference
                    should_remove = False
                    if DUPLICATE_CONFIG['keep_all']:
                        print(f"{Fore.YELLOW}Keeping all duplicates (as requested)")
                        should_remove = False
                    elif DUPLICATE_CONFIG['auto_remove']:
                        print(f"{Fore.GREEN}Auto-removing duplicates (as requested)")
                        should_remove = True
                    else:
                        # Ask user (default behavior)
                        remove_choice = input(f"\n{Fore.CYAN}Remove duplicates? (y/n): ").lower().strip()
                        should_remove = (remove_choice == 'y')
                    
                    if should_remove:
                        removed = remove_playlist_duplicates(sp, playlist_id, duplicates)
                        print(f"{Fore.GREEN}✅ Removed {removed} duplicate tracks")
                        # Clear cache to force refresh
                        cache_key = f"playlist_tracks_{playlist_id}"
                        save_to_cache(None, cache_key, force_expire=True)
                    else:
                        print(f"{Fore.YELLOW}Duplicates kept in playlist")
                else:
                    print(f"{Fore.GREEN}✅ No duplicates found")
            
            return playlist_id, len(tracks_to_add)
        else:
            logger.info(f"✅ Playlist '{playlist_name}' is already complete. No new tracks to add.")
            return playlist_id, 0
    else:
        logger.info(f"Creating new playlist: {playlist_name}")
        playlist = sp.user_playlist_create(
            user=user_id,
            name=playlist_name,
            public=False,
            description=f"Playlist created from local file by Spotify Playlist Converter"
        )
        
        logger.info(f"Adding {len(track_uris)} tracks to new playlist")
        
        # Add tracks in batches of 100 (Spotify API limit)
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]
            sp.playlist_add_items(playlist['id'], batch)
        
        # Update the user playlists cache
        cache_key = f"user_playlists_{user_id}"
        current_playlists = get_user_playlists(sp, user_id)
        current_playlists.append(playlist)
        save_to_cache(current_playlists, cache_key)
        
        # Cache the playlist tracks
        cache_key = f"playlist_tracks_{playlist['id']}"
        save_to_cache(track_uris, cache_key)
        
        logger.info(f"✅ Successfully created playlist '{playlist_name}' with {len(track_uris)} tracks")
        
        # Check for duplicates in new playlist
        if len(track_uris) > 1:
            print(f"\n{Fore.CYAN}🔍 Checking for duplicates in new playlist...")
            duplicates = detect_playlist_duplicates(sp, playlist['id'])
            if duplicates:
                print(f"Found {len(duplicates)} potential duplicates:")
                for i, dup in enumerate(duplicates[:5], 1):  # Show first 5
                    track = dup['track']
                    print(f"  {i}. {track['name']} by {', '.join(track['artists'])} ({dup['type']})")
                if len(duplicates) > 5:
                    print(f"  ... and {len(duplicates) - 5} more")
                
                # Handle duplicates based on user preference
                should_remove = False
                if DUPLICATE_CONFIG['keep_all']:
                    print(f"{Fore.YELLOW}Keeping all duplicates (as requested)")
                    should_remove = False
                elif DUPLICATE_CONFIG['auto_remove']:
                    print(f"{Fore.GREEN}Auto-removing duplicates (as requested)")
                    should_remove = True
                else:
                    # Ask user (default behavior)
                    remove_choice = input(f"\n{Fore.CYAN}Remove duplicates? (y/n): ").lower().strip()
                    should_remove = (remove_choice == 'y')
                
                if should_remove:
                    removed = remove_playlist_duplicates(sp, playlist['id'], duplicates)
                    print(f"{Fore.GREEN}✅ Removed {removed} duplicate tracks")
                    # Clear cache to force refresh
                    cache_key = f"playlist_tracks_{playlist['id']}"
                    save_to_cache(None, cache_key, force_expire=True)
                else:
                    print(f"{Fore.YELLOW}Duplicates kept in playlist")
            else:
                print(f"{Fore.GREEN}✅ No duplicates found")
        
        return playlist['id'], len(track_uris)

def manual_search_flow(sp, track):
    """Handle manual search flow for a track."""
    print(f"\nManual search for: {track.get('artist', '')} - {track.get('title', '')}")
    
    # Check if AI assistance is available
    ai_available = False
    ai_creds = get_ai_credentials()
    if ai_creds:
        ai_available = True
        print(f"{Fore.CYAN}AI assistance available: {', '.join(ai_creds.keys())}")
    
    while True:
        options = "\nEnter search query (artist - title) or 'skip' to skip"
        if ai_available:
            options += " or 'ai' for AI help"
        options += ": "
        
        search_query = input(options).strip()
        
        if search_query.lower() == 'skip':
            return None
        
        if search_query.lower() == 'ai' and ai_available:
            # Try AI-assisted search
            from ai_track_matcher import ai_assisted_search
            print(f"\n{Fore.YELLOW}Requesting AI assistance...")
            ai_match = ai_assisted_search(sp, track.get('artist', ''), track.get('title', ''), track.get('album'))
            
            if ai_match:
                print(f"\n{Fore.GREEN}AI suggestion:")
                print(f"Found: {', '.join(ai_match['artists'])} - {ai_match['name']}")
                print(f"Album: {ai_match['album']} (Score: {ai_match['score']:.1f})")
                if ai_match.get('ai_notes'):
                    print(f"{Fore.YELLOW}AI notes: {ai_match['ai_notes']}")
                
                confirm = input("\nAccept AI suggestion? (y/n): ").lower().strip()
                if confirm == 'y':
                    return ai_match
            else:
                print(f"{Fore.RED}AI couldn't identify the track.")
            continue
        
        if ' - ' in search_query:
            parts = search_query.split(' - ', 1)
            search_artist = parts[0].strip()
            search_title = parts[1].strip()
        else:
            search_artist = ""
            search_title = search_query
        
        search_album = input("Album (optional, press Enter to skip): ").strip() or None
        
        match = search_track_on_spotify(sp, search_artist, search_title, search_album)
        
        if match:
            print(f"\nFound: {', '.join(match['artists'])} - {match['name']}")
            print(f"Album: {match['album']} (Score: {match['score']:.1f})")
            
            while True:
                confirm = input("Accept? (y/n/s to search again): ").lower().strip()
                if confirm == 'y':
                    return match
                elif confirm == 'n':
                    skip_choice = input("Skip this track entirely? (y/n): ").lower().strip()
                    if skip_choice == 'y':
                        return None
                    else:
                        break  # Go back to search
                elif confirm == 's':
                    break  # Go back to search
                else:
                    print("Please enter y, n, or s")
        else:
            print("No matches found.")
            
            # Offer AI help if available and not already tried
            if ai_available:
                ai_choice = input("Try AI-assisted search? (y/n): ").lower().strip()
                if ai_choice == 'y':
                    from ai_track_matcher import ai_assisted_search
                    print(f"\n{Fore.YELLOW}Requesting AI assistance...")
                    ai_match = ai_assisted_search(sp, search_artist or track.get('artist', ''), 
                                                 search_title or track.get('title', ''), 
                                                 search_album or track.get('album'))
                    if ai_match:
                        print(f"\n{Fore.GREEN}AI suggestion:")
                        print(f"Found: {', '.join(ai_match['artists'])} - {ai_match['name']}")
                        print(f"Album: {ai_match['album']} (Score: {ai_match['score']:.1f})")
                        if ai_match.get('ai_notes'):
                            print(f"{Fore.YELLOW}AI notes: {ai_match['ai_notes']}")
                        
                        confirm = input("\nAccept AI suggestion? (y/n): ").lower().strip()
                        if confirm == 'y':
                            return ai_match
                    else:
                        print(f"{Fore.RED}AI couldn't identify the track.")
            
            retry = input("Try again? (y/n): ").lower().strip()
            if retry != 'y':
                return None

def process_tracks_batch(sp, tracks_batch, confidence_threshold, batch_mode=False, auto_threshold=85, use_previous_decisions=False, use_ai_boost=False):
    """
    Process a batch of tracks efficiently with minimal user interaction.

    Args:
        sp: Spotify client
        tracks_batch: List of tracks to process
        confidence_threshold: Minimum score for manual review
        batch_mode: If True, auto-accept high confidence matches
        auto_threshold: Score threshold for auto-acceptance in batch mode
        use_previous_decisions: If True, use cached user decisions
        use_ai_boost: If True, use AI to boost medium-confidence matches (60-84 score)
    """
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

    results = []
    ai_boost_count = 0
    ai_boost_limit = 50  # Cost control: max AI requests per batch

    # Create progress bar for batch processing
    progress_bar = create_progress_bar(total=len(tracks_batch), desc="Searching tracks", unit="track")

    for track in tracks_batch:
        # Show current track being processed
        original_line = track.get('original_line', f"{track.get('artist', '')} - {track.get('title', '')}")
        progress_bar.set_description(f"Searching: {original_line[:50]}")

        # Check for cached decision first if using previous decisions
        if use_previous_decisions:
            cached_decision = get_cached_decision(track)
            if cached_decision:
                # Apply the cached decision
                if cached_decision['decision'] == 'y' and cached_decision.get('match'):
                    results.append({'track': track, 'match': cached_decision['match'], 'accepted': True, 'auto': False, 'cached': True})
                    update_progress_bar(progress_bar, 1)
                    continue
                elif cached_decision['decision'] == 'n':
                    results.append({'track': track, 'match': None, 'accepted': False, 'review': False, 'cached': True})
                    update_progress_bar(progress_bar, 1)
                    continue

        match = search_track_on_spotify(sp, track['artist'], track['title'], track['album'])

        if match:
            score = match.get('score', 0)

            # Check if AI boost should be used for medium-confidence matches
            # Skip medium-confidence if ai_only_for_no_match is enabled
            from preferences_manager import get_preference
            ai_only_for_no_match = get_preference("ai.ai_only_for_no_match", False)

            if use_ai_boost and batch_mode and 60 <= score < auto_threshold and ai_boost_count < ai_boost_limit and not ai_only_for_no_match:
                try:
                    progress_bar.set_description(f"AI boosting: {original_line[:45]}")
                    from ai_track_matcher import ai_assisted_search
                    ai_match = ai_assisted_search(sp, track['artist'], track['title'], track.get('album'), min_confidence=0.7)

                    if ai_match and ai_match.get('score', 0) >= auto_threshold:
                        # AI found a better match - auto-accept
                        ai_match['ai_assisted'] = True
                        results.append({'track': track, 'match': ai_match, 'accepted': True, 'auto': True, 'ai_assisted': True})
                        ai_boost_count += 1
                        logger.info(f"AI boosted match for '{original_line}': {ai_match.get('score', 0):.1f}")
                    elif score >= confidence_threshold:
                        # AI didn't help enough - keep for manual review
                        results.append({'track': track, 'match': match, 'accepted': False, 'review': True})
                    else:
                        # Still low confidence - skip
                        results.append({'track': track, 'match': match, 'accepted': False, 'review': False})
                except Exception as e:
                    logger.warning(f"AI assist failed for '{original_line}': {e}")
                    # Fall back to regular logic
                    if score >= confidence_threshold:
                        results.append({'track': track, 'match': match, 'accepted': False, 'review': True})
                    else:
                        results.append({'track': track, 'match': match, 'accepted': False, 'review': False})
            elif batch_mode and score >= auto_threshold:
                # High confidence - auto-accept without AI
                results.append({'track': track, 'match': match, 'accepted': True, 'auto': True})
            elif score >= confidence_threshold:
                # Medium/high confidence - needs review
                results.append({'track': track, 'match': match, 'accepted': False, 'review': True})
            else:
                # Low confidence - skip
                results.append({'track': track, 'match': match, 'accepted': False, 'review': False})
        else:
            # No match found - try AI as last resort if enabled
            if use_ai_boost and batch_mode and ai_boost_count < ai_boost_limit:
                try:
                    progress_bar.set_description(f"AI searching: {original_line[:45]}")
                    from ai_track_matcher import ai_assisted_search
                    ai_match = ai_assisted_search(sp, track['artist'], track['title'], track.get('album'), min_confidence=0.7)

                    if ai_match:
                        ai_match['ai_assisted'] = True
                        results.append({'track': track, 'match': ai_match, 'accepted': True, 'auto': True, 'ai_assisted': True})
                        ai_boost_count += 1
                        logger.info(f"AI found match for '{original_line}': {ai_match.get('score', 0):.1f}")
                    else:
                        results.append({'track': track, 'match': None, 'accepted': False, 'review': False})
                except Exception as e:
                    logger.warning(f"AI assist failed for '{original_line}': {e}")
                    results.append({'track': track, 'match': None, 'accepted': False, 'review': False})
            else:
                results.append({'track': track, 'match': None, 'accepted': False, 'review': False})

        update_progress_bar(progress_bar, 1)

    close_progress_bar(progress_bar)

    if ai_boost_count > 0:
        logger.info(f"AI assisted with {ai_boost_count} tracks in this batch")

    return results

def process_playlist_file(sp, file_path, user_id, confidence_threshold, min_score=50, batch_mode=False, auto_threshold=85, use_previous_decisions=False, use_ai_boost=False):
    """Process a single playlist file and convert it to a Spotify playlist."""
    logger.info(f"Processing playlist: {file_path}")
    
    # Extract playlist name from file name
    playlist_name = os.path.splitext(os.path.basename(file_path))[0]
    
    # Parse the playlist file
    tracks = parse_playlist_file(file_path)
    
    if not tracks:
        logger.warning(f"No tracks found in playlist: {file_path}")
        return 0, 0
    
    logger.info(f"Found {len(tracks)} tracks in playlist")

    # Search for tracks on Spotify
    # Note: Removed broken sync check that compared M3U hash to previous M3U hash
    # The de-duplication logic below (checking existing Spotify tracks) handles avoiding duplicates
    spotify_tracks = []
    skipped_tracks = []
    
    # Process tracks in batches for efficiency when in batch mode
    if batch_mode and len(tracks) > 10:
        logger.info(f"Processing {len(tracks)} tracks in batch mode...")
        batch_size = BATCH_SIZES['processing_batch']
        
        # Process in batches
        total_batches = (len(tracks) + batch_size - 1) // batch_size
        for i in range(0, len(tracks), batch_size):
            batch = tracks[i:i + batch_size]
            batch_num = i//batch_size + 1
            logger.info(f"🔍 Processing batch {batch_num}/{total_batches} ({len(batch)} tracks)")
            
            batch_results = process_tracks_batch(sp, batch, confidence_threshold, batch_mode, auto_threshold, use_previous_decisions, use_ai_boost)
            
            for result in batch_results:
                if result['accepted'] and result['match']:
                    spotify_tracks.append(result['match'])
                    if result.get('cached'):
                        track = result['track']
                        original_line = track.get('original_line', f"{track['artist']} - {track['title']}")
                        print(f"\n{Fore.GREEN}✅ Using cached decision for: {original_line}")
                elif result.get('review', False) and result['match']:
                    # Check for cached decision first
                    track = result['track']
                    match = result['match']
                    original_line = track.get('original_line', f"{track['artist']} - {track['title']}")
                    
                    # Check if we have a cached decision for this exact match
                    if use_previous_decisions:
                        cached_decision = get_cached_decision(track, match)
                        if cached_decision:
                            if cached_decision['decision'] == 'y':
                                print(f"\n{Fore.GREEN}✅ Using cached positive decision for: {original_line}")
                                spotify_tracks.append(match)
                                continue
                            elif cached_decision['decision'] == 'n':
                                print(f"\n{Fore.YELLOW}⏭️  Using cached negative decision for: {original_line}")
                                skipped_tracks.append(track)
                                continue
                    
                    print(f"\nManual Review Required:")
                    print(f"Original: {original_line}")

                    # Check if this is a remix fallback (original offered when remix not found)
                    if match.get('remix_fallback'):
                        print(f"{Fore.YELLOW}⚠️  Specific remix not found: {match.get('original_search_title', 'unknown')}")
                        print(f"{Fore.GREEN}✓ Found original version instead: {', '.join(match['artists'])} - {match['name']} (Score: {match['score']:.1f})")
                        choice = input("Accept original version? (y/n/s - y:yes, n:no, s:search manually): ").lower().strip()
                    else:
                        print(f"Match: {', '.join(match['artists'])} - {match['name']} (Score: {match['score']:.1f})")
                        choice = input("Accept this match? (y/n/s - y:yes, n:no, s:search manually): ").lower().strip()
                    if choice == 'y':
                        spotify_tracks.append(match)
                        save_user_decision(track, match, 'y')
                    elif choice == 's':
                        # Manual search option with continuous searching
                        manual_match = manual_search_flow(sp, track)
                        if manual_match:
                            spotify_tracks.append(manual_match)
                            save_user_decision(track, manual_match, 'y', manual_search_used=True)
                        else:
                            skipped_tracks.append(track)
                    else:
                        skipped_tracks.append(track)
                        save_user_decision(track, match, 'n')
                else:
                    skipped_tracks.append(result['track'])
                    if result.get('cached') and result['match'] is None:
                        track = result['track']
                        original_line = track.get('original_line', f"{track['artist']} - {track['title']}")
                        print(f"\n{Fore.YELLOW}⏭️  Skipping based on cached decision: {original_line}")
                    
            # Add delay between batches for rate limiting
            if i + batch_size < len(tracks):
                time.sleep(0.5)
                
    else:
        # Interactive mode or small playlist - process individually
        progress_desc = f"Searching {len(tracks)} tracks"
        pbar = create_progress_bar(total=len(tracks), desc=progress_desc, unit="track")
        for track in tracks:
            # Get the original line from the playlist file if available
            original_line = track.get('original_line', f"{track['artist']} - {track['title']}")
            
            # Log the extracted metadata
            logger.debug(f"Extracted metadata: Artist='{track['artist']}', Album='{track['album']}', Title='{track['title']}'")
            
            # Check for cached decision first if using previous decisions
            if use_previous_decisions:
                cached_decision = get_cached_decision(track)
                if cached_decision:
                    if cached_decision['decision'] == 'y' and cached_decision.get('match'):
                        print(f"\nUsing previous decision for: {original_line}")
                        print(f"Match: {', '.join(cached_decision['match']['artists'])} - {cached_decision['match']['name']} - PREVIOUSLY ACCEPTED")
                        spotify_tracks.append(cached_decision['match'])
                        continue
                    elif cached_decision['decision'] == 'n':
                        print(f"\nSkipping (previously rejected): {original_line}")
                        skipped_tracks.append(track)
                        continue
            
            # Search with all available metadata
            match = search_track_on_spotify(sp, track['artist'], track['title'], track['album'])
            
            if match:
                # Show the original line from the playlist file
                print(f"\nOriginal entry: {original_line}")
                print(f"Extracted as: {track['artist']} - {track['title']}")
                if track['album']:
                    print(f"Album: {track['album']}")
                print(f"Match: {', '.join(match['artists'])} - {match['name']} (from album: {match['album']}) (Score: {match['score']:.1f})")
            
                # Batch mode logic
                if batch_mode and match['score'] >= auto_threshold:
                    print(f"AUTO-ACCEPTED (score {match['score']:.1f} >= {auto_threshold})")
                    spotify_tracks.append(match)
                    # Save the auto-accept decision
                    save_user_decision(track, match, 'y')
                elif match['score'] >= confidence_threshold:
                    # High confidence match
                    if batch_mode:
                        # In batch mode, auto-accept high confidence matches above threshold
                        print(f"AUTO-ACCEPTED (high confidence: {match['score']:.1f})")
                        spotify_tracks.append(match)
                        # Save the auto-accept decision
                        save_user_decision(track, match, 'y')
                    else:
                        # Interactive mode - user confirmation required
                        options = "Accept this match? (y/n/s/t - y:yes, n:no, s:search manually, t:try again): "
                        
                        while True:
                            confirm = input(options).lower()
                            
                            if confirm == 'y':
                                spotify_tracks.append(match)
                                # Save the user's positive decision
                                save_user_decision(track, match, 'y')
                                break
                            elif confirm == 'n':
                                skipped_tracks.append(track)
                                # Save the user's negative decision
                                save_user_decision(track, match, 'n')
                                break
                            elif confirm == 's':
                                # Manual search option
                                search_query = input("Enter search query (artist - title): ")
                                if search_query:
                                    parts = search_query.split(" - ", 1)
                                    search_artist = parts[0].strip() if len(parts) > 1 else ""
                                    search_title = parts[1].strip() if len(parts) > 1 else search_query.strip()
                                    
                                    # Ask for album info
                                    search_album = input("Enter album name (optional): ").strip()
                                    
                                    # Perform the manual search
                                    manual_match = search_track_on_spotify(sp, search_artist, search_title, search_album if search_album else None)
                                    
                                    if manual_match:
                                        print(f"Found: {', '.join(manual_match['artists'])} - {manual_match['name']} (from album: {manual_match['album']}) (Score: {manual_match['score']:.1f})")
                                        manual_confirm = input("Accept this match? (y/n/s - y:yes, n:no, s:search again): ").lower()
                                        if manual_confirm == 'y':
                                            spotify_tracks.append(manual_match)
                                            # Save the user's decision for the manual match
                                            save_user_decision(track, manual_match, 'y', manual_search_used=True)
                                            break
                                        elif manual_confirm == 'n':
                                            skipped_tracks.append(track)
                                            # Don't save 'n' for manual searches as they might try different terms
                                            break
                                        # If 's', continue the loop to search again
                                    else:
                                        print("No matches found for your search query.")
                                        # Continue the loop to try again
                                else:
                                    # Empty search query, ask again
                                    continue
                            elif confirm == 't':
                                # Try again option - attempt a different search strategy
                                # Try with just the title if we were using artist before, or vice versa
                                if track['artist']:
                                    print("Trying with title only...")
                                    retry_match = search_track_on_spotify(sp, "", track['title'], track['album'])
                                else:
                                    # If we don't have artist info, try with partial title
                                    print("Trying with partial title...")
                                    base_title = re.sub(r'\([^\)]+\)|\[[^\]]+\]', '', track['title']).strip()
                                    retry_match = search_track_on_spotify(sp, track['artist'], base_title, track['album'])
                                
                                if retry_match:
                                    print(f"New match: {', '.join(retry_match['artists'])} - {retry_match['name']} (from album: {retry_match['album']}) (Score: {retry_match['score']:.1f})")
                                    retry_confirm = input("Accept this match? (y/n/s - y:yes, n:no, s:search manually): ").lower()
                                    if retry_confirm == 'y':
                                        spotify_tracks.append(retry_match)
                                        break
                                    elif retry_confirm == 'n':
                                        skipped_tracks.append(track)
                                        break
                                    elif retry_confirm == 's':
                                        # Go back to manual search option
                                        continue
                                else:
                                    print("No alternative matches found.")
                                    skip_confirm = input("Skip this track? (y/n/s - y:yes, n:try again, s:search manually): ").lower()
                                    if skip_confirm == 'y':
                                        skipped_tracks.append(track)
                                        break
                                # Otherwise continue the loop to try again
                            else:
                                print("Invalid option. Please try again.")
            else:
                print(f"\nNo match found for: {original_line}")
                options = "Would you like to search manually? (y/n): "
                confirm = input(options).lower()
                
                if confirm == 'y':
                    # Manual search loop
                    while True:
                        search_query = input("Enter search query (artist - title): ")
                        if search_query:
                            parts = search_query.split(" - ", 1)
                            search_artist = parts[0].strip() if len(parts) > 1 else ""
                            search_title = parts[1].strip() if len(parts) > 1 else search_query.strip()
                            
                            # Ask for album info
                            search_album = input("Enter album name (optional): ").strip()
                            
                            # Perform the manual search
                            manual_match = search_track_on_spotify(sp, search_artist, search_title, search_album if search_album else None)
                            
                            if manual_match:
                                print(f"Found: {', '.join(manual_match['artists'])} - {manual_match['name']} (from album: {manual_match['album']}) (Score: {manual_match['score']:.1f})")
                                manual_confirm = input("Accept this match? (y/n/s - y:yes, n:no, s:search again): ").lower()
                                if manual_confirm == 'y':
                                    spotify_tracks.append(manual_match)
                                    break  # Exit manual search loop
                                elif manual_confirm == 'n':
                                    skipped_tracks.append(track)
                                    break  # Exit manual search loop
                                elif manual_confirm == 's':
                                    # Continue the manual search loop to search again
                                    continue
                                else:
                                    print("Invalid option. Please enter y, n, or s.")
                                    continue
                            else:
                                print("No matches found for your search query.")
                                retry_search = input("Try a different search? (y/n): ").lower()
                                if retry_search != 'y':
                                    skipped_tracks.append(track)
                                    break
                        else:
                            # Empty search query
                            retry_search = input("Empty search query. Try again? (y/n): ").lower()
                            if retry_search != 'y':
                                skipped_tracks.append(track)
                                break
                else:
                    skipped_tracks.append(track)

            # Update progress bar after processing each track
            update_progress_bar(pbar, 1)

        # Close progress bar after loop
        close_progress_bar(pbar)

    if not spotify_tracks:
        logger.warning("No tracks could be matched on Spotify. Playlist will not be created.")
        return 0, len(tracks)
    
    # Create or update Spotify playlist
    track_uris = [track['uri'] for track in spotify_tracks]
    playlist_id, tracks_added = create_or_update_spotify_playlist(sp, playlist_name, track_uris, user_id)
    
    # Summary
    logger.info(f"Playlist '{playlist_name}' processed:")
    logger.info(f"  - Total tracks in local playlist: {len(tracks)}")
    logger.info(f"  - Tracks matched on Spotify: {len(spotify_tracks)}")
    logger.info(f"  - Tracks added to Spotify playlist: {tracks_added}")
    logger.info(f"  - Tracks skipped: {len(skipped_tracks)}")
    
    if skipped_tracks:
        logger.info("Skipped tracks:")
        for track in skipped_tracks:
            logger.info(f"  - {track['artist']} - {track['title']}")

    # Note: Sync state tracking removed - playlists are now fully processed each run
    # De-duplication logic prevents adding duplicate tracks to Spotify playlists

    return len(spotify_tracks), len(skipped_tracks)

def view_all_text_files_paginated(files, page_size=20):
    """View all text files with pagination."""
    total_files = len(files)
    total_pages = (total_files + page_size - 1) // page_size
    current_page = 0
    
    while True:
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, total_files)
        
        print(f"\n{Fore.CYAN}Page {current_page + 1}/{total_pages} (showing files {start_idx + 1}-{end_idx} of {total_files}):")
        print(f"{Fore.CYAN}{'-' * 60}")
        
        for i in range(start_idx, end_idx):
            # Show relative path from current directory for readability
            try:
                rel_path = os.path.relpath(files[i])
            except:
                rel_path = files[i]
            print(f"{i + 1:3d}. {rel_path}")
        
        print(f"{Fore.CYAN}{'-' * 60}")
        
        # Navigation options
        options = []
        if current_page > 0:
            options.append("p=previous")
        if current_page < total_pages - 1:
            options.append("n=next")
        options.append("q=quit")
        
        nav = input(f"\n{Fore.CYAN}Navigation ({', '.join(options)}): ").lower().strip()
        
        if nav == 'p' and current_page > 0:
            current_page -= 1
        elif nav == 'n' and current_page < total_pages - 1:
            current_page += 1
        elif nav == 'q':
            break

def select_specific_text_files(files):
    """Allow user to select specific files from the list."""
    print(f"\n{Fore.CYAN}Select files to include:")
    print(f"{Fore.WHITE}Enter file numbers separated by commas (e.g., 1,3,5-10,15)")
    print(f"{Fore.WHITE}Or 'view' to see all files with pagination")
    
    # Show first 20 files
    for i, file_path in enumerate(files[:20], 1):
        try:
            rel_path = os.path.relpath(file_path)
        except:
            rel_path = file_path
        print(f"{i:3d}. {rel_path}")
    
    if len(files) > 20:
        print(f"\n{Fore.YELLOW}... and {len(files) - 20} more files")
        print(f"{Fore.YELLOW}Type 'view' to see all files")
    
    while True:
        selection = input(f"\n{Fore.CYAN}Enter selection: ").strip()
        
        if selection.lower() == 'view':
            view_all_text_files_paginated(files)
            continue
        
        if not selection:
            return []
        
        try:
            selected_indices = parse_number_ranges(selection, len(files))
            selected_files = [files[i-1] for i in selected_indices if 1 <= i <= len(files)]
            
            print(f"\n{Fore.GREEN}Selected {len(selected_files)} files:")
            for f in selected_files[:5]:
                print(f"  • {os.path.basename(f)}")
            if len(selected_files) > 5:
                print(f"  ... and {len(selected_files) - 5} more")
            
            confirm = input(f"\n{Fore.CYAN}Confirm selection? (y/n): ").lower().strip()
            if confirm == 'y':
                return selected_files
            
        except ValueError as e:
            print(f"{Fore.RED}Invalid selection: {e}")

def parse_number_ranges(selection, max_value):
    """Parse comma-separated numbers and ranges like '1,3,5-10,15'."""
    indices = set()
    
    for part in selection.split(','):
        part = part.strip()
        if not part:
            continue
            
        if '-' in part:
            # Range
            try:
                start, end = part.split('-', 1)
                start = int(start.strip())
                end = int(end.strip())
                
                if start < 1 or end > max_value or start > end:
                    raise ValueError(f"Invalid range: {part}")
                
                indices.update(range(start, end + 1))
            except ValueError:
                raise ValueError(f"Invalid range format: {part}")
        else:
            # Single number
            try:
                num = int(part)
                if num < 1 or num > max_value:
                    raise ValueError(f"Number out of range: {num}")
                indices.add(num)
            except ValueError:
                raise ValueError(f"Invalid number: {part}")
    
    return sorted(indices)

def find_playlist_files(directory, include_text_files=True):
    """Find all playlist files in the given directory and its subdirectories."""
    playlist_files = []
    
    # First get standard playlist files
    for ext in SUPPORTED_EXTENSIONS:
        pattern = os.path.join(directory, f"**/*{ext}")
        playlist_files.extend(glob.glob(pattern, recursive=True))
    
    if include_text_files:
        # Also check for text files that might be playlists
        all_files = glob.glob(os.path.join(directory, "**/*"), recursive=True)
        
        # Extensions to skip
        skip_extensions = {
            '.py', '.pyc', '.pyo', '.js', '.json', '.xml', '.yaml', '.yml',
            '.jpg', '.jpeg', '.png', '.gif', '.mp3', '.mp4', '.wav', '.flac',
            '.exe', '.dll', '.so', '.dylib', '.zip', '.tar', '.gz',
            '.pdf', '.doc', '.docx', '.db', '.log', '.bak', '.tmp'
        }
        
        potential_text_playlists = []
        for file_path in all_files:
            if os.path.isfile(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                basename = os.path.basename(file_path)
                
                # Skip if already in playlist files
                if file_path in playlist_files:
                    continue
                    
                # Skip known non-playlist extensions
                if ext in skip_extensions:
                    continue
                    
                # Skip hidden files
                if basename.startswith('.'):
                    continue
                    
                # Skip files in certain directories
                if any(part in file_path.split(os.sep) for part in ['.git', '__pycache__', 'node_modules', '.venv', 'venv']):
                    continue
                
                # Check if it could be a text playlist
                if is_text_playlist_file(file_path):
                    potential_text_playlists.append(file_path)
        
        if potential_text_playlists:
            print(f"\n{Fore.YELLOW}Found {len(potential_text_playlists)} potential text playlist files:")
            
            # Show options
            print(f"\n{Fore.CYAN}Options:")
            print(f"1. Include all text files")
            print(f"2. Select specific files") 
            print(f"3. View all files (paginated)")
            print(f"4. Skip all text files")
            
            choice = input(f"\n{Fore.CYAN}Enter your choice (1-4): ").strip()
            
            if choice == '1':
                # Include all
                playlist_files.extend(potential_text_playlists)
                print(f"{Fore.GREEN}✅ Added all {len(potential_text_playlists)} text files")
                
            elif choice == '2':
                # Select specific files
                selected_files = select_specific_text_files(potential_text_playlists)
                if selected_files:
                    playlist_files.extend(selected_files)
                    print(f"{Fore.GREEN}✅ Added {len(selected_files)} selected text files")
                    
            elif choice == '3':
                # View all with pagination, then decide
                view_all_text_files_paginated(potential_text_playlists)
                
                # After viewing, ask again
                print(f"\n{Fore.CYAN}After viewing all files:")
                print(f"1. Include all text files")
                print(f"2. Select specific files")
                print(f"3. Skip all text files")
                
                view_choice = input(f"\n{Fore.CYAN}Enter your choice (1-3): ").strip()
                
                if view_choice == '1':
                    playlist_files.extend(potential_text_playlists)
                    print(f"{Fore.GREEN}✅ Added all {len(potential_text_playlists)} text files")
                elif view_choice == '2':
                    selected_files = select_specific_text_files(potential_text_playlists)
                    if selected_files:
                        playlist_files.extend(selected_files)
                        print(f"{Fore.GREEN}✅ Added {len(selected_files)} selected text files")
                        
            # choice '4' or any other choice skips the text files
    
    return playlist_files

def clear_processed_playlist_cache():
    """Clear all processed playlist cache entries for the converter."""
    from cache_utils import list_caches, clear_cache
    
    caches = list_caches()
    converter_caches = [c for c in caches if c['name'].startswith('user_decision_') or 
                       c['name'].startswith('playlist_processed_')]
    
    if not converter_caches:
        print(f"{Fore.YELLOW}No converter cache entries found.")
        return
    
    print(f"{Fore.CYAN}Found {len(converter_caches)} converter cache entries.")
    for cache in converter_caches:
        clear_cache(cache['name'])
    print(f"{Fore.GREEN}✅ Cleared {len(converter_caches)} converter cache entries.")

def process_playlists_parallel(sp, playlist_files, user_id, auto_threshold=85, use_ai_boost=False, max_workers=3):
    """Process multiple playlists in parallel for auto mode."""
    results = []

    def process_single_playlist(file_path):
        """Helper to process a single playlist."""
        try:
            return process_playlist_file_auto_mode(sp, file_path, user_id, auto_threshold, use_ai_boost)
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return (0, 0, 0)
    
    # Use ThreadPoolExecutor for parallel processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {executor.submit(process_single_playlist, f): f for f in playlist_files}

        # Process completed tasks with progress bar
        pbar = create_progress_bar(total=len(playlist_files), desc="Processing playlists", unit="playlist")
        for future in concurrent.futures.as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                result = future.result()
                results.append((file_path, result))
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                results.append((file_path, (0, 0, 0)))

            update_progress_bar(pbar, 1)

        close_progress_bar(pbar)
    
    return results

def process_playlist_file_auto_mode(sp, file_path, user_id, auto_threshold=85, use_ai_boost=False):
    """Process a playlist file in fully autonomous mode - no user interaction."""
    logger.info(f"[AUTO] Processing playlist: {file_path}")

    # Extract playlist name from file name
    playlist_name = os.path.splitext(os.path.basename(file_path))[0]

    # Parse the playlist file
    tracks = parse_playlist_file(file_path)

    if not tracks:
        logger.warning(f"[AUTO] No tracks found in playlist: {file_path}")
        return 0, 0, 0

    logger.info(f"[AUTO] Found {len(tracks)} tracks in playlist '{playlist_name}'")

    # Search for tracks on Spotify with learning patterns
    spotify_tracks = []
    skipped_tracks = []
    ai_boost_count = 0
    ai_boost_limit = 50  # Cost control

    for track in tracks:
        # Apply learning patterns first
        learned_artist, learned_title = apply_learning_patterns(track['artist'], track['title'])

        # Search with learned patterns
        match = search_track_on_spotify(sp, learned_artist, learned_title, track.get('album'))

        # If no match with learned patterns, try original
        if not match and (learned_artist != track['artist'] or learned_title != track['title']):
            match = search_track_on_spotify(sp, track['artist'], track['title'], track.get('album'))

        score = match.get('score', 0) if match else 0

        # Try AI boost for medium-confidence matches or no matches
        # Check preference to see if AI should only run for no-match cases
        from preferences_manager import get_preference
        ai_only_for_no_match = get_preference("ai.ai_only_for_no_match", False)

        if use_ai_boost and ai_boost_count < ai_boost_limit:
            # Use AI if: no match found, OR (match exists with medium score AND not restricted to no-match only)
            should_use_ai = not match or (match and 60 <= score < auto_threshold and not ai_only_for_no_match)
            if should_use_ai:
                try:
                    from ai_track_matcher import ai_assisted_search
                    ai_match = ai_assisted_search(sp, track['artist'], track['title'], track.get('album'), min_confidence=0.7)

                    if ai_match and ai_match.get('score', 0) >= auto_threshold:
                        ai_match['ai_assisted'] = True
                        spotify_tracks.append(ai_match)
                        save_user_decision(track, ai_match, 'y')
                        ai_boost_count += 1
                        logger.info(f"[AUTO] AI boosted: {track['artist']} - {track['title']} (score: {ai_match.get('score', 0):.1f})")
                    elif match and score >= auto_threshold:
                        # Original match is good enough
                        spotify_tracks.append(match)
                        save_user_decision(track, match, 'y')
                    else:
                        skipped_tracks.append(track)
                except Exception as e:
                    logger.warning(f"[AUTO] AI boost failed: {e}")
                    # Fall back to original match if good enough
                    if match and score >= auto_threshold:
                        spotify_tracks.append(match)
                        save_user_decision(track, match, 'y')
                    else:
                        skipped_tracks.append(track)
            elif match and score >= auto_threshold:
                # High confidence match - no AI needed
                spotify_tracks.append(match)
                save_user_decision(track, match, 'y')
            else:
                skipped_tracks.append(track)
        elif match and score >= auto_threshold:
            # AI boost not enabled - use threshold only
            spotify_tracks.append(match)
            save_user_decision(track, match, 'y')
        else:
            skipped_tracks.append(track)

    if ai_boost_count > 0:
        logger.info(f"[AUTO] AI assisted with {ai_boost_count} tracks in this playlist")
    
    if not spotify_tracks:
        logger.warning(f"[AUTO] No tracks matched above threshold {auto_threshold}. Skipping playlist.")
        return 0, 0, len(tracks)
    
    # Create or update Spotify playlist WITHOUT user interaction
    track_uris = [track['uri'] for track in spotify_tracks]
    
    # Get user playlists to check for existing ones
    user_playlists = get_user_playlists(sp, user_id)
    
    # Find exact match only (no similar name prompting in auto mode)
    existing_playlist = None
    for playlist in user_playlists:
        if playlist['name'] == playlist_name:
            existing_playlist = playlist
            break
    
    if existing_playlist:
        # Update existing playlist
        playlist_id = existing_playlist['id']
        existing_tracks = get_playlist_tracks(sp, playlist_id)
        tracks_to_add = [uri for uri in track_uris if uri not in existing_tracks]
        
        if tracks_to_add:
            # Add tracks in batches
            for i in range(0, len(tracks_to_add), 100):
                batch = tracks_to_add[i:i+100]
                sp.playlist_add_items(playlist_id, batch)
            logger.info(f"[AUTO] ✅ Added {len(tracks_to_add)} new tracks to existing playlist '{playlist_name}'")
        else:
            logger.info(f"[AUTO] ✅ Playlist '{playlist_name}' already up to date")
        
        return len(spotify_tracks), len(skipped_tracks), len(tracks_to_add)
    else:
        # Create new playlist
        playlist = sp.user_playlist_create(
            user=user_id,
            name=playlist_name,
            public=False,
            description=f"Auto-created from {os.path.basename(file_path)}"
        )
        
        # Add tracks in batches
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]
            sp.playlist_add_items(playlist['id'], batch)
        
        logger.info(f"[AUTO] ✅ Created new playlist '{playlist_name}' with {len(track_uris)} tracks")
        return len(spotify_tracks), len(skipped_tracks), len(track_uris)

def auto_create_or_update_playlist(sp, playlist_name, track_uris, user_id):
    """Create or update playlist in auto mode without user prompts."""
    # Get user playlists
    user_playlists = get_user_playlists(sp, user_id)
    
    # Clean the playlist name - remove common file extensions
    clean_name = playlist_name
    for ext in ['.m3u', '.m3u8', '.pls', '.txt']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break
    
    # Find exact match or suffix match - prefer the one with most tracks
    existing_playlist = None
    suffix_playlists = []
    
    for playlist in user_playlists:
        if playlist['name'] == playlist_name:
            existing_playlist = playlist
            break
        elif playlist['name'] == clean_name or playlist['name'].startswith(clean_name + '.'):
            suffix_playlists.append(playlist)
    
    # If no exact match but found suffix matches, use the one with most tracks
    if not existing_playlist and suffix_playlists:
        suffix_playlists.sort(key=lambda p: p['tracks']['total'], reverse=True)
        existing_playlist = suffix_playlists[0]
        logger.info(f"[AUTO] Using existing playlist '{existing_playlist['name']}' instead of creating '{playlist_name}'")
    
    if existing_playlist:
        # Update existing playlist
        playlist_id = existing_playlist['id']
        existing_tracks = get_playlist_tracks(sp, playlist_id)
        tracks_to_add = [uri for uri in track_uris if uri not in existing_tracks]
        
        if tracks_to_add:
            # Add tracks in batches
            for i in range(0, len(tracks_to_add), 100):
                batch = tracks_to_add[i:i+100]
                sp.playlist_add_items(playlist_id, batch)
            
            # Update cache
            cache_key = f"playlist_tracks_{playlist_id}"
            save_to_cache(existing_tracks + tracks_to_add, cache_key)
            
            return len(tracks_to_add)
        return 0
    else:
        # Create new playlist
        playlist = sp.user_playlist_create(
            user=user_id,
            name=playlist_name,
            public=False,
            description=f"Auto-created by Spotify Playlist Converter"
        )
        
        # Add tracks in batches
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]
            sp.playlist_add_items(playlist['id'], batch)
        
        # Update caches
        cache_key = f"user_playlists_{user_id}"
        current_playlists = get_user_playlists(sp, user_id)
        current_playlists.append(playlist)
        save_to_cache(current_playlists, cache_key)
        
        cache_key = f"playlist_tracks_{playlist['id']}"
        save_to_cache(track_uris, cache_key)
        
        return len(track_uris)

def find_missing_tracks_in_playlists(sp, file_path, user_id, suggest_threshold=70):
    """Find tracks missing from Spotify playlists and suggest additions."""
    playlist_name = os.path.splitext(os.path.basename(file_path))[0]
    
    # Parse local playlist
    local_tracks = parse_playlist_file(file_path)
    if not local_tracks:
        return
    
    # Find matching Spotify playlist
    user_playlists = get_user_playlists(sp, user_id)
    spotify_playlist = None
    
    for playlist in user_playlists:
        if playlist['name'] == playlist_name:
            spotify_playlist = playlist
            break
    
    if not spotify_playlist:
        print(f"\n{Fore.YELLOW}No Spotify playlist found matching: {playlist_name}")
        print(f"Local playlist has {len(local_tracks)} tracks that could be added.")
        return
    
    # Get existing tracks in Spotify playlist
    existing_track_uris = get_playlist_tracks(sp, spotify_playlist['id'])
    existing_track_ids = set(uri.split(':')[-1] for uri in existing_track_uris)
    
    print(f"\n{Fore.CYAN}Analyzing playlist: {playlist_name}")
    print(f"Local tracks: {len(local_tracks)}, Spotify tracks: {len(existing_track_uris)}")
    
    # Find missing tracks
    missing_tracks = []
    low_confidence_tracks = []
    
    for track in local_tracks:
        match = search_track_on_spotify(sp, track['artist'], track['title'], track.get('album'))
        
        if match:
            if match['id'] not in existing_track_ids:
                if match['score'] >= suggest_threshold:
                    missing_tracks.append((track, match))
                else:
                    low_confidence_tracks.append((track, match))
    
    if missing_tracks:
        print(f"\n{Fore.GREEN}Found {len(missing_tracks)} missing tracks with confidence >= {suggest_threshold}:")
        for i, (local, match) in enumerate(missing_tracks[:10], 1):
            artists = ', '.join(match['artists'])
            print(f"{i}. {artists} - {match['name']} (Score: {match['score']:.1f})")
        if len(missing_tracks) > 10:
            print(f"... and {len(missing_tracks) - 10} more")
        
        add_all = input(f"\n{Fore.CYAN}Add all {len(missing_tracks)} missing tracks? (y/n): ").lower().strip()
        if add_all == 'y':
            track_uris = [match['uri'] for _, match in missing_tracks]
            for i in range(0, len(track_uris), 100):
                batch = track_uris[i:i+100]
                sp.playlist_add_items(spotify_playlist['id'], batch)
            print(f"{Fore.GREEN}✅ Added {len(track_uris)} tracks to playlist")
    else:
        print(f"{Fore.GREEN}✅ No missing tracks found above threshold {suggest_threshold}")
    
    if low_confidence_tracks:
        print(f"\n{Fore.YELLOW}Found {len(low_confidence_tracks)} potential matches below threshold:")
        review = input("Review low confidence matches? (y/n): ").lower().strip()
        if review == 'y':
            added_count = 0
            for local, match in low_confidence_tracks:
                artists = ', '.join(match['artists'])
                print(f"\nLocal: {local['artist']} - {local['title']}")
                print(f"Match: {artists} - {match['name']} (Score: {match['score']:.1f})")
                add = input("Add this track? (y/n): ").lower().strip()
                if add == 'y':
                    sp.playlist_add_items(spotify_playlist['id'], [match['uri']])
                    added_count += 1
            if added_count > 0:
                print(f"{Fore.GREEN}✅ Added {added_count} additional tracks")

def replace_karaoke_in_playlists(sp, user_id):
    """
    Scan user's playlists for karaoke tracks and replace with real versions.

    Args:
        sp: Authenticated Spotify client
        user_id: User ID
    """
    from spotify_utils import is_karaoke_track

    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}KARAOKE REPLACEMENT MODE")
    print(f"{Fore.CYAN}{'='*60}")
    print(f"{Fore.WHITE}Scanning playlists for karaoke/backing track versions...")
    print(f"{Fore.CYAN}{'='*60}\n")

    # Get all user playlists
    user_playlists = get_user_playlists(sp, user_id)

    total_playlists_scanned = 0
    total_karaoke_found = 0
    total_karaoke_replaced = 0

    for playlist in user_playlists:
        playlist_name = playlist['name']
        playlist_id = playlist['id']

        # Get all tracks in the playlist
        tracks = get_playlist_tracks_with_details(sp, playlist_id)

        if not tracks:
            continue

        total_playlists_scanned += 1

        # Find karaoke tracks
        karaoke_tracks = []
        for track_uri, track in tracks.items():
            track_name = track.get('name', '')
            artists = track.get('artists', [])
            artist_name = ', '.join([a['name'] for a in artists]) if artists else ''
            album = track.get('album', {})
            album_name = album.get('name', '') if album else ''

            if is_karaoke_track(track_name, artist_name, album_name):
                karaoke_tracks.append({
                    'uri': track_uri,
                    'name': track_name,
                    'artist': artist_name,
                    'album': album_name,
                    'id': track.get('id', '')
                })

        if karaoke_tracks:
            total_karaoke_found += len(karaoke_tracks)
            print(f"\n{Fore.YELLOW}Found {len(karaoke_tracks)} karaoke track(s) in '{playlist_name}':")

            for karaoke in karaoke_tracks:
                print(f"  • {karaoke['artist']} - {karaoke['name']} (from: {karaoke['album']})")

                # Try to find the real version
                # Extract clean artist and title (removing karaoke indicators)
                clean_title = karaoke['name']
                clean_artist = karaoke['artist']

                # Search for the real version
                match = search_track_on_spotify(sp, clean_artist, clean_title)

                if match and match.get('score', 0) >= 70:
                    # Verify it's not also karaoke
                    match_artists = ', '.join(match.get('artists', []))
                    match_album = match.get('album', '')

                    if not is_karaoke_track(match['name'], match_artists, match_album):
                        print(f"    {Fore.GREEN}✓ Found real version: {match_artists} - {match['name']} (from: {match_album})")

                        # Ask user for confirmation
                        replace = input(f"    Replace karaoke with real version? (y/n): ").strip().lower()

                        if replace == 'y':
                            try:
                                # Remove karaoke track
                                sp.playlist_remove_all_occurrences_of_items(playlist_id, [karaoke['uri']])
                                # Add real version
                                sp.playlist_add_items(playlist_id, [match['uri']])
                                print(f"    {Fore.GREEN}✅ Replaced successfully!")
                                total_karaoke_replaced += 1
                            except Exception as e:
                                print(f"    {Fore.RED}❌ Error replacing track: {e}")
                        else:
                            print(f"    {Fore.YELLOW}Skipped")
                    else:
                        print(f"    {Fore.YELLOW}⚠ Match is also karaoke, skipping")
                else:
                    print(f"    {Fore.RED}✗ Could not find real version")

    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}KARAOKE REPLACEMENT SUMMARY")
    print(f"{Fore.CYAN}{'='*60}")
    print(f"{Fore.WHITE}Playlists scanned: {total_playlists_scanned}")
    print(f"{Fore.YELLOW}Karaoke tracks found: {total_karaoke_found}")
    print(f"{Fore.GREEN}Karaoke tracks replaced: {total_karaoke_replaced}")
    print(f"{Fore.CYAN}{'='*60}\n")

def main():
    """Main function to run the script."""
    global DUPLICATE_CONFIG
    
    parser = argparse.ArgumentParser(description="Convert local playlist files to Spotify playlists")
    parser.add_argument("directory", nargs="?", default=".", help="Directory to search for playlist files (default: current directory)")
    parser.add_argument("--threshold", type=int, default=CONFIDENCE_THRESHOLD, help=f"Confidence threshold for automatic matching (default: {CONFIDENCE_THRESHOLD})")
    parser.add_argument("--min-score", type=int, default=50, help="Minimum score to show recommendations (default: 50)")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching (always fetch fresh data)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--batch", action="store_true", help="Batch mode: auto-accept high confidence matches")
    parser.add_argument("--auto-threshold", type=int, default=85, help="Auto-accept threshold for batch mode (default: 85)")
    parser.add_argument("--use-ai-boost", action="store_true",
                        help="Enable AI-assisted matching: Uses AI models (Claude/Gemini/GPT-4) to help identify "
                             "tracks with medium confidence (60-84 score) or when regular search fails. "
                             "Improves accuracy but may incur API costs. Max 50 AI requests per batch.")
    parser.add_argument("--max-playlists", type=int, help="Maximum number of playlists to process")
    
    # New mode arguments
    parser.add_argument("--auto-mode", action="store_true", help="Fully autonomous mode - no user interaction")
    parser.add_argument("--missing-tracks-mode", action="store_true", help="Find and suggest missing tracks in playlists")
    parser.add_argument("--suggest-threshold", type=int, default=70, help="Threshold for suggesting missing tracks (default: 70)")
    parser.add_argument("--clear-cache", action="store_true", help="Clear processed playlist cache")
    parser.add_argument("--auto-remove-duplicates", action="store_true", help="Automatically remove duplicate tracks from playlists")
    parser.add_argument("--keep-duplicates", action="store_true", help="Keep all duplicate tracks (don't remove any)")
    parser.add_argument("--ask-duplicates", action="store_true", help="Ask for each playlist whether to remove duplicates")
    parser.add_argument("--replace-karaoke", action="store_true", help="Scan playlists for karaoke versions and replace with real versions")

    args = parser.parse_args()
    
    # Set up logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Handle cache clearing
    if args.clear_cache:
        clear_processed_playlist_cache()
        return
    
    # Set minimum score
    min_score = args.min_score
    
    # Resolve directory path
    directory = os.path.abspath(args.directory)
    
    if not os.path.isdir(directory):
        logger.error(f"Directory not found: {directory}")
        sys.exit(1)
    
    # Find playlist files
    logger.info(f"Searching for playlist files in: {directory}")
    # In auto-mode, include text files automatically without prompting
    playlist_files = find_playlist_files(directory, include_text_files=True)
    
    if not playlist_files:
        logger.info(f"No playlist files found in {directory}")
        sys.exit(0)
    
    logger.info(f"Found {len(playlist_files)} playlist files")
    
    # Limit number of playlists if specified
    if args.max_playlists:
        playlist_files = playlist_files[:args.max_playlists]
        logger.info(f"Limited to {len(playlist_files)} playlists")
    
    # Authenticate with Spotify
    logger.info("Authenticating with Spotify...")
    sp = authenticate_spotify()
    
    if not sp:
        logger.error("Failed to authenticate with Spotify")
        sys.exit(1)
    
    # Get user ID
    user_info = sp.current_user()
    user_id = user_info['id']
    
    # Handle different modes
    if args.auto_mode:
        # Fully autonomous mode
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.CYAN}AUTO-SYNC MODE - FULLY AUTONOMOUS")
        print(f"{Fore.CYAN}{'='*60}")
        print(f"{Fore.WHITE}• Will auto-add tracks with confidence >= {args.auto_threshold}")
        print(f"{Fore.WHITE}• Will create missing playlists automatically")
        print(f"{Fore.WHITE}• Will update existing playlists without duplicates")
        print(f"{Fore.WHITE}• Will apply learned matching patterns")
        if args.use_ai_boost:
            print(f"{Fore.GREEN}• 🤖 AI Boost ENABLED:")
            print(f"{Fore.GREEN}  - Uses AI models to identify hard-to-find tracks")
            print(f"{Fore.GREEN}  - Activates for scores 60-{args.auto_threshold} or when no match found")
            print(f"{Fore.GREEN}  - Limit: 50 AI requests per batch to control costs")
        print(f"{Fore.WHITE}• No user interaction required")
        print(f"{Fore.CYAN}{'='*60}\n")
        
        # Use batch processing for efficiency if many playlists
        if len(playlist_files) > 10:
            print(f"{Fore.CYAN}Using batch processing for {len(playlist_files)} playlists...")
            
            # Collect all unique tracks first
            all_tracks = []
            playlist_tracks_map = defaultdict(list)
            
            for file_path in playlist_files:
                tracks = parse_playlist_file(file_path)
                if tracks:
                    for track in tracks:
                        track['source_playlist'] = file_path
                        all_tracks.append(track)
                        playlist_tracks_map[file_path].append(track)
            
            # Deduplicate tracks
            unique_tracks = {}
            for track in all_tracks:
                key = f"{track.get('artist', '').lower()}||{track.get('title', '').lower()}"
                if key not in unique_tracks:
                    unique_tracks[key] = track
            
            print(f"{Fore.WHITE}Found {len(unique_tracks)} unique tracks across all playlists")
            
            # Search all unique tracks with progress bar
            track_matches = {}
            ai_boost_count = 0
            ai_boost_limit = 50  # Cost control
            search_desc = f"🎵 Searching {len(unique_tracks)} unique tracks across all playlists"
            with create_progress_bar(total=len(unique_tracks), desc=search_desc, unit="track") as pbar:
                for key, track in unique_tracks.items():
                    # Apply learning patterns
                    learned_artist, learned_title = apply_learning_patterns(track['artist'], track['title'])

                    match = search_track_on_spotify(sp, learned_artist, learned_title, track.get('album'))
                    if not match and (learned_artist != track['artist'] or learned_title != track['title']):
                        match = search_track_on_spotify(sp, track['artist'], track['title'], track.get('album'))

                    score = match.get('score', 0) if match else 0

                    # Try AI boost for medium-confidence matches or no matches
                    # Check preference to see if AI should only run for no-match cases
                    from preferences_manager import get_preference
                    ai_only_for_no_match = get_preference("ai.ai_only_for_no_match", False)

                    if args.use_ai_boost and ai_boost_count < ai_boost_limit:
                        # Use AI if: no match found, OR (match exists with medium score AND not restricted to no-match only)
                        should_use_ai = not match or (match and 60 <= score < args.auto_threshold and not ai_only_for_no_match)
                        if should_use_ai:
                            try:
                                update_progress_bar(pbar, 0, f"🤖 AI boosting: {track['artist'][:30]} - {track['title'][:30]}")
                                from ai_track_matcher import ai_assisted_search
                                ai_match = ai_assisted_search(sp, track['artist'], track['title'], track.get('album'), min_confidence=0.7)

                                if ai_match and ai_match.get('score', 0) >= args.auto_threshold:
                                    ai_match['ai_assisted'] = True
                                    track_matches[key] = ai_match
                                    save_user_decision(track, ai_match, 'y')
                                    ai_boost_count += 1
                                    logger.info(f"[AUTO] AI boosted: {track['artist']} - {track['title']} (score: {ai_match.get('score', 0):.1f})")
                                elif match and score >= args.auto_threshold:
                                    # Original match is good enough
                                    track_matches[key] = match
                                    save_user_decision(track, match, 'y')
                            except Exception as e:
                                logger.warning(f"[AUTO] AI boost failed: {e}")
                                # Fall back to original match if good enough
                                if match and score >= args.auto_threshold:
                                    track_matches[key] = match
                                    save_user_decision(track, match, 'y')
                        elif match and score >= args.auto_threshold:
                            # High confidence match - no AI needed
                            track_matches[key] = match
                            save_user_decision(track, match, 'y')
                    elif match and score >= args.auto_threshold:
                        # AI boost not enabled - use threshold only
                        track_matches[key] = match
                        save_user_decision(track, match, 'y')

                    update_progress_bar(pbar, 1)
                    time.sleep(0.05)  # Rate limiting

            if ai_boost_count > 0:
                print(f"{Fore.GREEN}🤖 AI assisted with {ai_boost_count} tracks")
            
            # Process each playlist with the matches
            total_processed = 0
            total_matches = 0
            total_skipped = 0
            total_added = 0
            
            for file_path in playlist_files:
                playlist_name = os.path.splitext(os.path.basename(file_path))[0]
                tracks = playlist_tracks_map[file_path]
                
                if not tracks:
                    continue
                
                # Collect matches for this playlist
                spotify_tracks = []
                for track in tracks:
                    key = f"{track.get('artist', '').lower()}||{track.get('title', '').lower()}"
                    if key in track_matches:
                        spotify_tracks.append(track_matches[key])
                
                if spotify_tracks:
                    # Create/update playlist
                    track_uris = [t['uri'] for t in spotify_tracks]
                    tracks_added = auto_create_or_update_playlist(sp, playlist_name, track_uris, user_id)
                    
                    total_processed += 1
                    total_matches += len(spotify_tracks)
                    total_skipped += len(tracks) - len(spotify_tracks)
                    total_added += tracks_added
                    
                    logger.info(f"[AUTO] {playlist_name}: {len(spotify_tracks)}/{len(tracks)} matched, {tracks_added} added")
                else:
                    total_processed += 1
                    total_skipped += len(tracks)
                    logger.info(f"[AUTO] {playlist_name}: No tracks matched threshold")
        else:
            # Parallel processing for fewer playlists
            print(f"{Fore.CYAN}Processing {len(playlist_files)} playlists in parallel...")

            # Process playlists in parallel
            results = process_playlists_parallel(sp, playlist_files, user_id, args.auto_threshold, args.use_ai_boost, max_workers=min(3, len(playlist_files)))
            
            # Aggregate results
            total_processed = 0
            total_matches = 0
            total_skipped = 0
            total_added = 0
            
            for file_path, (matches, skipped, added) in results:
                if matches > 0 or skipped > 0:
                    total_processed += 1
                    total_matches += matches
                    total_skipped += skipped
                    total_added += added
                    playlist_name = os.path.splitext(os.path.basename(file_path))[0]
                    logger.info(f"[AUTO] {playlist_name}: {matches} matched, {added} added, {skipped} skipped")
        
        # Print summary
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.CYAN}AUTO-ADD COMPLETE")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.WHITE}Playlists processed: {total_processed}/{len(playlist_files)}")
        print(f"{Fore.WHITE}Total tracks matched: {total_matches}")
        print(f"{Fore.WHITE}Total tracks added: {total_added}")
        print(f"{Fore.WHITE}Total tracks skipped: {total_skipped}")
        
        if total_processed > 0:
            success_rate = (total_matches / (total_matches + total_skipped)) * 100 if (total_matches + total_skipped) > 0 else 0
            print(f"{Fore.WHITE}Match rate: {success_rate:.1f}%")
        
        print(f"{Fore.GREEN}✅ Auto-add completed successfully!")
        return

    elif args.replace_karaoke:
        # Karaoke replacement mode
        replace_karaoke_in_playlists(sp, user_id)
        return

    elif args.missing_tracks_mode:
        # Missing tracks mode
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.CYAN}MISSING TRACKS ANALYSIS")
        print(f"{Fore.CYAN}{'='*60}")
        print(f"{Fore.WHITE}• Will find tracks in local playlists missing from Spotify")
        print(f"{Fore.WHITE}• Will suggest additions above confidence >= {args.suggest_threshold}")
        print(f"{Fore.CYAN}{'='*60}\n")
        
        for i, file_path in enumerate(playlist_files, 1):
            try:
                logger.info(f"\nAnalyzing playlist {i}/{len(playlist_files)}: {os.path.basename(file_path)}")
                find_missing_tracks_in_playlists(sp, file_path, user_id, args.suggest_threshold)
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {e}")
                if args.debug:
                    traceback.print_exc()
        
        print(f"\n{Fore.GREEN}✅ Missing tracks analysis completed!")
        return
    
    # Standard mode - interactive threshold selection (only if not in command line batch mode)
    if not args.batch:
        print("\n" + "="*60)
        print("CONFIDENCE THRESHOLD SELECTION")
        print("="*60)
        print("The playlist converter uses fuzzy matching to find your songs on Spotify.")
        print("You can set two thresholds to control automation:")
        print()
        print("📊 Confidence Score Meanings:")
        print("  95-100: Almost certainly correct (perfect matches)")
        print("  85-94:  Very high confidence (recommended for auto-accept)")
        print("  80-84:  High confidence")  
        print("  70-79:  Good confidence")
        print("  60-69:  Medium confidence")
        print("  50-59:  Low confidence")
        print()
        print("🎯 Threshold Types:")
        print("  • Auto-Accept: Tracks above this score are added automatically")
        print("  • Manual Review: Tracks above this score are shown for your review")
        print("  • Below Manual Review: Tracks are skipped completely")
        print()
        
        # Get auto-accept threshold
        while True:
            try:
                user_auto = input(f"Enter auto-accept threshold (70-100, default 85): ").strip()
                if not user_auto:
                    auto_threshold = 85
                    break
                
                auto_value = int(user_auto)
                if 70 <= auto_value <= 100:
                    auto_threshold = auto_value
                    break
                else:
                    print("❌ Please enter a number between 70 and 100")
            except ValueError:
                print("❌ Please enter a valid number")
        
        # Get manual review threshold
        while True:
            try:
                user_manual = input(f"Enter manual review threshold (50-{auto_threshold-1}, default {min(70, auto_threshold-5)}): ").strip()
                default_manual = min(70, auto_threshold-5)
                if not user_manual:
                    manual_threshold = default_manual
                    break
                
                manual_value = int(user_manual)
                if 50 <= manual_value < auto_threshold:
                    manual_threshold = manual_value
                    break
                else:
                    print(f"❌ Manual review threshold must be between 50 and {auto_threshold-1}")
            except ValueError:
                print("❌ Please enter a valid number")
        
        print(f"✅ Auto-accept threshold: {auto_threshold}")
        print(f"✅ Manual review threshold: {manual_threshold}")
        
        # Ask about duplicate handling
        print("\n" + "="*60)
        print("DUPLICATE TRACK HANDLING")
        print("="*60)
        print("When creating/updating playlists, duplicates may be found.")
        print("Choose how you want to handle them:")
        print()
        print("Options:")
        print("  1. Auto-remove all duplicates (recommended)")
        print("  2. Ask me for each playlist (current behavior)")
        print("  3. Keep all duplicates (no removal)")
        print()
        
        while True:
            duplicate_choice = input("Choose duplicate handling (1-3, default: 1): ").strip()
            if not duplicate_choice:
                duplicate_choice = "1"
            
            if duplicate_choice in ["1", "2", "3"]:
                if duplicate_choice == "1":
                    DUPLICATE_CONFIG['auto_remove'] = True
                    DUPLICATE_CONFIG['keep_all'] = False
                    print("✅ Auto-remove duplicates: ON")
                elif duplicate_choice == "2":
                    DUPLICATE_CONFIG['auto_remove'] = False
                    DUPLICATE_CONFIG['keep_all'] = False
                    print("✅ Auto-remove duplicates: OFF (will ask per playlist)")
                else:  # "3"
                    DUPLICATE_CONFIG['auto_remove'] = False
                    DUPLICATE_CONFIG['keep_all'] = True
                    print("✅ Keep all duplicates: ON")
                break
            else:
                print("❌ Please enter 1, 2, or 3")

        # Ask about AI boost if not already set via command line
        if not args.use_ai_boost:
            print("\n" + "="*60)
            print("AI BOOST - INTELLIGENT TRACK MATCHING")
            print("="*60)
            print("AI Boost uses AI models to help identify hard-to-find tracks.")
            print()
            print("🤖 How it works:")
            print("  • Activates when regular search scores 60-84 (medium confidence)")
            print("  • Also tries when regular search finds nothing")
            print("  • AI analyzes metadata and suggests corrections for:")
            print("    - Swapped artist/title")
            print("    - Typos and alternative spellings")
            print("    - Cover versions vs originals")
            print("    - Alternative titles or featuring artists")
            print()
            print("⚙️  AI Service (configured in preferences):")
            from preferences_manager import get_preference
            ai_service = get_preference("ai.ai_service", "gemini")
            print(f"  • Current: {ai_service}")
            print(f"  • Gemini: Free tier available (recommended)")
            print(f"  • Claude/OpenAI/Perplexity: Paid API credits required")
            print()
            print("💰 Cost control: Max 50 AI requests per batch")
            print()

            while True:
                ai_choice = input("Enable AI Boost? (y/n, default: n): ").strip().lower()
                if ai_choice in ['', 'n']:
                    args.use_ai_boost = False
                    print("✅ AI Boost disabled - using regular search only")
                    break
                elif ai_choice == 'y':
                    args.use_ai_boost = True
                    print(f"✅ AI Boost enabled using {ai_service}")
                    break
                else:
                    print("❌ Please enter 'y' or 'n'")

        # Set up batch mode with dual thresholds
        args.batch = True
        args.auto_threshold = auto_threshold
        args.manual_threshold = manual_threshold
        confidence_threshold = manual_threshold

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"✅ Batch mode enabled:")
        print(f"  • {auto_threshold}+ = Auto-accept")
        print(f"  • {manual_threshold}-{auto_threshold-1} = Manual review")
        print(f"  • <{manual_threshold} = Skip")
        if args.use_ai_boost:
            print(f"\n🤖 AI Boost ENABLED:")
            print(f"  • Uses AI to identify tracks with scores 60-{auto_threshold-1}")
            print(f"  • Also tries AI when regular search finds nothing")
            print(f"  • Max 50 AI requests per batch (cost control)")

        print("="*60)
    else:
        # For batch mode or when no interactive selection, use command line threshold
        confidence_threshold = args.threshold
        if not hasattr(args, 'manual_threshold'):
            args.manual_threshold = confidence_threshold
    
    # Handle duplicate removal command line arguments and set global configuration
    if args.auto_remove_duplicates:
        DUPLICATE_CONFIG['auto_remove'] = True
        DUPLICATE_CONFIG['keep_all'] = False
    elif args.keep_duplicates:
        DUPLICATE_CONFIG['auto_remove'] = False
        DUPLICATE_CONFIG['keep_all'] = True
    elif args.ask_duplicates:
        DUPLICATE_CONFIG['auto_remove'] = False
        DUPLICATE_CONFIG['keep_all'] = False
    elif not hasattr(args, 'auto_remove_duplicates'):
        # Use defaults already set in DUPLICATE_CONFIG
        pass
    
    # Batch mode information
    if args.batch:
        logger.info(f"Batch mode enabled: auto-accepting matches with score >= {args.auto_threshold}")
    
    # Authenticate with Spotify
    logger.info("Authenticating with Spotify...")
    sp = authenticate_spotify()
    
    # Get user ID
    user_info = sp.current_user()
    user_id = user_info['id']
    
    # Check if user wants to use previous session decisions
    use_previous_decisions = check_and_use_previous_session()
    
    # Process each playlist file
    total_processed = 0
    total_matches = 0
    total_skipped = 0
    
    for i, file_path in enumerate(playlist_files, 1):
        try:
            logger.info(f"\nProcessing playlist {i}/{len(playlist_files)}: {os.path.basename(file_path)}")
            matches, skipped = process_playlist_file(sp, file_path, user_id, confidence_threshold, min_score, args.batch, args.auto_threshold, use_previous_decisions, args.use_ai_boost)
            total_processed += 1
            total_matches += matches
            total_skipped += skipped
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            traceback.print_exc()
    
    # Print summary
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"{Fore.CYAN}PROCESSING COMPLETE")
    print(f"{Fore.CYAN}{'='*50}")
    print(f"{Fore.WHITE}Playlists processed: {total_processed}/{len(playlist_files)}")
    print(f"{Fore.WHITE}Total tracks matched: {total_matches}")
    if 'total_added' in locals():
        print(f"{Fore.WHITE}Total tracks added: {total_added}")
    print(f"{Fore.WHITE}Total tracks skipped: {total_skipped}")
    
    if total_processed > 0:
        success_rate = (total_matches / (total_matches + total_skipped)) * 100 if (total_matches + total_skipped) > 0 else 0
        print(f"{Fore.WHITE}Success rate: {success_rate:.1f}%")
    
    print(f"{Fore.GREEN}✅ All playlists processed successfully!")

if __name__ == "__main__":
    main()
