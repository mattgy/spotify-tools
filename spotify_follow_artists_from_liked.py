#!/usr/bin/env python3
"""
Script to follow all artists from your Liked Songs on Spotify.
This script uses the Spotify Web API to:
1. Authenticate with your Spotify account
2. Fetch all your Liked Songs
3. Extract unique artists from those songs
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
    "user-follow-read",
    "user-follow-modify"
]

# Import cache expiration from constants
from constants import STANDARD_CACHE_KEYS, CLEANUP_THRESHOLDS, DEFAULT_CACHE_EXPIRATION, MENU_ICONS
from print_utils import print_box_header
from preferences_manager import get_cache_duration_seconds

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    from spotify_utils import create_spotify_client

    try:
        return create_spotify_client(SCOPES, "follow_artists_from_liked")
    except Exception as e:
        print_error(f"Failed to set up Spotify client: {e}")
        sys.exit(1)

def get_artists_from_liked_songs(sp):
    """Extract all unique artists from the user's Liked Songs."""
    from spotify_utils import fetch_user_saved_tracks
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

    # Try to load from cache first
    cache_key = "liked_songs_artists"
    cached_data = load_from_cache(cache_key, DEFAULT_CACHE_EXPIRATION)

    if cached_data:
        print("Using cached artist data")
        return cached_data

    # Fetch all liked songs
    print_info("Fetching your Liked Songs...")
    saved_tracks = fetch_user_saved_tracks(
        sp,
        show_progress=True,
        cache_key=STANDARD_CACHE_KEYS['liked_songs'],
        cache_expiration=get_cache_duration_seconds()
    )

    print_success(f"Found {len(saved_tracks)} liked songs")

    # Extract unique artists
    print_info("Extracting artists from your Liked Songs...")
    artists_dict = {}

    progress_bar = create_progress_bar(total=len(saved_tracks), desc="Processing songs", unit="song")

    for track_data in saved_tracks:
        track = track_data.get('track')
        if not track:
            continue

        # Get all artists for this track
        for artist in track.get('artists', []):
            artist_id = artist['id']
            if artist_id and artist_id not in artists_dict:
                artists_dict[artist_id] = {
                    'id': artist_id,
                    'name': artist['name'],
                    'uri': artist.get('uri', f'spotify:artist:{artist_id}')
                }

        update_progress_bar(progress_bar, 1)

    close_progress_bar(progress_bar)

    artists = list(artists_dict.values())
    print_success(f"Found {len(artists)} unique artists in your Liked Songs")

    # Save to cache
    save_to_cache(artists, cache_key)

    return artists

def get_followed_artists(sp):
    """Get a list of artists the user is already following."""
    from spotify_utils import fetch_followed_artists
    return fetch_followed_artists(
        sp,
        show_progress=True,
        cache_key=STANDARD_CACHE_KEYS['followed_artists'],
        cache_expiration=get_cache_duration_seconds()
    )

def follow_artists_batch(sp, artist_ids):
    """Follow a batch of artists (max 50 at a time due to API limits)."""
    if not artist_ids:
        return

    # Spotify API allows following up to 50 artists at once
    batch_size = 50

    for i in range(0, len(artist_ids), batch_size):
        batch = artist_ids[i:i + batch_size]
        try:
            sp.user_follow_artists(batch)
            time.sleep(0.1)  # Small delay to avoid rate limiting
        except Exception as e:
            print_error(f"Error following artist batch: {e}")

def main():
    """Main function."""
    print_box_header("Follow Artists from Liked Songs", icon=MENU_ICONS['artist'])

    # Set up Spotify client
    sp = setup_spotify_client()

    # Get artists from liked songs
    artists = get_artists_from_liked_songs(sp)

    if not artists:
        print_warning("No artists found in your Liked Songs")
        return

    # Get already followed artists
    print_info("\nFetching your currently followed artists...")
    followed_artists = get_followed_artists(sp)
    followed_ids = {artist['id'] for artist in followed_artists}
    print_success(f"You're currently following {len(followed_ids)} artists")

    # Filter out excluded artists and already followed artists
    artists_to_follow = []
    excluded_count = 0

    for artist in artists:
        artist_id = artist['id']
        artist_name = artist['name']

        # Skip if excluded
        if is_excluded('artist', artist_id, artist_name):
            excluded_count += 1
            continue

        # Skip if already following
        if artist_id in followed_ids:
            continue

        artists_to_follow.append(artist)

    if excluded_count > 0:
        print_info(f"Skipping {excluded_count} excluded artists")

    # Check if there are any new artists to follow
    if not artists_to_follow:
        print_success("\nYou're already following all artists from your Liked Songs!")
        return

    # Display summary
    print_info(f"\nFound {len(artists_to_follow)} new artists to follow")

    # Ask for confirmation
    print_warning("\nThis will follow all these artists. Continue?")
    response = input("Type 'yes' to continue: ").strip().lower()

    if response != 'yes':
        print_warning("Operation cancelled")
        return

    # Follow the artists
    print_info(f"\nFollowing {len(artists_to_follow)} artists...")
    artist_ids = [artist['id'] for artist in artists_to_follow]
    follow_artists_batch(sp, artist_ids)

    print_success(f"\n✅ Successfully followed {len(artists_to_follow)} artists from your Liked Songs!")

    # Pause before returning to main menu
    input("\nPress Enter to return to main menu...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\n\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
