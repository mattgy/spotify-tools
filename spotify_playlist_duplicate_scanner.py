#!/usr/bin/env python3
"""
Spotify Playlist Duplicate Scanner

This script scans for duplicate tracks in playlists that you created.
It performs exact duplicate matching (same track ID) to safely identify
and optionally remove duplicate tracks without any fancy matching algorithms.

Features:
- Scan only user-created playlists
- Find exact duplicate tracks (same Spotify track ID)
- Safe, non-destructive scanning with user confirmation
- Option to auto-remove duplicates
- Progress tracking for large playlists

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import time
from collections import defaultdict, Counter
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from spotify_utils import create_spotify_client, print_success, print_error, print_warning, print_info, print_header
from cache_utils import save_to_cache, load_from_cache
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
from constants import CACHE_EXPIRATION, BATCH_SIZES, SPOTIFY_SCOPES

# Spotify API scopes needed for this script
SCOPES = SPOTIFY_SCOPES['modify']

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        sp = create_spotify_client(SCOPES, "playlist_duplicate_scanner")
        
        if sp:
            # Test the connection
            user = sp.current_user()
            print_success(f"Connected to Spotify as: {user['display_name']}")
            return sp
        else:
            print_error("Failed to authenticate with Spotify.")
            return None
    
    except Exception as e:
        print_error(f"Failed to set up Spotify client: {e}")
        return None

def get_user_created_playlists(sp):
    """Get all playlists created by the current user."""
    from spotify_utils import fetch_user_playlists
    
    # Get current user ID
    user_profile = sp.current_user()
    current_user_id = user_profile['id']
    
    # Fetch all user playlists
    all_playlists = fetch_user_playlists(sp, show_progress=True, cache_key="user_playlists_for_duplicate_scan")
    
    # Filter to only user-created playlists
    user_playlists = [p for p in all_playlists if p['owner']['id'] == current_user_id]
    
    print_success(f"Found {len(user_playlists)} playlists created by you (out of {len(all_playlists)} total)")
    return user_playlists

def get_playlist_tracks_with_details(sp, playlist_id, playlist_name):
    """Get all tracks from a playlist with detailed information."""
    from spotify_utils import fetch_playlist_tracks
    
    # Fetch tracks with progress bar
    tracks = fetch_playlist_tracks(sp, playlist_id, show_progress=False, cache_key=f"playlist_tracks_{playlist_id}")
    
    # Convert to our format with track details
    track_details = []
    for item in tracks:
        if item and item.get('track') and item['track'].get('id'):
            track = item['track']
            track_details.append({
                'track_id': track['id'],
                'name': track['name'],
                'artists': [artist['name'] for artist in track['artists']],
                'album': track['album']['name'],
                'uri': track['uri'],
                'added_at': item.get('added_at', 'Unknown'),
                'playlist_id': playlist_id,
                'playlist_name': playlist_name
            })
    
    return track_details

def find_duplicate_tracks_in_playlist(tracks):
    """Find exact duplicate tracks within a single playlist."""
    track_counts = Counter(track['track_id'] for track in tracks)
    duplicates = {}
    
    for track_id, count in track_counts.items():
        if count > 1:
            # Find all instances of this track
            duplicate_tracks = [track for track in tracks if track['track_id'] == track_id]
            duplicates[track_id] = duplicate_tracks
    
    return duplicates

def scan_playlists_for_duplicates(sp, playlists):
    """Scan all playlists for duplicate tracks."""
    print_info("Scanning playlists for duplicate tracks...")
    
    all_duplicates = {}
    
    # Create progress bar for scanning playlists
    progress_bar = create_progress_bar(len(playlists), "Scanning playlists", "playlist")
    
    for playlist in playlists:
        try:
            playlist_id = playlist['id']
            playlist_name = playlist['name']
            
            # Get tracks for this playlist
            tracks = get_playlist_tracks_with_details(sp, playlist_id, playlist_name)
            
            if tracks:
                # Find duplicates in this playlist
                duplicates = find_duplicate_tracks_in_playlist(tracks)
                
                if duplicates:
                    all_duplicates[playlist_id] = {
                        'playlist': playlist,
                        'duplicates': duplicates,
                        'total_tracks': len(tracks),
                        'duplicate_track_count': sum(len(dup_tracks) - 1 for dup_tracks in duplicates.values())
                    }
            
            update_progress_bar(progress_bar, 1)
            
        except Exception as e:
            print_warning(f"Error scanning playlist {playlist.get('name', 'Unknown')}: {e}")
            update_progress_bar(progress_bar, 1)
            continue
    
    close_progress_bar(progress_bar)
    
    return all_duplicates

def display_duplicate_results(all_duplicates):
    """Display the duplicate scanning results."""
    print_header("Duplicate Track Scan Results")
    
    if not all_duplicates:
        print_success("🎉 No duplicate tracks found in your playlists!")
        return
    
    total_playlists_with_duplicates = len(all_duplicates)
    total_duplicate_tracks = sum(data['duplicate_track_count'] for data in all_duplicates.values())
    
    print(f"Found duplicates in {total_playlists_with_duplicates} playlist(s)")
    print(f"Total duplicate tracks to potentially remove: {total_duplicate_tracks}")
    
    print(f"\n{Fore.YELLOW}Playlists with duplicates:")
    
    for playlist_id, data in all_duplicates.items():
        playlist = data['playlist']
        duplicates = data['duplicates']
        duplicate_count = data['duplicate_track_count']
        total_tracks = data['total_tracks']
        
        print(f"\n{Fore.CYAN}📋 {playlist['name']}")
        print(f"   Total tracks: {total_tracks} | Duplicates to remove: {duplicate_count}")
        
        # Show first few duplicate tracks as examples
        shown_count = 0
        for track_id, duplicate_tracks in duplicates.items():
            if shown_count >= 3:  # Only show first 3 examples
                remaining = len(duplicates) - shown_count
                if remaining > 0:
                    print(f"   ... and {remaining} more duplicate track(s)")
                break
            
            track = duplicate_tracks[0]  # All tracks in this group are the same
            instances = len(duplicate_tracks)
            print(f"   🔄 {' & '.join(track['artists'])} - {track['name']} ({instances} copies)")
            shown_count += 1

def remove_duplicates_from_playlist(sp, playlist_id, duplicates):
    """Remove duplicate tracks from a specific playlist."""
    tracks_to_remove = []
    
    # For each set of duplicates, keep the first (oldest) and remove the rest
    for track_id, duplicate_tracks in duplicates.items():
        # Sort by added_at date, keep the first (oldest)
        sorted_tracks = sorted(duplicate_tracks, key=lambda x: x.get('added_at', ''))
        tracks_to_remove.extend(sorted_tracks[1:])  # Remove all but the first
    
    if not tracks_to_remove:
        return 0
    
    print_info(f"Removing {len(tracks_to_remove)} duplicate tracks from playlist...")
    
    # Remove tracks in batches
    batch_size = BATCH_SIZES['spotify_tracks']
    removed_count = 0
    
    progress_bar = create_progress_bar(len(tracks_to_remove), "Removing duplicates", "track")
    
    for i in range(0, len(tracks_to_remove), batch_size):
        batch = tracks_to_remove[i:i + batch_size]
        
        # Create list of track URIs and positions for removal
        # Note: We need to be careful about positions as they change after each removal
        track_uris = [track['uri'] for track in batch]
        
        try:
            # For playlist track removal, we need to use the track URI format
            sp.playlist_remove_all_occurrences_of_items(playlist_id, track_uris)
            removed_count += len(batch)
            
            # Update progress
            update_progress_bar(progress_bar, len(batch))
            
            # Add delay to avoid rate limiting
            time.sleep(0.2)
            
        except Exception as e:
            print_warning(f"Error removing batch of tracks: {e}")
            update_progress_bar(progress_bar, len(batch))
    
    close_progress_bar(progress_bar)
    
    # Clear the playlist tracks cache since we modified it
    cache_key = f"playlist_tracks_{playlist_id}"
    save_to_cache(None, cache_key, force_expire=True)
    
    return removed_count

def handle_duplicate_removal(sp, all_duplicates):
    """Handle the user's choice for removing duplicates."""
    if not all_duplicates:
        return
    
    print_header("Duplicate Removal Options")
    
    total_duplicates = sum(data['duplicate_track_count'] for data in all_duplicates.values())
    
    print(f"You have {total_duplicates} duplicate tracks across {len(all_duplicates)} playlist(s)")
    print(f"\n{Fore.CYAN}Options:")
    print(f"1. Remove all duplicates automatically (keeps oldest copy of each track)")
    print(f"2. Remove duplicates playlist by playlist (with confirmation)")
    print(f"3. Exit without removing anything")
    
    choice = input(f"\n{Fore.CYAN}Choose option (1-3): ").strip()
    
    if choice == "1":
        # Auto-remove all duplicates
        confirm = input(f"\n{Fore.YELLOW}⚠️  This will remove {total_duplicates} duplicate tracks. Continue? (y/n): ").strip().lower()
        
        if confirm == 'y':
            print_info("Removing all duplicates...")
            total_removed = 0
            
            for playlist_id, data in all_duplicates.items():
                playlist_name = data['playlist']['name']
                duplicates = data['duplicates']
                
                print_info(f"Processing playlist: {playlist_name}")
                removed = remove_duplicates_from_playlist(sp, playlist_id, duplicates)
                total_removed += removed
                
                if removed > 0:
                    print_success(f"Removed {removed} duplicates from '{playlist_name}'")
            
            print_success(f"🎉 Successfully removed {total_removed} duplicate tracks from all playlists!")
        else:
            print_info("Cancelled duplicate removal.")
    
    elif choice == "2":
        # Remove duplicates playlist by playlist
        for playlist_id, data in all_duplicates.items():
            playlist = data['playlist']
            duplicates = data['duplicates']
            duplicate_count = data['duplicate_track_count']
            
            print(f"\n{Fore.CYAN}Playlist: {playlist['name']}")
            print(f"Duplicates to remove: {duplicate_count}")
            
            # Show what would be removed
            for track_id, duplicate_tracks in list(duplicates.items())[:3]:  # Show first 3
                track = duplicate_tracks[0]
                instances = len(duplicate_tracks)
                print(f"  • {' & '.join(track['artists'])} - {track['name']} ({instances} copies)")
            
            confirm = input(f"\nRemove duplicates from this playlist? (y/n): ").strip().lower()
            
            if confirm == 'y':
                removed = remove_duplicates_from_playlist(sp, playlist_id, duplicates)
                if removed > 0:
                    print_success(f"Removed {removed} duplicates from '{playlist['name']}'")
            else:
                print_info(f"Skipped playlist '{playlist['name']}'")
    
    elif choice == "3":
        print_info("Exiting without removing duplicates.")
    
    else:
        print_error("Invalid choice.")

def main():
    """Main function to run the playlist duplicate scanner."""
    print_header("Spotify Playlist Duplicate Scanner")
    print(f"{Fore.CYAN}This tool scans for exact duplicate tracks in playlists you created.")
    print(f"{Fore.CYAN}It only looks at playlists you own and uses safe, exact matching.")
    
    # Set up Spotify client
    sp = setup_spotify_client()
    if not sp:
        return
    
    # Get user-created playlists
    playlists = get_user_created_playlists(sp)
    if not playlists:
        print_warning("You don't have any playlists created yet.")
        return
    
    # Scan for duplicates
    all_duplicates = scan_playlists_for_duplicates(sp, playlists)
    
    # Display results
    display_duplicate_results(all_duplicates)
    
    # Handle removal if duplicates found
    if all_duplicates:
        print(f"\n{Fore.YELLOW}Would you like to remove these duplicates?")
        handle_duplicate_removal(sp, all_duplicates)
    
    print_info("\nDuplicate scan complete!")

if __name__ == "__main__":
    main()