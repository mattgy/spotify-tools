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
from thefuzz import fuzz, process
import time
import logging
import json
from tqdm import tqdm
import traceback
from datetime import datetime, timedelta
import colorama
from colorama import Fore, Style
import unicodedata
from collections import defaultdict

# Initialize colorama for cross-platform color support
colorama.init(autoreset=True)

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from credentials_manager import get_spotify_credentials
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

# Constants
CONFIDENCE_THRESHOLD = 80  # Default minimum confidence score for automatic matching
SCOPE = "playlist-read-private playlist-modify-private playlist-modify-public"
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

# Track number patterns to remove
TRACK_NUMBER_PATTERNS = [
    r'^\d+[\s\-\.\)]+',  # "01 ", "01-", "01.", "01)"
    r'^\[\d+\]\s*',       # "[01] "
    r'^\(\d+\)\s*',       # "(01) "
    r'^Track\s*\d+[\s\-:]+',  # "Track 01 - "
    r'^\d+\.\s*-\s*',     # "01. - "
]

def create_decision_cache_key(track_info, match_info):
    """Create a cache key for user decisions based on track and match info."""
    # Use track path, artist, title and matched track ID for uniqueness
    track_path = track_info.get('path', '')
    track_artist = track_info.get('artist', '').lower().strip()
    track_title = track_info.get('title', '').lower().strip()
    match_id = match_info.get('id', '') if match_info else ''
    
    # Create a stable key
    key_parts = [track_path, track_artist, track_title, match_id]
    cache_key = "_".join(str(part) for part in key_parts if part)
    return f"user_decision_{hash(cache_key) % 1000000}"  # Use hash to keep key manageable

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

