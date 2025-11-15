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
from exclusion_manager import is_excluded

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

# Import cache expiration from constants
from constants import DEFAULT_CACHE_EXPIRATION, STANDARD_CACHE_KEYS, CLEANUP_THRESHOLDS

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
    from spotify_utils import fetch_user_playlists
    
    # Fetch all playlists
    all_playlists = fetch_user_playlists(sp, show_progress=True, cache_key=STANDARD_CACHE_KEYS['user_playlists'], cache_expiration=DEFAULT_CACHE_EXPIRATION)
    
    # Filter for playlists created by the user
    user_id = sp.current_user()['id']
    user_playlists = [p for p in all_playlists if p['owner']['id'] == user_id]
    
    print(f"Found {len(user_playlists)} playlists that you've created")
    return user_playlists

def get_artists_from_playlists(sp, playlists):
    """Extract all unique artists from the given playlists."""
    from spotify_utils import extract_artists_from_playlists
    
    # Try to load from cache first
    cache_key = "playlist_artists"
    cached_data = load_from_cache(cache_key, DEFAULT_CACHE_EXPIRATION)
    
    if cached_data:
        print("Using cached track data")
        return cached_data
    
    # Extract artists using the reusable function
    artists = extract_artists_from_playlists(playlists, sp, show_progress=True)
    
    # Save to cache
    save_to_cache(artists, cache_key)
    
    return artists

def get_followed_artists(sp):
    """Get a list of artists the user is already following."""
    from spotify_utils import fetch_followed_artists
    return fetch_followed_artists(sp, show_progress=True, cache_key=STANDARD_CACHE_KEYS['followed_artists'], cache_expiration=DEFAULT_CACHE_EXPIRATION)

def follow_artists(sp, artists, followed_artists):
    """Follow artists that the user isn't already following."""
    # Create set of followed artist IDs for efficient lookup
    # Handle case where followed_artists might contain strings instead of dicts
    followed_ids = set()
    for artist in followed_artists:
        if isinstance(artist, dict) and 'id' in artist:
            followed_ids.add(artist['id'])
        elif isinstance(artist, str):
            followed_ids.add(artist)  # Assume it's an artist ID
        else:
            print_warning(f"Invalid artist data: {type(artist)}")
            continue
    
    # Filter out artists already being followed
    new_artists = [a for a in artists if a['id'] not in followed_ids]

    # Filter out excluded artists
    excluded_count = 0
    filtered_artists = []
    for artist in new_artists:
        if is_excluded(artist['id'], 'artist'):
            excluded_count += 1
        else:
            filtered_artists.append(artist)

    new_artists = filtered_artists

    if excluded_count > 0:
        print_warning(f"Skipped {excluded_count} artists in exclusion list")

    if not new_artists:
        print("You are already following all artists from your playlists!")
        return
    
    print(f"Found {len(new_artists)} new artists to follow")

    # Check for low-follower artists (safely handle missing follower data)
    low_follower_threshold = CLEANUP_THRESHOLDS['low_follower_count']
    low_follower_artists = []
    
    # Filter artists that have follower data
    artists_with_followers = [a for a in new_artists if 'followers' in a and a['followers']]
    
    if artists_with_followers:
        low_follower_artists = [a for a in artists_with_followers if a['followers']['total'] <= low_follower_threshold]
    
    # If no artists have follower data, we'll skip the low-follower check
    if not artists_with_followers and len(new_artists) > 100:
        print_info(f"\nNote: Follower data not available for playlist artists. Recommend reviewing the {len(new_artists)} artists manually.")
        # Ask if user wants to fetch detailed artist info for follower checking
        fetch_details = input("Fetch detailed artist info to check follower counts? (This may take a while) (y/n): ").strip().lower()
        
        if fetch_details == 'y':
            # Use batch function for much better efficiency
            from spotify_utils import batch_get_artist_details
            
            # Sample first 50 artists to check for low followers
            sample_artists = new_artists[:50]
            artist_ids = [artist['id'] for artist in sample_artists]
            
            # Batch fetch all artist details at once
            artist_details = batch_get_artist_details(
                sp, 
                artist_ids, 
                show_progress=True, 
                cache_key_prefix="follow_artist_details",
                cache_expiration=7 * 24 * 60 * 60  # 7 days
            )
            
            # Check for low followers
            for artist in sample_artists:
                artist_id = artist['id']
                if artist_id in artist_details:
                    full_artist = artist_details[artist_id]
                    if full_artist and 'followers' in full_artist and full_artist['followers']['total'] <= low_follower_threshold:
                        # Update artist with follower info
                        artist['followers'] = full_artist['followers']
                        low_follower_artists.append(artist)
    
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
    
    # Set up progress tracking using centralized utilities
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    progress_bar = create_progress_bar(total=len(new_artists), desc="Following artists", unit="artist")
    
    # Follow artists in batches of 50 (Spotify API limit)
    batch_size = 50
    followed_count = 0
    
    for i in range(0, len(new_artists), batch_size):
        batch = new_artists[i:i+batch_size]
        artist_ids = [a['id'] for a in batch]
        
        try:
            sp.user_follow_artists(artist_ids)
            followed_count += len(batch)
            
            # Update progress bar with the number of artists in this batch
            update_progress_bar(progress_bar, len(batch))
            
            # SafeSpotifyClient handles rate limiting automatically
        except Exception as e:
            print_error(f"Error following batch of {len(batch)} artists: {e}")
            print_warning("Continuing with next batch...")
            # Still update progress bar even if batch failed
            update_progress_bar(progress_bar, len(batch))
    
    close_progress_bar(progress_bar)
    print_success(f"Successfully followed {followed_count} new artists!")
    
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
