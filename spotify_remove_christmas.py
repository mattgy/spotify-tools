#!/usr/bin/env python3
"""
Script to remove Christmas songs from Liked Songs.

This script:
1. Authenticates with your Spotify account
2. Scans your Liked Songs for Christmas-related tracks
3. Identifies songs from Christmas playlists you've created
4. Allows you to remove them in bulk

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import time
import re
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from spotify_utils import (
    create_spotify_client, print_success, print_error, print_info,
    fetch_user_saved_tracks, fetch_user_playlists, fetch_playlist_tracks
)
from cache_utils import load_from_cache, save_to_cache
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

# Import colorama for colored output
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Spotify API scopes needed for this script
SCOPES = [
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "user-read-email",
    "user-read-private"
]

# Import cache expiration from constants
from constants import DEFAULT_CACHE_EXPIRATION, STANDARD_CACHE_KEYS

# Christmas-related keywords and phrases
CHRISTMAS_KEYWORDS = [
    'christmas', 'xmas', 'holiday', 'santa', 'reindeer', 'jingle', 'bells',
    'winter wonderland', 'silent night', 'deck the halls', 'joy to the world',
    'white christmas', 'let it snow', 'sleigh', 'mistletoe', 'holly', 'noel',
    'rudolph', 'frosty', 'snowman', 'feliz navidad', 'merry', 'yuletide',
    'advent', 'nativity', 'bethlehem', 'peace on earth', 'goodwill', 'sleigh ride',
    'winter song', 'holiday song', 'christmas song', 'xmas song', 'carol'
]

# Import print functions from spotify_utils
from spotify_utils import print_header, print_warning, print_success, print_error, print_info

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        sp = create_spotify_client(SCOPES, "remove_christmas")
        
        # Test the connection and show user info
        user = sp.current_user()
        print_success(f"Authenticated as: {user['display_name']} ({user.get('email', 'email not available')})")
        
        return sp
    except Exception as e:
        print_error(f"Error setting up Spotify client: {e}")
        sys.exit(1)

def get_user_liked_songs(sp):
    """Get all user's liked songs using centralized fetch function."""
    # Use the centralized function which handles caching, progress, and rate limiting
    tracks = fetch_user_saved_tracks(
        sp, 
        show_progress=True, 
        cache_key=STANDARD_CACHE_KEYS['liked_songs'],
        cache_expiration=DEFAULT_CACHE_EXPIRATION
    )
    
    # Transform to expected format for this script
    liked_songs = []
    for item in tracks:
        track = item.get('track')
        if not track:
            continue
            
        # Skip tracks without valid IDs (podcasts, local files, unavailable tracks)
        if not track.get('id'):
            continue
            
        # Skip tracks with missing required fields
        if not track.get('name') or not track.get('artists') or not track.get('album'):
            continue
            
        # Ensure artists is a list and has at least one entry
        if not isinstance(track['artists'], list) or len(track['artists']) == 0:
            continue
            
        try:
            track_info = {
                'id': track['id'],
                'name': track['name'],
                'artists': [artist['name'] for artist in track['artists'] if artist and artist.get('name')],
                'album': track['album']['name'] if track['album'] else 'Unknown Album',
                'added_at': item.get('added_at', '')
            }
            
            # Only add if we have at least one valid artist
            if track_info['artists']:
                liked_songs.append(track_info)
                
        except (KeyError, TypeError, AttributeError) as e:
            # Skip tracks with malformed data
            continue
    
    print_success(f"Processed {len(liked_songs)} valid liked songs")
    return liked_songs

def get_christmas_playlists(sp):
    """Get user's Christmas-related playlists using centralized fetch function."""
    print_info("Scanning your playlists for Christmas-related ones...")
    
    user = sp.current_user()
    user_id = user['id']
    
    # Use centralized function to get all playlists
    all_playlists = fetch_user_playlists(
        sp,
        show_progress=False,  # Don't show progress for this scan
        cache_key="user_playlists",
        cache_expiration=DEFAULT_CACHE_EXPIRATION
    )
    
    # Filter for user's own playlists that might be Christmas-related
    playlists = []
    for playlist in all_playlists:
        if playlist['owner']['id'] == user_id:
            playlist_name = playlist['name'].lower()
            if any(keyword in playlist_name for keyword in ['christmas', 'xmas', 'holiday', 'winter']):
                playlists.append(playlist)
    
    if playlists:
        print_success(f"Found {len(playlists)} Christmas-related playlists:")
        for playlist in playlists:
            print(f"  • {playlist['name']} ({playlist['tracks']['total']} tracks)")
    else:
        print_info("No Christmas-related playlists found.")
    
    return playlists