def get_cached_decision(track_info, match_info):
    """Get a previously cached user decision."""
    cache_key = create_decision_cache_key(track_info, match_info)
    cached_data = load_from_cache(cache_key, 30 * 24 * 60 * 60)  # Cache for 30 days
    if cached_data and cached_data.get('decision') == 'y':
        return cached_data
    return None

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
    Handles various common path formats.
    """
    # Default values
    track_info = {
        'artist': '',
        'album': '',
        'title': '',
        'path': path,
        'original_line': path  # Store the original path
    }
    
    # Get just the filename without extension
    filename = os.path.basename(path)
    filename_no_ext = os.path.splitext(filename)[0]
    
    # First, try to extract from the filename (common pattern: "Artist - Title.mp3")
    parts = re.split(r' - ', filename_no_ext, maxsplit=1)
    
    if len(parts) > 1:
        # Remove track numbers from the beginning
        artist = re.sub(r'^(\d+[\s\.\-_]+)', '', parts[0].strip())
        title = parts[1].strip()
        
        track_info['artist'] = artist
        track_info['title'] = title
    else:
        # If no artist-title separator found, assume it's just the title
        title = re.sub(r'^(\d+[\s\.\-_]+)', '', filename_no_ext.strip())
        track_info['title'] = title
    
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
            
            # If no separator found, assume space-separated (artist first words, song rest)
            if not artist and len(line.split()) >= 2:
                words = line.split()
                # Simple heuristic: first 1-2 words are artist, rest is title
                if len(words) > 4:
                    artist = ' '.join(words[:2])
                    title = ' '.join(words[2:])
                else:
                    artist = words[0]
                    title = ' '.join(words[1:])
            
            if artist and title:
                tracks.append({
                    'artist': artist,
                    'title': title,
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

def normalize_string(s):
    """Normalize string for better matching."""
    if not s:
        return ""
    # Remove special characters, convert to lowercase
    s = re.sub(r'[^\w\s]', '', s.lower())
    # Remove common words that might interfere with matching
    common_words = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'feat', 'featuring', 'ft']
    words = s.split()
    words = [w for w in words if w not in common_words]
    return ' '.join(words).strip()

def normalize_for_variations(text):
    """Apply common variations normalization."""
    if not text:
        return ""
    
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

def calculate_match_score(search_artist, search_title, result_artist, result_title, result_album=""):
    """Calculate a comprehensive match score between search terms and result."""
    # First apply variations normalization
    search_artist_var = normalize_for_variations(search_artist)
    search_title_var = normalize_for_variations(search_title)
    result_artist_var = normalize_for_variations(result_artist)
    result_title_var = normalize_for_variations(result_title)
    
    # Strip remaster tags for comparison
    search_title_clean = strip_remaster_tags(search_title_var)
    result_title_clean = strip_remaster_tags(result_title_var)
    
    # Then normalize for comparison
    norm_search_artist = normalize_string(search_artist_var)
    norm_search_title = normalize_string(search_title_clean)
    norm_result_artist = normalize_string(result_artist_var)
    norm_result_title = normalize_string(result_title_clean)
    norm_result_album = normalize_string(result_album)
    
    # Artist matching (40% weight)
    artist_score = fuzz.ratio(norm_search_artist, norm_result_artist)
    
    # If artist score is low, try phonetic matching
    if artist_score < 70:
        phonetic_artist_score = phonetic_match(search_artist, result_artist)
        if phonetic_artist_score > artist_score:
            artist_score = (artist_score + phonetic_artist_score) / 2
    
    # Title matching (50% weight)
    title_score = fuzz.ratio(norm_search_title, norm_result_title)
    
    # If title score is low, try phonetic matching
    if title_score < 70:
        phonetic_title_score = phonetic_match(search_title_clean, result_title_clean)
        if phonetic_title_score > title_score:
            title_score = (title_score + phonetic_title_score) / 2
    
    # Bonus points for partial matches (10% weight)
    bonus_score = 0
    if norm_search_artist in norm_result_artist or norm_result_artist in norm_search_artist:
        bonus_score += 20
    if norm_search_title in norm_result_title or norm_result_title in norm_search_title:
        bonus_score += 30
    
    # Special handling for remix vs non-remix
    search_is_remix = 'remix' in search_title.lower()
    result_is_remix = 'remix' in result_title.lower()
    
    # Penalty if remix status doesn't match
    if search_is_remix != result_is_remix:
        bonus_score -= 15
    
    # Penalty for very different string lengths (unless it's due to remaster tags)
    length_penalty = 0
    if not ('remaster' in result_title.lower() and 'remaster' not in search_title.lower()):
        title_len_diff = abs(len(norm_search_title) - len(norm_result_title))
        if title_len_diff > 15:  # Increased tolerance for length differences
            length_penalty = min(15, title_len_diff - 10)  # Reduced penalty
    
    # Calculate weighted score
    total_score = (artist_score * 0.4 + title_score * 0.5 + bonus_score * 0.1) - length_penalty
    return max(0, min(100, total_score))

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
        
        # Calculate match score
        score = calculate_match_score(search_artist or "", search_title, result_artists, result_title, result_album)
        
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
    if not title:
        return None
    
    # Create a cache key based on artist, album and title
    # Clean the key components first
    clean_artist = normalize_for_variations(artist) if artist else "none"
    clean_title = normalize_for_variations(title) if title else "none"
    clean_album = normalize_for_variations(album) if album else "none"
    
    # Create cache key
    cache_key = f"track_search_{clean_artist}_{clean_album}_{clean_title}".replace(" ", "_").lower()
    
    # Also check for variation cache keys (e.g., with/without "feat." vs "featuring")
    variation_keys = []
    if artist and ('feat' in artist.lower() or 'ft' in artist.lower() or '&' in artist):
        # Create alternate keys with variations
        for variant, normalized in COMMON_VARIATIONS.items():
            if variant in artist.lower():
                alt_artist = artist.lower().replace(variant, normalized)
                alt_key = f"track_search_{alt_artist}_{clean_album}_{clean_title}".replace(" ", "_").lower()
                variation_keys.append(alt_key)
    
    # Try to load from cache first
    cached_result = load_from_cache(cache_key, CACHE_EXPIRATION['medium'])
    if cached_result:
        logger.debug(f"Using cached result for '{artist} - {title}'")
        return cached_result
    
    # Clean up the title and artist
    # Remove common file extensions and numbering
    title = re.sub(r'\.mp3$|\.flac$|\.wav$|\.m4a$|\.ogg$|\.wma$|\.aac$|\.opus$', '', title, flags=re.IGNORECASE)
    title = remove_track_numbers(title)
    
    # Handle cases where artist might be in the title
    if not artist and " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()
    
    # Log the search parameters
    logger.debug(f"Searching for: Artist='{artist}', Album='{album}', Title='{title}'")
    
    # Try multiple search strategies
    candidates = []
    
    # Strategy 1: Exact artist, album and title search (if album is available)
    if artist and album:
        query1 = f"artist:\"{artist}\" album:\"{album}\" track:\"{title}\""
        logger.debug(f"Strategy 1: {query1}")
        try:
            results1 = sp.search(q=query1, type='track', limit=10)
            process_search_results(results1, artist, title, album, candidates, weight=1.5)
            time.sleep(0.1)  # Rate limiting between strategies
            
            # Early exit if we found a very high-confidence match
            if candidates and max(c['score'] for c in candidates) > 95:
                logger.debug("Found very high-confidence match, skipping remaining strategies")
                best_match = max(candidates, key=lambda x: x['score'])
                result = {
                    'id': best_match['track']['id'],
                    'name': best_match['track']['name'],
                    'artists': [artist['name'] for artist in best_match['track']['artists']],
                    'album': best_match['track']['album']['name'],
                    'score': best_match['score'],
                    'uri': best_match['track']['uri']
                }
                save_to_cache(result, cache_key)
                return result
        except Exception as e:
            logger.error(f"Error in search strategy 1: {e}")
    
    # Strategy 2: Exact artist and title search
    if artist:
        query2 = f"artist:\"{artist}\" track:\"{title}\""
        logger.debug(f"Strategy 2: {query2}")
        try:
            results2 = sp.search(q=query2, type='track', limit=10)
            process_search_results(results2, artist, title, album, candidates, weight=1.3)
        except Exception as e:
            logger.error(f"Error in search strategy 2: {e}")
    
    # Strategy 3: Album and title search (if album is available)
    if album:
        query3 = f"album:\"{album}\" track:\"{title}\""
        logger.debug(f"Strategy 3: {query3}")
        try:
            results3 = sp.search(q=query3, type='track', limit=10)
            process_search_results(results3, artist, title, album, candidates, weight=1.2)
        except Exception as e:
            logger.error(f"Error in search strategy 3: {e}")
    
    # Strategy 4: Quoted title with artist
    if artist:
        query4 = f"\"{title}\" artist:\"{artist}\""
        logger.debug(f"Strategy 4: {query4}")
        try:
            results4 = sp.search(q=query4, type='track', limit=10)
            process_search_results(results4, artist, title, album, candidates, weight=1.1)
        except Exception as e:
            logger.error(f"Error in search strategy 4: {e}")
    
    # Strategy 5: Simple artist, album and title
    if artist and album:
        query5 = f"{artist} {album} {title}"
        logger.debug(f"Strategy 5: {query5}")
        try:
            results5 = sp.search(q=query5, type='track', limit=10)
            process_search_results(results5, artist, title, album, candidates, weight=1.05)
        except Exception as e:
            logger.error(f"Error in search strategy 5: {e}")
    
    # Strategy 6: Simple artist and title
    if artist:
        query6 = f"{artist} {title}"
        logger.debug(f"Strategy 6: {query6}")
        try:
            results6 = sp.search(q=query6, type='track', limit=10)
            process_search_results(results6, artist, title, album, candidates, weight=1.0)
        except Exception as e:
            logger.error(f"Error in search strategy 6: {e}")
    
    # Strategy 7: Just the title
    query7 = f"\"{title}\""
    logger.debug(f"Strategy 7: {query7}")
    try:
        results7 = sp.search(q=query7, type='track', limit=10)
        process_search_results(results7, artist, title, album, candidates, weight=0.9)
    except Exception as e:
        logger.error(f"Error in search strategy 7: {e}")
    
    # Strategy 8: Try with partial matching for title
    # This helps with tracks that have additional info in parentheses
    base_title = re.sub(r'\([^\)]+\)|\[[^\]]+\]', '', title).strip()
    if base_title != title:
        query8 = f"artist:\"{artist}\" track:\"{base_title}\"" if artist else f"\"{base_title}\""
        logger.debug(f"Strategy 8: {query8}")
        try:
            results8 = sp.search(q=query8, type='track', limit=10)
            process_search_results(results8, artist, title, album, candidates, weight=0.95)
        except Exception as e:
            logger.error(f"Error in search strategy 8: {e}")
    
    # Strategy 9: Try with just the album name and artist
    if artist and album:
        query9 = f"artist:\"{artist}\" album:\"{album}\""
        logger.debug(f"Strategy 9: {query9}")
        try:
            results9 = sp.search(q=query9, type='track', limit=20)
            # For this strategy, we'll check each track to see if the title is similar
            if results9['tracks']['items']:
                for track in results9['tracks']['items']:
                    track_name = track['name']
                    title_score = fuzz.ratio(title.lower(), track_name.lower())
                    if title_score > 70:  # Only add if title is somewhat similar
                        track_artists = [a['name'] for a in track['artists']]
                        track_album = track['album']['name']
                        
                        # Create a candidate with high weight if it's a good match
                        candidates.append({
                            'track': track,
                            'score': title_score * 1.2,  # Boost the score
                            'title_score': title_score,
                            'artist_score': 100 if any(a.lower() == artist.lower() for a in track_artists) else 0,
                            'album_score': 100 if album.lower() == track_album.lower() else 0
                        })
        except Exception as e:
            logger.error(f"Error in search strategy 9: {e}")
    
    # If we have no candidates, return None
    if not candidates:
        logger.debug("No candidates found for this track")
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
    Uses caching to avoid redundant API calls.
    """
    cache_key = f"user_playlists_{user_id}"
    
    # Try to load from cache first
    cached_playlists = load_from_cache(cache_key, 60 * 60)  # Cache for 1 hour
    if cached_playlists:
        logger.debug("Using cached user playlists")
        return cached_playlists
    
    playlists = []
    offset = 0
    limit = 50
    
    while True:
        response = sp.current_user_playlists(limit=limit, offset=offset)
        playlists.extend(response['items'])
        
        if len(response['items']) < limit:
            break
        
        offset += limit
    
    # Save to cache
    save_to_cache(playlists, cache_key)
    
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
    
    # Look for exact name matches
    exact_matches = [p for p in playlists if p['name'] == playlist_name]
    
    # Look for similar name matches
    similar_matches = []
    norm_target_name = normalize_string(playlist_name).lower()
    
    for playlist in playlists:
        if playlist['name'] != playlist_name:  # Skip exact matches, already found
            norm_playlist_name = normalize_string(playlist['name']).lower()
            similarity = fuzz.ratio(norm_target_name, norm_playlist_name)
            
            # Consider names similar if they have >80% similarity
            if similarity > 80:
                similar_matches.append({
                    'playlist': playlist,
                    'similarity': similarity
                })
    
    # Sort similar matches by similarity
    similar_matches.sort(key=lambda x: x['similarity'], reverse=True)
    
    return exact_matches, similar_matches

