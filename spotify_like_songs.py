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
from exclusion_manager import is_excluded, add_bulk_exclusions, get_exclusion_count
from spotify_utils import (
    create_spotify_client, COMMON_SCOPES, print_success, print_error, print_warning, print_info,
    fetch_user_playlists, fetch_user_saved_tracks, fetch_playlist_tracks
)
from constants import DEFAULT_CACHE_EXPIRATION, MENU_ICONS, BOX_CHARS
from print_utils import print_box_header, print_section_header, print_menu_item

# Import tqdm_utils for progress bars
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

# Spotify API scopes needed for this script
SCOPES = [
    "user-library-read",
    "user-library-modify",
    "playlist-read-private"
]

# Import cache expiration from constants
from constants import STANDARD_CACHE_KEYS
from preferences_manager import get_cache_duration_seconds

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        return create_spotify_client(SCOPES, "like_songs")
    except Exception as e:
        print(f"Error setting up Spotify client: {e}")
        sys.exit(1)

def get_user_playlists(sp):
    """Get all playlists created by the current user."""
    from spotify_utils import fetch_user_playlists
    
    # Fetch all playlists with progress bar
    all_playlists = fetch_user_playlists(sp, show_progress=True, cache_key=STANDARD_CACHE_KEYS['user_playlists'], cache_expiration=get_cache_duration_seconds())
    
    # Filter to only include playlists created by the user
    user_id = sp.current_user()['id']
    user_playlists = [p for p in all_playlists if p['owner']['id'] == user_id]
    
    print(f"Found {len(user_playlists)} playlists that you've created")
    return user_playlists

def get_tracks_from_playlists(sp, playlists):
    """Extract all unique tracks from the given playlists using centralized functions."""
    # Try to load from cache
    cache_key = "playlist_tracks"
    cached_data = load_from_cache(cache_key, DEFAULT_CACHE_EXPIRATION)
    
    if cached_data:
        print("Using cached track data")
        return cached_data
    
    print("Extracting tracks from your playlists...")
    
    # Dictionary to store track info by ID
    tracks = {}
    
    # Dictionary to track which playlists each track appears in
    track_playlists = defaultdict(list)
    
    # Set up progress tracking using centralized utilities
    
    progress_bar = create_progress_bar(total=len(playlists), desc="Processing playlists", unit="playlist")
    
    # Process each playlist
    for playlist in playlists:
        playlist_id = playlist['id']
        playlist_name = playlist['name']
        
        # Use centralized function to get playlist tracks
        playlist_items = fetch_playlist_tracks(
            sp,
            playlist_id,
            show_progress=False,  # Don't show individual progress per playlist
            cache_key=f"playlist_tracks_{playlist_id}",
            cache_expiration=get_cache_duration_seconds()
        )
        
        # Process tracks in this playlist
        for item in playlist_items:
            # Handle potential cache corruption where item is not a dict
            if not isinstance(item, dict):
                print_warning(f"Skipping corrupted item in playlist '{playlist_name}': {item}")
                continue

            # Skip null tracks or episodes
            if not item.get('track') or not item['track'].get('id'):
                continue
            
            track = item['track']
            track_id = track['id']
            
            # Store track info if we haven't seen it before
            if track_id not in tracks:
                tracks[track_id] = {
                    'id': track_id,
                    'name': track['name'],
                    # Keep full artist objects with id, name, uri for downstream processing
                    'artists': track.get('artists', []),
                    'album': track['album']['name'] if track.get('album') else 'Unknown Album'
                }
            
            # Record that this track appears in this playlist
            track_playlists[track_id].append(playlist_name)
        
        # Update progress bar
        update_progress_bar(progress_bar, 1)
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    # Add playlist info to each track
    for track_id, playlists_list in track_playlists.items():
        if track_id in tracks:
            tracks[track_id]['playlists'] = playlists_list
    
    print(f"Found {len(tracks)} unique tracks across all playlists")
    
    # Save to cache
    save_to_cache(list(tracks.values()), cache_key)
    
    return list(tracks.values())

def get_saved_tracks(sp):
    """Get all tracks the user has already saved (liked)."""
    from spotify_utils import fetch_user_saved_tracks
    
    # Fetch saved tracks with progress bar - use same cache key as other scripts
    saved_tracks_data = fetch_user_saved_tracks(sp, show_progress=True, cache_key=STANDARD_CACHE_KEYS['liked_songs'], cache_expiration=get_cache_duration_seconds())
    
    # Convert to set of track IDs for efficient lookup
    saved_tracks = {item['track']['id'] for item in saved_tracks_data if item['track']}
    
    print(f"You have {len(saved_tracks)} saved tracks")
    return saved_tracks

