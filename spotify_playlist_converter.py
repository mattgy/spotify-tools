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
CACHE_EXPIRATION = 30 * 24 * 60 * 60  # 30 days in seconds

def authenticate_spotify():
    """Authenticate with Spotify API."""
    try:
        # Get credentials from credentials manager
        client_id, client_secret, redirect_uri = get_spotify_credentials()
        
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPE,
            cache_path=os.path.join(os.getcwd(), ".cache")
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        sp.current_user()  # Test the connection
        return sp
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)

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
    parts = re.split(r' - ', filename_no_ext, 1)
    
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
            parts = re.split(r' - ', title_value, 1)
            
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

def search_track_on_spotify(sp, artist, title, album=None):
    """
    Search for a track on Spotify and return the best match.
    Uses caching to avoid redundant API calls.
    """
    if not title:
        return None
    
    # Create a cache key based on artist, album and title
    cache_key = f"track_search_{artist}_{album}_{title}".replace(" ", "_").lower()
    
    # Try to load from cache first
    cached_result = load_from_cache(cache_key, CACHE_EXPIRATION)
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

def process_search_results(results, artist, title, album, candidates, weight=1.0):
    """Process search results and add to candidates list with scores."""
    if not results['tracks']['items']:
        return
    
    for item in results['tracks']['items']:
        track_name = item['name']
        track_artists = [a['name'] for a in item['artists']]
        track_album = item['album']['name']
        
        # Calculate title similarity
        title_score = fuzz.ratio(title.lower(), track_name.lower())
        
        # Try partial token matching for title
        title_token_score = fuzz.token_sort_ratio(title.lower(), track_name.lower())
        title_score = max(title_score, title_token_score)
        
        # Calculate artist similarity if we have artist info
        artist_score = 0
        if artist:
            # Try exact match first
            if any(a.lower() == artist.lower() for a in track_artists):
                artist_score = 100
            else:
                # Try fuzzy matching
                artist_scores = [fuzz.ratio(artist.lower(), a.lower()) for a in track_artists]
                artist_token_scores = [fuzz.token_sort_ratio(artist.lower(), a.lower()) for a in track_artists]
                artist_score = max(max(artist_scores), max(artist_token_scores)) if artist_scores else 0
        
        # Calculate album similarity if we have album info
        album_score = 0
        if album:
            # Try exact match first
            if track_album.lower() == album.lower():
                album_score = 100
            else:
                # Try fuzzy matching
                album_score = fuzz.ratio(album.lower(), track_album.lower())
                album_token_score = fuzz.token_sort_ratio(album.lower(), track_album.lower())
                album_score = max(album_score, album_token_score)
        
        # Combined score with weights
        if artist and album:
            # Weight: 40% artist, 30% title, 30% album
            combined_score = (artist_score * 0.4 + title_score * 0.3 + album_score * 0.3) * weight
        elif artist:
            # Weight: 60% artist, 40% title
            combined_score = (artist_score * 0.6 + title_score * 0.4) * weight
        elif album:
            # Weight: 50% title, 50% album
            combined_score = (title_score * 0.5 + album_score * 0.5) * weight
        else:
            # Just title
            combined_score = title_score * weight
        
        candidates.append({
            'track': item,
            'score': combined_score,
            'title_score': title_score,
            'artist_score': artist_score,
            'album_score': album_score if album else 0
        })

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
        
        # Find tracks to add (tracks in track_uris but not in existing_tracks)
        tracks_to_add = [uri for uri in track_uris if uri not in existing_tracks]
        
        if tracks_to_add:
            logger.info(f"Adding {len(tracks_to_add)} new tracks to playlist '{playlist_name}'")
            
            # Add tracks in batches of 100 (Spotify API limit)
            for i in range(0, len(tracks_to_add), 100):
                batch = tracks_to_add[i:i+100]
                sp.playlist_add_items(playlist_id, batch)
            
            # Invalidate the cache for this playlist's tracks
            cache_key = f"playlist_tracks_{playlist_id}"
            save_to_cache(existing_tracks + tracks_to_add, cache_key)
            
            return playlist_id, len(tracks_to_add)
        else:
            logger.info(f"Playlist '{playlist_name}' is already complete. No new tracks added.")
            return playlist_id, 0
    else:
        logger.info(f"Creating new playlist: {playlist_name}")
        playlist = sp.user_playlist_create(
            user=user_id,
            name=playlist_name,
            public=False,
            description=f"Playlist created from local file by Spotify Playlist Converter"
        )
        
        # Add tracks in batches of 100 (Spotify API limit)
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]
            sp.playlist_add_items(playlist['id'], batch)
        
        # Invalidate the user playlists cache
        cache_key = f"user_playlists_{user_id}"
        playlists.append(playlist)
        save_to_cache(playlists, cache_key)
        
        # Cache the playlist tracks
        cache_key = f"playlist_tracks_{playlist['id']}"
        save_to_cache(track_uris, cache_key)
        
        return playlist['id'], len(track_uris)

