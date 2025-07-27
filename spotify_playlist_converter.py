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
CONFIDENCE_THRESHOLD = 80  # Minimum confidence score for automatic matching
SCOPE = "playlist-read-private playlist-modify-private playlist-modify-public"
SUPPORTED_EXTENSIONS = ['.m3u', '.m3u8', '.pls']

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
    text = re.sub(r'^(\d+[\s\.\-_]+)', '', text)
    
    # Remove common file extensions
    text = re.sub(r'\.mp3$|\.flac$|\.wav$|\.m4a$|\.ogg$', '', text)
    
    # Remove brackets and their contents if they appear to be technical info
    text = re.sub(r'\([^\)]*kbps[^\)]*\)|\[[^\]]*kbps[^\]]*\]', '', text)
    
    # Clean up whitespace
    text = text.strip()
    
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

def parse_playlist_file(file_path):
    """Parse a playlist file based on its extension."""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in ['.m3u', '.m3u8']:
        return parse_m3u_playlist(file_path)
    elif ext == '.pls':
        return parse_pls_playlist(file_path)
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

def calculate_match_score(search_artist, search_title, result_artist, result_title, result_album=""):
    """Calculate a comprehensive match score between search terms and result."""
    # Normalize all strings
    norm_search_artist = normalize_string(search_artist)
    norm_search_title = normalize_string(search_title)
    norm_result_artist = normalize_string(result_artist)
    norm_result_title = normalize_string(result_title)
    norm_result_album = normalize_string(result_album)
    
    # Artist matching (40% weight)
    artist_score = fuzz.ratio(norm_search_artist, norm_result_artist)
    
    # Title matching (50% weight)
    title_score = fuzz.ratio(norm_search_title, norm_result_title)
    
    # Bonus points for partial matches (10% weight)
    bonus_score = 0
    if norm_search_artist in norm_result_artist or norm_result_artist in norm_search_artist:
        bonus_score += 20
    if norm_search_title in norm_result_title or norm_result_title in norm_search_title:
        bonus_score += 30
    
    # Penalty for very different string lengths
    length_penalty = 0
    title_len_diff = abs(len(norm_search_title) - len(norm_result_title))
    if title_len_diff > 10:
        length_penalty = min(20, title_len_diff)
    
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
    cache_key = f"track_search_{artist}_{album}_{title}".replace(" ", "_").lower()
    
    # Try to load from cache first
    cached_result = load_from_cache(cache_key, CACHE_EXPIRATION['medium'])
    if cached_result:
        logger.debug(f"Using cached result for '{artist} - {title}'")
        return cached_result
    
    # Clean up the title and artist
    # Remove common file extensions and numbering
    title = re.sub(r'\.mp3$|\.flac$|\.wav$|\.m4a$|\.ogg$', '', title)
    title = re.sub(r'^(\d+[\s\.\-_]+)', '', title)  # Remove leading numbers like "01 - " or "1. "
    
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

def create_or_update_spotify_playlist(sp, playlist_name, track_uris, user_id):
    """Create a new Spotify playlist or update an existing one."""
    # Get user playlists
    playlists = get_user_playlists(sp, user_id)
    
    existing_playlist = next((p for p in playlists if p['name'] == playlist_name), None)
    
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
        playlists.append(playlist)
        save_to_cache(playlists, cache_key)
        
        # Cache the playlist tracks
        cache_key = f"playlist_tracks_{playlist['id']}"
        save_to_cache(track_uris, cache_key)
        
        logger.info(f"✅ Successfully created playlist '{playlist_name}' with {len(track_uris)} tracks")
        return playlist['id'], len(track_uris)

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
                    elif choice == 's':
                        # Manual search option
                        search_artist = input("Enter artist name: ").strip()
                        search_title = input("Enter song title: ").strip()
                        search_album = input("Enter album (optional): ").strip() or None
                        
                        manual_match = search_track_on_spotify(sp, search_artist, search_title, search_album)
                        if manual_match:
                            print(f"Found: {', '.join(manual_match['artists'])} - {manual_match['name']} (Score: {manual_match['score']:.1f})")
                            if input("Accept this match? (y/n): ").lower().strip() == 'y':
                                spotify_tracks.append(manual_match)
                            else:
                                skipped_tracks.append(track)
                        else:
                            print("No matches found.")
                            skipped_tracks.append(track)
                    else:
                        skipped_tracks.append(track)
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
            elif match['score'] >= confidence_threshold:
                # High confidence match
                if batch_mode:
                    # In batch mode, auto-accept high confidence matches above threshold
                    print(f"AUTO-ACCEPTED (high confidence: {match['score']:.1f})")
                    spotify_tracks.append(match)
                else:
                    # Interactive mode - user confirmation required
                    options = "Accept this match? (y/n/s/t - y:yes, n:no, s:search manually, t:try again): "
                    
                    while True:
                        confirm = input(options).lower()
                        
                        if confirm == 'y':
                            spotify_tracks.append(match)
                            break
                        elif confirm == 'n':
                            skipped_tracks.append(track)
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
                                        break
                                    elif manual_confirm == 'n':
                                        skipped_tracks.append(track)
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
                        manual_confirm = input("Accept this match? (y/n): ").lower()
                        if manual_confirm == 'y':
                            spotify_tracks.append(manual_match)
                
                # If we get here, either the search failed or the user rejected the match
                skipped_tracks.append(track)
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

def find_playlist_files(directory):
    """Find all playlist files in the given directory and its subdirectories."""
    playlist_files = []
    
    for ext in SUPPORTED_EXTENSIONS:
        pattern = os.path.join(directory, f"**/*{ext}")
        playlist_files.extend(glob.glob(pattern, recursive=True))
    
    return playlist_files

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
    args = parser.parse_args()
    
    # Set up logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Use the provided threshold
    confidence_threshold = args.threshold
    min_score = args.min_score
    
    # Resolve directory path
    directory = os.path.abspath(args.directory)
    
    if not os.path.isdir(directory):
        logger.error(f"Directory not found: {directory}")
        sys.exit(1)
    
    # Find playlist files
    logger.info(f"Searching for playlist files in: {directory}")
    playlist_files = find_playlist_files(directory)
    
    if not playlist_files:
        logger.info(f"No playlist files found in {directory}")
        sys.exit(0)
    
    logger.info(f"Found {len(playlist_files)} playlist files")
    
    # Limit number of playlists if specified
    if args.max_playlists:
        playlist_files = playlist_files[:args.max_playlists]
        logger.info(f"Limited to {len(playlist_files)} playlists")
    
    # Interactive threshold selection (only if not in command line batch mode)
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
        confidence_threshold = manual_threshold
        
        print(f"✅ Batch mode enabled:")
        print(f"  • {auto_threshold}+ = Auto-accept")
        print(f"  • {manual_threshold}-{auto_threshold-1} = Manual review")
        print(f"  • <{manual_threshold} = Skip")
        
        print("="*60)
    elif args.batch:
        confidence_threshold = args.threshold
    
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
    logger.info(f"\n" + "="*50)
    logger.info(f"BATCH PROCESSING COMPLETE")
    logger.info(f"="*50)
    logger.info(f"Playlists processed: {total_processed}/{len(playlist_files)}")
    logger.info(f"Total tracks matched: {total_matches}")
    logger.info(f"Total tracks skipped: {total_skipped}")
    
    if total_processed > 0:
        success_rate = (total_matches / (total_matches + total_skipped)) * 100 if (total_matches + total_skipped) > 0 else 0
        logger.info(f"Success rate: {success_rate:.1f}%")
    
    logger.info("All playlists processed successfully!")

if __name__ == "__main__":
    main()