def create_or_update_spotify_playlist(sp, playlist_name, track_uris, user_id):
    """Create a new Spotify playlist or update an existing one."""
    # Check for duplicate playlists first
    exact_matches, similar_matches = check_for_duplicate_playlists(sp, playlist_name, track_uris, user_id)
    
    # Handle similar matches - ask user if they want to use existing playlist
    if similar_matches and not exact_matches:
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
                sp.playlist_add_items(playlist_id, batch)
            
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
                    
                    remove_choice = input(f"\n{Fore.CYAN}Remove duplicates? (y/n): ").lower().strip()
                    if remove_choice == 'y':
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
                
                remove_choice = input(f"\n{Fore.CYAN}Remove duplicates? (y/n): ").lower().strip()
                if remove_choice == 'y':
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
    
    while True:
        search_query = input("\nEnter search query (artist - title) or 'skip' to skip: ").strip()
        
        if search_query.lower() == 'skip':
            return None
        
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
            retry = input("Try again? (y/n): ").lower().strip()
            if retry != 'y':
                return None

def process_tracks_batch(sp, tracks_batch, confidence_threshold, batch_mode=False, auto_threshold=85):
    """Process a batch of tracks efficiently with minimal user interaction."""
    results = []
    
    for track in tracks_batch:
        match = search_track_on_spotify(sp, track['artist'], track['title'], track['album'])
        
        if match:
            if batch_mode and match['score'] >= auto_threshold:
                results.append({'track': track, 'match': match, 'accepted': True, 'auto': True})
            elif match['score'] >= confidence_threshold:
                results.append({'track': track, 'match': match, 'accepted': False, 'review': True})
            else:
                results.append({'track': track, 'match': match, 'accepted': False, 'review': False})
        else:
            results.append({'track': track, 'match': None, 'accepted': False, 'review': False})
    
    return results