def process_playlist_file(sp, file_path, user_id, confidence_threshold, min_score=50):
    """Process a single playlist file and convert it to a Spotify playlist."""
    logger.info(f"Processing playlist: {file_path}")
    
    # Extract playlist name from file name
    playlist_name = os.path.splitext(os.path.basename(file_path))[0]
    
    # Parse the playlist file
    tracks = parse_playlist_file(file_path)
    
    if not tracks:
        logger.warning(f"No tracks found in playlist: {file_path}")
        return
    
    logger.info(f"Found {len(tracks)} tracks in playlist")
    
    # Search for tracks on Spotify
    spotify_tracks = []
    skipped_tracks = []
    
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
            
            # Consistent options for all matches
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
                            continue
                
                # If we get here, either the search failed or the user rejected the match
                skipped_tracks.append(track)
            else:
                skipped_tracks.append(track)
                            
                            # Ask for album info
                            search_album = input("Enter album name (optional): ").strip()
                            
                            # Perform the manual search
                            manual_match = search_track_on_spotify(sp, search_artist, search_title, search_album if search_album else None)
                            
                            if manual_match:
                                print(f"Found: {', '.join(manual_match['artists'])} - {manual_match['name']} (from album: {manual_match['album']}) (Score: {manual_match['score']:.1f})")
                                confirm = input("Accept this match? (y/n): ").lower()
                                if confirm == 'y':
                                    spotify_tracks.append(manual_match)
                                    continue
                else:
                    print("No alternative match found.")
                
                # If we get here, the retry didn't work or was rejected
                skipped_tracks.append(track)
            else:
                # User rejected the match
                skipped_tracks.append(track)
        else:
            # No match found
            print(f"\nNo match found for: {track['artist']} - {track['title']}")
            if track['album']:
                print(f"Album: {track['album']}")
                
            options = "What would you like to do? (s:search manually, n:skip): "
            action = input(options).lower()
            
            if action == 's':
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
                        confirm = input("Accept this match? (y/n): ").lower()
                        if confirm == 'y':
                            spotify_tracks.append(manual_match)
                            continue
            
            # If we get here, either the user skipped or the manual search failed
            skipped_tracks.append(track)
    
    if not spotify_tracks:
        logger.warning("No tracks could be matched on Spotify. Playlist will not be created.")
        return
    
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
    
    return playlist_id

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
    
    # Authenticate with Spotify
    logger.info("Authenticating with Spotify...")
    sp = authenticate_spotify()
    
    # Get user ID
    user_info = sp.current_user()
    user_id = user_info['id']
    
    # Process each playlist file
    for file_path in playlist_files:
        try:
            process_playlist_file(sp, file_path, user_id, confidence_threshold, min_score)
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            traceback.print_exc()
    
    logger.info("All playlists processed successfully!")

if __name__ == "__main__":
    main()
