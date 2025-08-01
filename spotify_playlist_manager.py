#!/usr/bin/env python3
"""
Advanced playlist management for Spotify.

This script provides advanced playlist management features including:
- Duplicate track detection and removal
- Playlist cleanup and organization
- Playlist merging and splitting
- Cross-playlist analysis

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import time
import json
import spotipy
from collections import defaultdict, Counter
import difflib
import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform color support
colorama.init(autoreset=True)

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from spotify_utils import create_spotify_client, print_success, print_error, print_warning, print_info, print_header
from cache_utils import save_to_cache, load_from_cache
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

# Spotify API scopes needed for this script
SPOTIFY_SCOPES = [
    "playlist-read-private",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-library-read"
]

# Import cache from constants
from constants import DEFAULT_CACHE_EXPIRATION, STANDARD_CACHE_KEYS

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        sp = create_spotify_client(SPOTIFY_SCOPES, "playlist_manager")
        
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

def get_all_user_playlists(sp):
    """Get all playlists for the current user."""
    cache_key = STANDARD_CACHE_KEYS['user_playlists'] 
    cached_data = load_from_cache(cache_key, DEFAULT_CACHE_EXPIRATION)
    
    if cached_data:
        print_info("Using cached playlist data...")
        return cached_data
    
    print_info("Fetching all playlists...")
    playlists = []
    
    try:
        # Get current user ID
        user = sp.current_user()
        user_id = user['id']
        
        # Fetch all playlists
        results = sp.current_user_playlists(limit=50)
        
        while results:
            for playlist in results['items']:
                if playlist and playlist['owner']['id'] == user_id:
                    playlists.append({
                        'id': playlist['id'],
                        'name': playlist['name'],
                        'description': playlist.get('description', ''),
                        'public': playlist['public'],
                        'tracks_total': playlist['tracks']['total'],
                        'owner_id': playlist['owner']['id']
                    })
            
            if results['next']:
                results = sp.next(results)
            else:
                break
        
        # Cache the results
        save_to_cache(playlists, cache_key)
        print_success(f"Found {len(playlists)} playlists")
        
        return playlists
    
    except Exception as e:
        print_error(f"Error fetching playlists: {e}")
        return []

def get_playlist_tracks(sp, playlist_id):
    """Get all tracks from a playlist."""
    cache_key = f"playlist_tracks_{playlist_id}"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        return cached_data
    
    tracks = []
    try:
        results = sp.playlist_tracks(playlist_id, limit=100)
        
        while results:
            for item in results['items']:
                if item['track'] and item['track']['id']:
                    track = {
                        'id': item['track']['id'],
                        'name': item['track']['name'],
                        'artists': [artist['name'] for artist in item['track']['artists']],
                        'album': item['track']['album']['name'],
                        'duration_ms': item['track']['duration_ms'],
                        'popularity': item['track']['popularity'],
                        'uri': item['track']['uri']
                    }
                    tracks.append(track)
            
            if results['next']:
                results = sp.next(results)
            else:
                break
        
        # Cache the results
        save_to_cache(tracks, cache_key)
        
        return tracks
    
    except Exception as e:
        print_error(f"Error fetching tracks from playlist: {e}")
        return []

def find_duplicate_tracks_in_playlist(sp, playlist_id, playlist_name):
    """Find duplicate tracks within a single playlist."""
    print_info(f"Analyzing playlist: {playlist_name}")
    
    tracks = get_playlist_tracks(sp, playlist_id)
    if not tracks:
        print_warning("No tracks found in playlist")
        return []
    
    # Group tracks by ID (exact duplicates)
    track_counts = Counter(track['id'] for track in tracks)
    exact_duplicates = {track_id: count for track_id, count in track_counts.items() if count > 1}
    
    # Find similar tracks (fuzzy matching)
    similar_groups = []
    processed_tracks = set()
    
    for i, track1 in enumerate(tracks):
        if track1['id'] in processed_tracks:
            continue
        
        similar_tracks = [track1]
        track1_signature = f"{' '.join(track1['artists'])} - {track1['name']}".lower()
        
        for j, track2 in enumerate(tracks[i+1:], i+1):
            if track2['id'] in processed_tracks:
                continue
            
            track2_signature = f"{' '.join(track2['artists'])} - {track2['name']}".lower()
            
            # Calculate similarity
            similarity = difflib.SequenceMatcher(None, track1_signature, track2_signature).ratio()
            
            if similarity > 0.85:  # 85% similarity threshold
                similar_tracks.append(track2)
                processed_tracks.add(track2['id'])
        
        if len(similar_tracks) > 1:
            similar_groups.append(similar_tracks)
        
        processed_tracks.add(track1['id'])
    
    return {
        'exact_duplicates': exact_duplicates,
        'similar_groups': similar_groups,
        'total_tracks': len(tracks)
    }

def find_duplicates_across_playlists(sp, playlists):
    """Find duplicate tracks across multiple playlists."""
    print_info("Analyzing tracks across all playlists...")
    
    # Track to playlists mapping
    track_to_playlists = defaultdict(list)
    all_tracks = {}
    
    progress = create_progress_bar(len(playlists), "Analyzing playlists", "playlist")
    
    for i, playlist in enumerate(playlists):
        tracks = get_playlist_tracks(sp, playlist['id'])
        
        for track in tracks:
            track_id = track['id']
            track_to_playlists[track_id].append(playlist['name'])
            if track_id not in all_tracks:
                all_tracks[track_id] = track
        
        update_progress_bar(progress, i + 1)
    
    close_progress_bar(progress)
    
    # Find tracks that appear in multiple playlists
    cross_duplicates = {
        track_id: playlists_list 
        for track_id, playlists_list in track_to_playlists.items() 
        if len(playlists_list) > 1
    }
    
    return {
        'cross_duplicates': cross_duplicates,
        'all_tracks': all_tracks
    }

def display_duplicate_analysis(duplicates, playlist_name=None):
    """Display duplicate analysis results."""
    if playlist_name:
        print_header(f"Duplicate Analysis: {playlist_name}")
    else:
        print_header("Cross-Playlist Duplicate Analysis")
    
    if 'exact_duplicates' in duplicates:
        # Single playlist analysis
        exact_dupes = duplicates['exact_duplicates']
        similar_groups = duplicates['similar_groups']
        total_tracks = duplicates['total_tracks']
        
        print(f"Total tracks: {total_tracks}")
        print(f"Exact duplicates: {len(exact_dupes)} track types")
        print(f"Similar track groups: {len(similar_groups)}")
        
        if exact_dupes:
            print(f"\n{Fore.YELLOW}Exact Duplicates:")
            for track_id, count in exact_dupes.items():
                print(f"  - Track appears {count} times")
        
        if similar_groups:
            print(f"\n{Fore.YELLOW}Similar Track Groups:")
            for i, group in enumerate(similar_groups, 1):
                print(f"  Group {i}:")
                for track in group:
                    print(f"    - {' '.join(track['artists'])} - {track['name']}")
    
    else:
        # Cross-playlist analysis
        cross_dupes = duplicates['cross_duplicates']
        all_tracks = duplicates['all_tracks']
        
        print(f"Tracks appearing in multiple playlists: {len(cross_dupes)}")
        
        if cross_dupes:
            # Offer pagination for large lists
            total_dupes = len(cross_dupes)
            if total_dupes > 20:
                print(f"\n{Fore.CYAN}Options:")
                print(f"{Fore.WHITE}1. Show first 20 duplicates")
                print(f"{Fore.WHITE}2. Browse all {total_dupes} duplicates with pagination")
                print(f"{Fore.WHITE}3. Skip duplicate display")
                
                choice = input(f"\n{Fore.CYAN}Choose option (1-3): ").strip()
                
                if choice == "1":
                    print(f"\n{Fore.YELLOW}Cross-Playlist Duplicates (showing first 20 of {total_dupes}):")
                    for i, (track_id, playlists_list) in enumerate(list(cross_dupes.items())[:20], 1):
                        track = all_tracks[track_id]
                        print(f"{i:2d}. {' '.join(track['artists'])} - {track['name']}")
                        print(f"    Found in: {', '.join(playlists_list)}")
                elif choice == "2":
                    display_cross_duplicates_paginated(cross_dupes, all_tracks)
                # For choice == "3", skip display
            else:
                print(f"\n{Fore.YELLOW}Cross-Playlist Duplicates:")
                for i, (track_id, playlists_list) in enumerate(cross_dupes.items(), 1):
                    track = all_tracks[track_id]
                    print(f"{i:2d}. {' '.join(track['artists'])} - {track['name']}")
                    print(f"    Found in: {', '.join(playlists_list)}")

def display_cross_duplicates_paginated(cross_dupes, all_tracks):
    """Display cross-playlist duplicates with pagination."""
    if not cross_dupes:
        print_warning("No cross-playlist duplicates to display.")
        return
    
    page_size = 15
    items = list(cross_dupes.items())
    total_pages = (len(items) + page_size - 1) // page_size
    current_page = 1
    
    while True:
        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, len(items))
        page_items = items[start_idx:end_idx]
        
        print_header(f"Cross-Playlist Duplicates - Page {current_page}/{total_pages}")
        print(f"Showing {start_idx + 1}-{end_idx} of {len(items)} duplicate tracks")
        
        for i, (track_id, playlists_list) in enumerate(page_items, start_idx + 1):
            track = all_tracks[track_id]
            print(f"{i:3d}. {Fore.WHITE}{' '.join(track['artists'])} - {track['name']}")
            print(f"     {Fore.CYAN}Found in: {', '.join(playlists_list)}")
        
        print(f"\n{Fore.WHITE}Navigation:")
        nav_options = []
        if current_page > 1:
            nav_options.append("p: Previous page")
        if current_page < total_pages:
            nav_options.append("n: Next page")
        nav_options.append("q: Back to menu")
        
        print(" | ".join(nav_options))
        
        choice = input(f"\n{Fore.CYAN}Enter choice: ").strip().lower()
        
        if choice == 'n' and current_page < total_pages:
            current_page += 1
        elif choice == 'p' and current_page > 1:
            current_page -= 1
        elif choice == 'q':
            break
        else:
            print_warning("Invalid choice. Please try again.")

def remove_duplicates_from_playlist(sp, playlist_id, duplicates):
    """Remove duplicate tracks from a playlist."""
    if not duplicates['exact_duplicates'] and not duplicates['similar_groups']:
        print_info("No duplicates to remove.")
        return
    
    print_warning("Duplicate removal is not yet implemented.")
    print_info("This feature will be added in a future update.")

def manage_single_playlist_duplicates(sp):
    """Manage duplicates within a single playlist."""
    playlists = get_all_user_playlists(sp)
    
    if not playlists:
        print_warning("No playlists found.")
        return
    
    print_header("Single Playlist Duplicate Management")
    
    # Display playlists
    print("Your playlists:")
    for i, playlist in enumerate(playlists, 1):
        track_count = playlist['tracks_total']
        print(f"{i:2d}. {playlist['name']} ({track_count} tracks)")
    
    try:
        choice = int(input(f"\nSelect playlist (1-{len(playlists)}): ")) - 1
        
        if 0 <= choice < len(playlists):
            selected_playlist = playlists[choice]
            
            duplicates = find_duplicate_tracks_in_playlist(
                sp, 
                selected_playlist['id'], 
                selected_playlist['name']
            )
            
            display_duplicate_analysis(duplicates, selected_playlist['name'])
            
            # Ask if user wants to remove duplicates
            remove = input("\nRemove duplicates? (y/n): ").strip().lower()
            if remove == 'y':
                remove_duplicates_from_playlist(sp, selected_playlist['id'], duplicates)
        
        else:
            print_error("Invalid selection.")
    
    except ValueError:
        print_error("Invalid input. Please enter a number.")

def manage_cross_playlist_duplicates(sp):
    """Manage duplicates across multiple playlists."""
    playlists = get_all_user_playlists(sp)
    
    if not playlists:
        print_warning("No playlists found.")
        return
    
    duplicates = find_duplicates_across_playlists(sp, playlists)
    display_duplicate_analysis(duplicates)

def main():
    """Main function to run the playlist manager."""
    print_header("Spotify Playlist Manager")
    
    # Set up Spotify client
    sp = setup_spotify_client()
    if not sp:
        return
    
    while True:
        print_header("Playlist Management Options")
        print(f"{Fore.WHITE}1. Find duplicates in a specific playlist")
        print(f"{Fore.WHITE}2. Find duplicates across all playlists")
        print(f"{Fore.WHITE}3. Back to main menu")
        
        choice = input(f"\n{Fore.CYAN}Enter your choice (1-3): ")
        
        if choice == "1":
            manage_single_playlist_duplicates(sp)
        elif choice == "2":
            manage_cross_playlist_duplicates(sp)
        elif choice == "3":
            break
        else:
            print_error("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()