def process_playlist_file(sp, file_path, user_id, confidence_threshold, min_score=50, batch_mode=False, auto_threshold=85):
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
    spotify_tracks = []
    skipped_tracks = []
    
    # Process tracks in batches for efficiency when in batch mode
    if batch_mode and len(tracks) > 10:
        logger.info(f"Processing {len(tracks)} tracks in batch mode...")
        batch_size = BATCH_SIZES['processing_batch']
        
        # Process in batches
        for i in range(0, len(tracks), batch_size):
            batch = tracks[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(tracks) + batch_size - 1)//batch_size}")
            
            batch_results = process_tracks_batch(sp, batch, confidence_threshold, batch_mode, auto_threshold)
            
            for result in batch_results:
                if result['accepted'] and result['match']:
                    spotify_tracks.append(result['match'])
                elif result.get('review', False) and result['match']:
                    # Manual review needed
                    track = result['track']
                    match = result['match']
                    original_line = track.get('original_line', f"{track['artist']} - {track['title']}")
                    
                    print(f"\nManual Review Required:")
                    print(f"Original: {original_line}")
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
                    
            # Add delay between batches for rate limiting
            if i + batch_size < len(tracks):
                time.sleep(0.5)
                
    else:
        # Interactive mode or small playlist - process individually
        for track in tqdm(tracks, desc="Searching tracks"):
            # Get the original line from the playlist file if available
            original_line = track.get('original_line', f"{track['artist']} - {track['title']}")
            
            # Log the extracted metadata
            logger.debug(f"Extracted metadata: Artist='{track['artist']}', Album='{track['album']}', Title='{track['title']}'")
            
            # Search with all available metadata
            match = search_track_on_spotify(sp, track['artist'], track['title'], track['album'])
            
            if match:
                # Check if we have a cached decision for this track/match combination
                cached_decision = get_cached_decision(track, match)
                if cached_decision:
                    print(f"\nUsing previous decision for: {original_line}")
                    print(f"Match: {', '.join(match['artists'])} - {match['name']} (Score: {match['score']:.1f}) - PREVIOUSLY ACCEPTED")
                    spotify_tracks.append(match)
                    continue
                
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