def get_playlist_tracks(sp, playlist_id):
    """Get all tracks from a playlist using centralized fetch function."""
    # Use centralized function which handles caching, progress, and rate limiting
    playlist_items = fetch_playlist_tracks(
        sp,
        playlist_id,
        show_progress=False,  # Don't show progress for individual playlists
        cache_key=f"playlist_tracks_{playlist_id}",
        cache_expiration=DEFAULT_CACHE_EXPIRATION
    )
    
    # Transform to expected format for this script
    tracks = []
    for item in playlist_items:
        if item and item.get('track') and item['track'].get('id'):
            track = item['track']
            track_info = {
                'id': track['id'],
                'name': track['name'],
                'artists': [artist['name'] for artist in track.get('artists', [])],
                'album': track['album']['name'] if track.get('album') else 'Unknown Album'
            }
            tracks.append(track_info)
    
    return tracks

def is_christmas_song(track):
    """Check if a track is Christmas-related based on title, artist, or album."""
    # Handle corrupted cache data
    if not isinstance(track, dict):
        return False
    
    # Safely get track information with defaults
    track_name = track.get('name', '')
    track_artists = track.get('artists', [])
    track_album = track.get('album', '')
    
    # Handle case where artists might be strings instead of list
    if isinstance(track_artists, str):
        artists_text = track_artists
    elif isinstance(track_artists, list):
        # Handle mixed data types in artists list
        artist_names = []
        for artist in track_artists:
            if isinstance(artist, str):
                artist_names.append(artist)
            elif isinstance(artist, dict) and 'name' in artist:
                artist_names.append(artist['name'])
        artists_text = ' '.join(artist_names)
    else:
        artists_text = ''
    
    # Combine all text to search
    search_text = f"{track_name} {artists_text} {track_album}".lower()
    
    # Check for Christmas keywords
    for keyword in CHRISTMAS_KEYWORDS:
        if keyword in search_text:
            return True
    
    return False

def identify_christmas_songs(liked_songs, christmas_playlists, sp):
    """Identify Christmas songs in liked songs."""
    print_info("Identifying Christmas songs in your liked songs...")
    
    christmas_songs = []
    
    # Get tracks from Christmas playlists
    playlist_track_ids = set()
    if christmas_playlists:
        print_info("Getting tracks from Christmas playlists...")
        for playlist in christmas_playlists:
            tracks = get_playlist_tracks(sp, playlist['id'])
            for track in tracks:
                # Handle corrupted cache data - skip tracks missing required fields
                if not isinstance(track, dict):
                    print_warning(f"Skipping non-dict playlist track data: {type(track)}")
                    continue
                    
                track_id = track.get('id')
                if track_id:
                    playlist_track_ids.add(track_id)
                else:
                    print_warning(f"Skipping playlist track with missing ID: {track.get('name', 'Unknown')}")
    
    # Check each liked song
    skipped_count = 0
    for track in liked_songs:
        # Handle corrupted cache data - skip tracks missing required fields
        if not isinstance(track, dict):
            skipped_count += 1
            continue
            
        # Check for required fields - silently skip problematic tracks
        track_id = track.get('id')
        if not track_id:
            skipped_count += 1
            continue
            
        # Ensure other required fields exist for Christmas detection
        if not track.get('name'):
            skipped_count += 1
            continue
        
        # Check if it's in a Christmas playlist
        if track_id in playlist_track_ids:
            track['reason'] = 'Found in Christmas playlist'
            christmas_songs.append(track)
        # Check if it contains Christmas keywords
        elif is_christmas_song(track):
            track['reason'] = 'Contains Christmas keywords'
            christmas_songs.append(track)
    
    # Inform user about skipped tracks if there were many
    if skipped_count > 0:
        if skipped_count > 10:
            print_info(f"Skipped {skipped_count} tracks with missing/invalid data (podcasts, local files, etc.)")
            # If we skipped a lot of tracks, the cache might be corrupted - clear it
            if skipped_count > 50:
                print_warning("Many tracks had invalid data - clearing liked songs cache for next run")
                from cache_utils import save_to_cache
                from constants import STANDARD_CACHE_KEYS
                save_to_cache(None, STANDARD_CACHE_KEYS['liked_songs'], force_expire=True)
        elif skipped_count > 0:
            print_info(f"Skipped {skipped_count} tracks with missing data")
    
    return christmas_songs

