#!/usr/bin/env python3
"""
Script to follow all artists in your Spotify playlists.
This script uses the Spotify Web API to:
1. Authenticate with your Spotify account
2. Fetch all playlists you've created
3. Extract unique artists from those playlists
4. Follow all those artists

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

# Import colorama for colored output
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Import print functions from spotify_utils
from spotify_utils import print_warning, print_info, print_success, print_error, print_header

# Spotify API scopes needed for this script
SCOPES = [
    "user-library-read",
    "playlist-read-private",
    "user-follow-modify"
]

# Cache expiration (in seconds)
CACHE_EXPIRATION = 24 * 60 * 60  # 24 hours

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    from spotify_utils import create_spotify_client
    
    try:
        return create_spotify_client(SCOPES, "follow_artists")
    except Exception as e:
        print_error(f"Failed to set up Spotify client: {e}")
        sys.exit(1)

def get_user_playlists(sp):
    """Get all playlists created by the current user."""
    # Try to load from cache
    cache_key = "user_playlists"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        print("Using cached playlist data")
        return cached_data
    
    print("Fetching your playlists...")
    
    # Get current user ID
    user_id = sp.current_user()['id']
    
    # Get all playlists
    playlists = []
    offset = 0
    limit = 50  # Maximum allowed by Spotify API
    
    while True:
        results = sp.current_user_playlists(limit=limit, offset=offset)
        
        if not results['items']:
            break
        
        # Filter for playlists created by the user
        user_playlists = [p for p in results['items'] if p['owner']['id'] == user_id]
        playlists.extend(user_playlists)
        
        if len(results['items']) < limit:
            break
        
        offset += limit
    
    print(f"Found {len(playlists)} playlists that you've created")
    
    # Save to cache
    save_to_cache(playlists, cache_key)
    
    return playlists

def get_artists_from_playlists(sp, playlists):
    """Extract all unique artists from the given playlists."""
    # Try to load from cache
    cache_key = "playlist_artists"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        print("Using cached artist data")
        return cached_data
    
    print("Extracting artists from your playlists...")
    
    # Dictionary to store artist info by ID
    artists = {}
    
    # Dictionary to track which playlists each artist appears in
    artist_playlists = defaultdict(list)
    
    # Set up progress tracking
    total_playlists = len(playlists)
    
    # Import tqdm for progress bar
    try:
        from tqdm import tqdm
        playlists_iter = tqdm(playlists, desc="Processing playlists", unit="playlist")
    except ImportError:
        print(f"Processing {total_playlists} playlists...")
        playlists_iter = playlists
    
    # Process each playlist
    for i, playlist in enumerate(playlists_iter):
        playlist_id = playlist['id']
        playlist_name = playlist['name']
        
        # Get all tracks in the playlist
        tracks = []
        offset = 0
        limit = 100  # Maximum allowed by Spotify API
        
        while True:
            results = sp.playlist_items(
                playlist_id,
                fields='items(track(artists)),total',
                limit=limit,
                offset=offset
            )
            
            tracks.extend(results['items'])
            
            if len(results['items']) < limit:
                break
            
            offset += limit
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.1)
        
        # Extract artists from tracks
        for item in tracks:
            if not item['track'] or not item['track']['artists']:
                continue
            
            for artist in item['track']['artists']:
                artist_id = artist['id']
                artist_name = artist['name']
                
                # Store artist info
                artists[artist_id] = {
                    'id': artist_id,
                    'name': artist_name
                }
                
                # Track which playlist this artist appears in
                if playlist_name not in artist_playlists[artist_id]:
                    artist_playlists[artist_id].append(playlist_name)
    
    # Add playlist information to each artist
    for artist_id, playlists in artist_playlists.items():
        if artist_id in artists:
            artists[artist_id]['playlists'] = playlists
    
    # Convert to list
    artist_list = list(artists.values())
    
    print(f"Found {len(artist_list)} unique artists across all playlists")
    
    # Save to cache
    save_to_cache(artist_list, cache_key)
    
    return artist_list

def get_followed_artists(sp):
    """Get a list of artists the user is already following."""
    # Try to load from cache
    cache_key = "followed_artists"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        print("Using cached followed artists data")
        return cached_data
    
    print("Fetching artists you already follow...")
    
    followed_artists = set()
    after = None
    
    while True:
        results = sp.current_user_followed_artists(limit=50, after=after)
        
        for artist in results['artists']['items']:
            followed_artists.add(artist['id'])
        
        if not results['artists']['next']:
            break
        
        after = results['artists']['cursors']['after']
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.1)
    
    print(f"You are currently following {len(followed_artists)} artists")
    
    # Save to cache
    save_to_cache(list(followed_artists), cache_key)
    
    return followed_artists

def follow_artists(sp, artists, followed_artists):
    """Follow artists that the user isn't already following."""
    # Filter out artists already being followed
    new_artists = [a for a in artists if a['id'] not in followed_artists]
    
    if not new_artists:
        print("You are already following all artists from your playlists!")
        return
    
    print(f"Found {len(new_artists)} new artists to follow")
    
    # Check for low-follower artists
    low_follower_threshold = 10
    low_follower_artists = [a for a in new_artists if a['followers']['total'] <= low_follower_threshold]
    
    if low_follower_artists:
        print_warning(f"\nFound {len(low_follower_artists)} artists with {low_follower_threshold} or fewer followers:")
        for i, artist in enumerate(low_follower_artists[:10], 1):
            followers = artist['followers']['total']
            print(f"  {i}. {artist['name']} ({followers} followers)")
        
        if len(low_follower_artists) > 10:
            print(f"  ... and {len(low_follower_artists) - 10} more")
        
        # Ask if user wants to follow low-follower artists
        follow_low = input(f"\nDo you want to follow artists with {low_follower_threshold} or fewer followers? (y/n): ").strip().lower()
        
        if follow_low != 'y':
            # Remove low-follower artists from the list
            new_artists = [a for a in new_artists if a['followers']['total'] > low_follower_threshold]
            print_info(f"Excluding {len(low_follower_artists)} low-follower artists. {len(new_artists)} artists remaining.")
            
            if not new_artists:
                print_warning("No artists left to follow after excluding low-follower artists.")
                return
    
    # Ask for confirmation
    confirm = input(f"Do you want to follow these {len(new_artists)} artists? (y/n): ")
    
    if confirm.lower() != 'y':
        print("Operation cancelled")
        return
    
    # Set up progress tracking
    try:
        from tqdm import tqdm
        artists_iter = tqdm(new_artists, desc="Following artists", unit="artist")
    except ImportError:
        print(f"Following {len(new_artists)} artists...")
        artists_iter = new_artists
    
    # Follow artists in batches of 50 (Spotify API limit)
    batch_size = 50
    for i in range(0, len(new_artists), batch_size):
        batch = new_artists[i:i+batch_size]
        artist_ids = [a['id'] for a in batch]
        
        try:
            sp.user_follow_artists(artist_ids)
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.5)
        except Exception as e:
            print(f"Error following artists: {e}")
            print("Continuing with next batch...")
    
    print(f"Successfully followed {len(new_artists)} new artists!")
    
    # Clear the followed artists cache since it's now outdated
    save_to_cache(list(followed_artists) + [a['id'] for a in new_artists], "followed_artists")

def main():
    """Main function to run the script."""
    print("Spotify Follow Artists")
    print("======================")
    
    # Set up Spotify client
    sp = setup_spotify_client()
    
    # Get user playlists
    playlists = get_user_playlists(sp)
    
    # Get artists from playlists
    artists = get_artists_from_playlists(sp, playlists)
    
    # Get followed artists
    followed_artists = get_followed_artists(sp)
    
    # Follow new artists
    follow_artists(sp, artists, followed_artists)

if __name__ == "__main__":
    main()
