#!/usr/bin/env python3
"""
Script to add all songs from your created Spotify playlists to your Liked Songs.
This script uses the Spotify Web API to:
1. Authenticate with your Spotify account
2. Fetch all playlists you've created
3. Extract all unique tracks from those playlists
4. Add those tracks to your Liked Songs collection

Requirements:
- Python 3.6+
- spotipy library (pip install spotipy)
"""

import os
import sys
import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from collections import defaultdict

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from credentials_manager import get_spotify_credentials
from cache_utils import save_to_cache, load_from_cache

# Spotify API scopes needed for this script
SCOPES = [
    "user-library-read",
    "user-library-modify",
    "playlist-read-private"
]

# Cache expiration (in seconds)
CACHE_EXPIRATION = 24 * 60 * 60  # 24 hours

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        # Get credentials from credentials manager
        client_id, client_secret, redirect_uri = get_spotify_credentials()
        
        # Set up authentication with a specific cache path
        cache_path = os.path.join(os.path.expanduser("~"), ".spotify-tools", "spotify_token_cache")
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=" ".join(SCOPES),
            open_browser=False,  # Don't open browser repeatedly
            cache_path=cache_path  # Use a specific cache path
        )
        
        # Create Spotify client
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        # Test the connection
        sp.current_user()
        
        return sp
    except Exception as e:
        print(f"Error setting up Spotify client: {e}")
        sys.exit(1)

def get_user_playlists(sp):
    """Get all playlists created by the current user."""
    # Try to load from cache
    cache_key = f"user_playlists_{sp.current_user()['id']}"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        print("Using cached playlist data")
        return cached_data
    
    print("Fetching your playlists...")
    
    # Get all user's playlists
    playlists = []
    offset = 0
    limit = 50  # Maximum allowed by Spotify API
    
    while True:
        results = sp.current_user_playlists(limit=limit, offset=offset)
        
        if not results['items']:
            break
        
        # Filter to only include playlists created by the user
        user_id = sp.current_user()['id']
        user_playlists = [p for p in results['items'] if p['owner']['id'] == user_id]
        playlists.extend(user_playlists)
        
        if len(results['items']) < limit:
            break
        
        offset += limit
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.1)
    
    print(f"Found {len(playlists)} playlists that you've created")
    
    # Save to cache
    save_to_cache(playlists, cache_key)
    
    return playlists

def get_tracks_from_playlists(sp, playlists):
    """Extract all unique tracks from the given playlists."""
    # Try to load from cache
    cache_key = "playlist_tracks"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        print("Using cached track data")
        return cached_data
    
    print("Extracting tracks from your playlists...")
    
    # Dictionary to store track info by ID
    tracks = {}
    
    # Dictionary to track which playlists each track appears in
    track_playlists = defaultdict(list)
    
    # Set up progress tracking
    try:
        from tqdm import tqdm
        playlists_iter = tqdm(playlists, desc="Processing playlists", unit="playlist")
    except ImportError:
        print(f"Processing {len(playlists)} playlists...")
        playlists_iter = playlists
    
    # Process each playlist
    for playlist in playlists_iter:
        playlist_id = playlist['id']
        playlist_name = playlist['name']
        
        # Get all tracks in the playlist
        playlist_tracks = []
        offset = 0
        limit = 100  # Maximum allowed by Spotify API
        
        while True:
            results = sp.playlist_items(
                playlist_id,
                fields='items(track(id,name,artists(name),album(name))),total',
                limit=limit,
                offset=offset
            )
            
            playlist_tracks.extend(results['items'])
            
            if len(results['items']) < limit:
                break
            
            offset += limit
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.1)
        
        # Process tracks in this playlist
        for item in playlist_tracks:
            # Skip null tracks or episodes
            if not item['track'] or item['track']['id'] is None:
                continue
            
            track_id = item['track']['id']
            
            # Store track info if we haven't seen it before
            if track_id not in tracks:
                tracks[track_id] = {
                    'id': track_id,
                    'name': item['track']['name'],
                    'artists': [artist['name'] for artist in item['track']['artists']],
                    'album': item['track']['album']['name']
                }
            
            # Record that this track appears in this playlist
            track_playlists[track_id].append(playlist_name)
    
    # Add playlist info to each track
    for track_id, playlists in track_playlists.items():
        if track_id in tracks:
            tracks[track_id]['playlists'] = playlists
    
    print(f"Found {len(tracks)} unique tracks across all playlists")
    
    # Save to cache
    save_to_cache(list(tracks.values()), cache_key)
    
    return list(tracks.values())

def get_saved_tracks(sp):
    """Get all tracks the user has already saved (liked)."""
    # Try to load from cache
    cache_key = "saved_tracks"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        print("Using cached saved tracks data")
        return cached_data
    
    print("Fetching your saved tracks...")
    
    saved_tracks = set()
    offset = 0
    limit = 50  # Maximum allowed by Spotify API
    
    while True:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        
        for item in results['items']:
            saved_tracks.add(item['track']['id'])
        
        if len(results['items']) < limit:
            break
        
        offset += limit
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.1)
    
    print(f"You have {len(saved_tracks)} saved tracks")
    
    # Save to cache
    save_to_cache(list(saved_tracks), cache_key)
    
    return saved_tracks

def like_tracks(sp, tracks, saved_tracks):
    """Like tracks that the user hasn't already saved."""
    # Filter out tracks already saved
    new_tracks = [t for t in tracks if t['id'] not in saved_tracks]
    
    if not new_tracks:
        print("You have already liked all tracks from your playlists!")
        return
    
    print(f"Found {len(new_tracks)} new tracks to like")
    
    # Ask for confirmation
    confirm = input(f"Do you want to like these {len(new_tracks)} tracks? (y/n): ")
    
    if confirm.lower() != 'y':
        print("Operation cancelled")
        return
    
    # Set up progress tracking
    try:
        from tqdm import tqdm
        tracks_iter = tqdm(new_tracks, desc="Liking tracks", unit="track")
    except ImportError:
        print(f"Liking {len(new_tracks)} tracks...")
        tracks_iter = new_tracks
    
    # Like tracks in batches of 50 (Spotify API limit)
    batch_size = 50
    for i in range(0, len(new_tracks), batch_size):
        batch = new_tracks[i:i+batch_size]
        track_ids = [t['id'] for t in batch]
        
        try:
            sp.current_user_saved_tracks_add(track_ids)
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.5)
        except Exception as e:
            print(f"Error liking tracks: {e}")
            print("Continuing with next batch...")
    
    print(f"Successfully liked {len(new_tracks)} new tracks!")
    
    # Invalidate the saved tracks cache
    save_to_cache(None, "saved_tracks", expire=True)

def main():
    """Main function to run the script."""
    print("Spotify Like Songs")
    print("=================")
    
    # Set up Spotify client
    sp = setup_spotify_client()
    
    # Get user playlists
    playlists = get_user_playlists(sp)
    
    # Get tracks from playlists
    tracks = get_tracks_from_playlists(sp, playlists)
    
    # Get saved tracks
    saved_tracks = get_saved_tracks(sp)
    
    # Like new tracks
    like_tracks(sp, tracks, saved_tracks)

if __name__ == "__main__":
    main()