def remove_songs_from_liked(sp, songs_to_remove):
    """Remove songs from user's liked songs."""
    if not songs_to_remove:
        print_warning("No songs to remove.")
        return
    
    print_info(f"Removing {len(songs_to_remove)} songs from your liked songs...")
    
    # Create progress bar
    progress_bar = create_progress_bar(total=len(songs_to_remove), desc="Removing songs", unit="song")
    
    # Process in batches of 50 (Spotify API limit)
    batch_size = 50
    removed_count = 0
    
    for i in range(0, len(songs_to_remove), batch_size):
        batch = songs_to_remove[i:i+batch_size]
        track_ids = [song['id'] for song in batch]
        
        try:
            sp.current_user_saved_tracks_delete(track_ids)
            removed_count += len(batch)
            
            # Update progress bar
            update_progress_bar(progress_bar, len(batch))
            
        except Exception as e:
            print_error(f"Error removing batch of songs: {e}")
            # Still update progress bar for failed batch
            update_progress_bar(progress_bar, len(batch))
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    print_success(f"Successfully removed {removed_count} Christmas songs from your liked songs.")
    
    # Clear the liked songs cache
    save_to_cache(None, STANDARD_CACHE_KEYS['liked_songs'], force_expire=True)

def main():
    print_header("Remove Christmas Songs from Liked Songs")
    
    # Set up API client
    print_info("Setting up Spotify client...")
    sp = setup_spotify_client()
    
    # Get user's liked songs
    liked_songs = get_user_liked_songs(sp)
    if not liked_songs:
        return
    
    # Get Christmas playlists
    christmas_playlists = get_christmas_playlists(sp)
    
    # Identify Christmas songs
    try:
        christmas_songs = identify_christmas_songs(liked_songs, christmas_playlists, sp)
    except (KeyError, TypeError, AttributeError) as e:
        print_error(f"Cache corruption detected: {e}")
        print_warning("This may be due to corrupted cache data.")
        print_info("The corrupted cache should be automatically cleaned up.")
        print_info("Try running the script again, or use menu option 9 to manage caches.")
        return
    
    if not christmas_songs:
        print_success("No Christmas songs found in your liked songs!")
        return
    
    print_warning(f"\nFound {len(christmas_songs)} Christmas songs in your liked songs:")
    
    # Group by reason and show examples
    by_reason = {}
    for song in christmas_songs:
        reason = song['reason']
        if reason not in by_reason:
            by_reason[reason] = []
        by_reason[reason].append(song)
    
    for reason, songs in by_reason.items():
        print(f"\n{Fore.YELLOW}📍 {reason}: {len(songs)} songs")
        # Show first 5 examples
        for i, song in enumerate(songs[:5], 1):
            artists_str = ', '.join(song['artists'])
            print(f"   {i}. {song['name']} by {artists_str}")
        if len(songs) > 5:
            print(f"   ... and {len(songs) - 5} more")
    
    # Ask user what to do
    print(f"\n{Fore.WHITE}Options:")
    print("1. Remove all Christmas songs")
    print("2. Remove only songs from Christmas playlists")
    print("3. Remove only songs with Christmas keywords")
    print("4. Review and select manually")
    print("5. Cancel")
    
    choice = input(f"\n{Fore.CYAN}Enter your choice (1-5): ")
    
    songs_to_remove = []
    
    if choice == "1":
        songs_to_remove = christmas_songs
    elif choice == "2":
        songs_to_remove = [s for s in christmas_songs if 'playlist' in s['reason'].lower()]
    elif choice == "3":
        songs_to_remove = [s for s in christmas_songs if 'keywords' in s['reason'].lower()]
    elif choice == "4":
        # Manual selection
        print_info("\nChristmas songs found:")
        for i, song in enumerate(christmas_songs, 1):
            artists_str = ', '.join(song['artists'])
            print(f"{i}. {song['name']} by {artists_str} ({song['reason']})")
        
        selection = input("\nEnter song numbers to remove (comma-separated, or 'all'): ").strip().lower()
        
        if selection == 'all':
            songs_to_remove = christmas_songs
        else:
            try:
                indices = [int(idx.strip()) - 1 for idx in selection.split(",")]
                songs_to_remove = [christmas_songs[idx] for idx in indices if 0 <= idx < len(christmas_songs)]
            except ValueError:
                print_error("Invalid input. Please enter numbers separated by commas.")
                return
    elif choice == "5":
        print_info("Operation cancelled.")
        return
    else:
        print_error("Invalid choice.")
        return
    
    if not songs_to_remove:
        print_warning("No songs selected for removal.")
        return
    
    # Final confirmation
    print_warning(f"\nYou are about to remove {len(songs_to_remove)} songs from your liked songs.")
    confirm = input("Are you sure? This cannot be undone. (y/n): ").strip().lower()
    
    if confirm == 'y':
        remove_songs_from_liked(sp, songs_to_remove)
    else:
        print_info("Operation cancelled.")

if __name__ == "__main__":
    main()