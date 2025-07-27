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
from spotify_utils import create_spotify_client, print_success, print_error, print_info
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

# Cache expiration (in seconds)
CACHE_EXPIRATION = 24 * 60 * 60  # 24 hours

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
    """Get all user's liked songs."""
    # Try to load from cache
    cache_key = "liked_songs"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        print_success(f"Found {len(cached_data)} liked songs (from cache)")
        return cached_data
    
    print_info("Fetching your liked songs...")
    
    liked_songs = []
    offset = 0
    limit = 50
    
    # First request to get total count
    results = sp.current_user_saved_tracks(limit=1)
    total_tracks = results['total']
    
    if total_tracks == 0:
        print_warning("You don't have any liked songs.")
        return []
    
    # Create progress bar
    progress_bar = create_progress_bar(total=total_tracks, desc="Fetching liked songs", unit="song")
    
    while True:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        
        if not results['items']:
            break
        
        # Extract track information
        for item in results['items']:
            track = item['track']
            if track:  # Make sure track is not None
                track_info = {
                    'id': track['id'],
                    'name': track['name'],
                    'artists': [artist['name'] for artist in track['artists']],
                    'album': track['album']['name'],
                    'added_at': item['added_at']
                }
                liked_songs.append(track_info)
        
        # Update progress bar
        update_progress_bar(progress_bar, len(results['items']))
        
        offset += len(results['items'])
        
        if len(results['items']) < limit:
            break
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.1)
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    print_success(f"Found {len(liked_songs)} liked songs")
    
    # Cache the results
    save_to_cache(liked_songs, cache_key)
    
    return liked_songs

def get_christmas_playlists(sp):
    """Get user's Christmas-related playlists."""
    print_info("Scanning your playlists for Christmas-related ones...")
    
    playlists = []
    offset = 0
    limit = 50
    
    user = sp.current_user()
    user_id = user['id']
    
    while True:
        results = sp.current_user_playlists(limit=limit, offset=offset)
        
        if not results['items']:
            break
        
        # Filter for user's own playlists that might be Christmas-related
        for playlist in results['items']:
            if playlist['owner']['id'] == user_id:
                playlist_name = playlist['name'].lower()
                if any(keyword in playlist_name for keyword in ['christmas', 'xmas', 'holiday', 'winter']):
                    playlists.append(playlist)
        
        offset += len(results['items'])
        
        if len(results['items']) < limit:
            break
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.1)
    
    if playlists:
        print_success(f"Found {len(playlists)} Christmas-related playlists:")
        for playlist in playlists:
            print(f"  • {playlist['name']} ({playlist['tracks']['total']} tracks)")
    else:
        print_info("No Christmas-related playlists found.")
    
    return playlists

def get_playlist_tracks(sp, playlist_id):
    """Get all tracks from a playlist."""
    tracks = []
    offset = 0
    limit = 100
    
    while True:
        results = sp.playlist_items(
            playlist_id,
            fields='items(track(id,name,artists,album)),total',
            limit=limit,
            offset=offset
        )
        
        # Extract track info
        for item in results['items']:
            if item['track'] and item['track']['id']:
                track_info = {
                    'id': item['track']['id'],
                    'name': item['track']['name'],
                    'artists': [artist['name'] for artist in item['track']['artists']],
                    'album': item['track']['album']['name']
                }
                tracks.append(track_info)
        
        offset += limit
        
        if len(results['items']) < limit:
            break
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.1)
    
    return tracks

def is_christmas_song(track):
    """Check if a track is Christmas-related based on title, artist, or album."""
    # Combine all text to search
    search_text = f"{track['name']} {' '.join(track['artists'])} {track['album']}".lower()
    
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
                playlist_track_ids.add(track['id'])
    
    # Check each liked song
    for track in liked_songs:
        # Check if it's in a Christmas playlist
        if track['id'] in playlist_track_ids:
            track['reason'] = 'Found in Christmas playlist'
            christmas_songs.append(track)
        # Check if it contains Christmas keywords
        elif is_christmas_song(track):
            track['reason'] = 'Contains Christmas keywords'
            christmas_songs.append(track)
    
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
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.5)
            
        except Exception as e:
            print_error(f"Error removing batch of songs: {e}")
            # Still update progress bar for failed batch
            update_progress_bar(progress_bar, len(batch))
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    print_success(f"Successfully removed {removed_count} Christmas songs from your liked songs.")
    
    # Clear the liked songs cache
    save_to_cache(None, "liked_songs", force_expire=True)

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
    christmas_songs = identify_christmas_songs(liked_songs, christmas_playlists, sp)
    
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