def process_playlist_file_auto_mode(sp, file_path, user_id, auto_threshold=85):
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
    
    for track in tracks:
        # Apply learning patterns first
        learned_artist, learned_title = apply_learning_patterns(track['artist'], track['title'])
        
        # Search with learned patterns
        match = search_track_on_spotify(sp, learned_artist, learned_title, track.get('album'))
        
        # If no match with learned patterns, try original
        if not match and (learned_artist != track['artist'] or learned_title != track['title']):
            match = search_track_on_spotify(sp, track['artist'], track['title'], track.get('album'))
        
        if match and match['score'] >= auto_threshold:
            spotify_tracks.append(match)
            # Save successful match for learning
            save_user_decision(track, match, 'y')
        else:
            skipped_tracks.append(track)
    
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
    
    # Find exact match only
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

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Convert local playlist files to Spotify playlists")
    parser.add_argument("directory", nargs="?", default=".", help="Directory to search for playlist files (default: current directory)")
    parser.add_argument("--threshold", type=int, default=CONFIDENCE_THRESHOLD, help=f"Confidence threshold for automatic matching (default: {CONFIDENCE_THRESHOLD})")
    parser.add_argument("--min-score", type=int, default=50, help="Minimum score to show recommendations (default: 50)")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching (always fetch fresh data)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--batch", action="store_true", help="Batch mode: auto-accept high confidence matches")
    parser.add_argument("--auto-threshold", type=int, default=85, help="Auto-accept threshold for batch mode (default: 85)")
    parser.add_argument("--max-playlists", type=int, help="Maximum number of playlists to process")
    
    # New mode arguments
    parser.add_argument("--auto-mode", action="store_true", help="Fully autonomous mode - no user interaction")
    parser.add_argument("--missing-tracks-mode", action="store_true", help="Find and suggest missing tracks in playlists")
    parser.add_argument("--suggest-threshold", type=int, default=70, help="Threshold for suggesting missing tracks (default: 70)")
    parser.add_argument("--clear-cache", action="store_true", help="Clear processed playlist cache")
    
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
    # In auto-mode, don't prompt for text files
    include_text = not args.auto_mode
    playlist_files = find_playlist_files(directory, include_text_files=include_text)
    
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
            with tqdm(total=len(unique_tracks), desc="Searching tracks") as pbar:
                for key, track in unique_tracks.items():
                    # Apply learning patterns
                    learned_artist, learned_title = apply_learning_patterns(track['artist'], track['title'])
                    
                    match = search_track_on_spotify(sp, learned_artist, learned_title, track.get('album'))
                    if not match and (learned_artist != track['artist'] or learned_title != track['title']):
                        match = search_track_on_spotify(sp, track['artist'], track['title'], track.get('album'))
                    
                    if match and match['score'] >= args.auto_threshold:
                        track_matches[key] = match
                        save_user_decision(track, match, 'y')
                    
                    pbar.update(1)
                    time.sleep(0.05)  # Rate limiting
            
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
            # Standard processing for fewer playlists
            total_processed = 0
            total_matches = 0
            total_skipped = 0
            total_added = 0
            
            for i, file_path in enumerate(playlist_files, 1):
                try:
                    logger.info(f"\n[AUTO] Processing playlist {i}/{len(playlist_files)}")
                    matches, skipped, added = process_playlist_file_auto_mode(sp, file_path, user_id, args.auto_threshold)
                    total_processed += 1
                    total_matches += matches
                    total_skipped += skipped
                    total_added += added
                except Exception as e:
                    logger.error(f"[AUTO] Error processing {file_path}: {e}")
                    if args.debug:
                        traceback.print_exc()
        
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
        
        # Set up batch mode with dual thresholds
        args.batch = True
        args.auto_threshold = auto_threshold
        args.manual_threshold = manual_threshold
        confidence_threshold = manual_threshold
        
        print(f"✅ Batch mode enabled:")
        print(f"  • {auto_threshold}+ = Auto-accept")
        print(f"  • {manual_threshold}-{auto_threshold-1} = Manual review")
        print(f"  • <{manual_threshold} = Skip")
        
        print("="*60)
    else:
        # For batch mode or when no interactive selection, use command line threshold
        confidence_threshold = args.threshold
        if not hasattr(args, 'manual_threshold'):
            args.manual_threshold = confidence_threshold
    
    # Batch mode information
    if args.batch:
        logger.info(f"Batch mode enabled: auto-accepting matches with score >= {args.auto_threshold}")
    
    # Authenticate with Spotify
    logger.info("Authenticating with Spotify...")
    sp = authenticate_spotify()
    
    # Get user ID
    user_info = sp.current_user()
    user_id = user_info['id']
    
    # Process each playlist file
    total_processed = 0
    total_matches = 0
    total_skipped = 0
    
    for i, file_path in enumerate(playlist_files, 1):
        try:
            logger.info(f"\nProcessing playlist {i}/{len(playlist_files)}: {os.path.basename(file_path)}")
            matches, skipped = process_playlist_file(sp, file_path, user_id, confidence_threshold, min_score, args.batch, args.auto_threshold)
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