def like_tracks(sp, tracks, saved_tracks):
    """Like tracks that the user hasn't already saved."""
    # Filter out tracks already saved
    new_tracks = [t for t in tracks if t['id'] not in saved_tracks]

    # Filter out excluded tracks
    excluded_count = 0
    filtered_tracks = []
    for track in new_tracks:
        if is_excluded(track['id'], 'track'):
            excluded_count += 1
        else:
            filtered_tracks.append(track)

    new_tracks = filtered_tracks

    if excluded_count > 0:
        print_warning(f"Skipped {excluded_count} tracks in exclusion list")

    if not new_tracks:
        print("You have already liked all tracks from your playlists!")
        return []
    
    print(f"Found {len(new_tracks)} new tracks to like")
    
    # Ask for confirmation
    confirm = input(f"Do you want to like these {len(new_tracks)} tracks? (y/n): ")
    
    if confirm.lower() != 'y':
        print("Operation cancelled")
        return []
    
    # Set up progress tracking using centralized utilities
    progress_bar = create_progress_bar(total=len(new_tracks), desc="Liking tracks", unit="track")

    # Like tracks in batches of 50 (Spotify API limit)
    batch_size = 50
    successfully_liked = 0
    failed_tracks = 0

    for i in range(0, len(new_tracks), batch_size):
        batch = new_tracks[i:i+batch_size]
        track_ids = [t['id'] for t in batch]

        try:
            sp.current_user_saved_tracks_add(track_ids)
            successfully_liked += len(batch)

            # Update progress bar
            update_progress_bar(progress_bar, len(batch))

            # SafeSpotifyClient handles rate limiting automatically
        except Exception as e:
            print_error(f"\nError liking batch of {len(batch)} tracks: {e}")
            failed_tracks += len(batch)
            # Still update progress even on error
            update_progress_bar(progress_bar, len(batch))

    # Close progress bar
    close_progress_bar(progress_bar)

    # Report results
    if failed_tracks > 0:
        print_warning(f"Successfully liked {successfully_liked} tracks, {failed_tracks} failed")
    else:
        print_success(f"Successfully liked {successfully_liked} new tracks!")

    # Invalidate the saved tracks cache
    save_to_cache(None, STANDARD_CACHE_KEYS['liked_songs'], force_expire=True)
    
    return new_tracks

def is_christmas_song(track):
    """Check if a track is Christmas-related based on title, artist, or album."""
    # Christmas-related keywords and phrases
    christmas_keywords = [
        'christmas', 'xmas', 'holiday', 'santa', 'reindeer', 'jingle', 'bells',
        'winter wonderland', 'silent night', 'deck the halls', 'joy to the world',
        'white christmas', 'let it snow', 'sleigh', 'mistletoe', 'holly', 'noel',
        'rudolph', 'frosty', 'snowman', 'feliz navidad', 'merry', 'yuletide',
        'advent', 'nativity', 'bethlehem', 'peace on earth', 'goodwill', 'sleigh ride',
        'winter song', 'holiday song', 'christmas song', 'xmas song', 'carol'
    ]

    # Combine all text to search
    # Extract artist names from artist objects
    artist_names = ' '.join([artist['name'] for artist in track.get('artists', [])])
    search_text = f"{track['name']} {artist_names} {track['album']}".lower()

    # Check for Christmas keywords
    for keyword in christmas_keywords:
        if keyword in search_text:
            return True

    return False

def filter_christmas_songs(tracks, exclude_christmas=False):
    """Filter out Christmas songs if requested."""
    if not exclude_christmas:
        return tracks
    
    print("Filtering out Christmas songs...")
    
    # Count original tracks
    original_count = len(tracks)
    
    # Filter out Christmas songs
    filtered_tracks = []
    christmas_count = 0
    
    for track_info in tracks:
        if is_christmas_song(track_info):
            christmas_count += 1
        else:
            filtered_tracks.append(track_info)
    
    print(f"Filtered out {christmas_count} Christmas songs from {original_count} total tracks")
    print(f"Remaining: {len(filtered_tracks)} tracks")
    
    return filtered_tracks

def main():
    """Main function to run the script."""
    print_box_header("Add Songs to Liked Songs", icon=MENU_ICONS['heart'])

    # Ask user about Christmas filtering
    print_section_header("OPTIONS")
    print_menu_item(1, "Add all songs from playlists (including Christmas songs)")
    print_menu_item(2, "Add all songs except Christmas songs")
    print("")
    print_menu_item(3, "Back to main menu", icon=BOX_CHARS['arrow'])

    while True:
        choice = input(f"\n{BOX_CHARS['arrow']} Enter your choice (1-3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print_warning("Please enter 1, 2, or 3")

    # Return to main menu if requested
    if choice == '3':
        return
    
    exclude_christmas = (choice == '2')
    
    if exclude_christmas:
        print("🎄 Christmas song filtering enabled - Christmas songs will be excluded")
    else:
        print("🎄 Christmas song filtering disabled - all songs will be included")
    
    # Set up Spotify client
    sp = setup_spotify_client()
    
    # Get user playlists
    playlists = get_user_playlists(sp)
    
    # Get tracks from playlists
    tracks = get_tracks_from_playlists(sp, playlists)
    
    # Filter Christmas songs if requested
    tracks = filter_christmas_songs(tracks, exclude_christmas)
    
    # Get saved tracks
    saved_tracks = get_saved_tracks(sp)
    
    # Like new tracks
    like_tracks(sp, tracks, saved_tracks)

    # Pause before returning to main menu
    input("\nPress Enter to return to main menu...")

if __name__ == "__main__":
    main()