#!/usr/bin/env python3
"""
Spotify Playlist Size Manager

This script allows users to find and manage playlists based on their track count.
Features include:
- Search for playlists with X or fewer tracks
- Display playlists with pagination
- Delete selected playlists with confirmation

Author: Matt Y
License: MIT
"""

import os
import sys
import time
from typing import List, Dict, Optional, Tuple
import math

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from spotify_utils import (
    create_spotify_client, 
    fetch_user_playlists,
    print_header, 
    print_success, 
    print_error, 
    print_warning, 
    print_info
)
from cache_utils import save_to_cache, load_from_cache
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Constants
PAGE_SIZE = 10  # Number of playlists to show per page
CACHE_KEY_PREFIX = "playlist_size_search"
CACHE_EXPIRATION = 3600  # 1 hour

class PlaylistSizeManager:
    """Manages finding and deleting playlists based on track count."""
    
    def __init__(self):
        """Initialize the playlist size manager."""
        self.sp = None
        self.user_id = None
        
    def setup(self):
        """Set up Spotify client and get user information."""
        print_info("Setting up Spotify client...")
        # Scopes needed for playlist management
        scopes = [
            "playlist-read-private",
            "playlist-modify-private",
            "playlist-modify-public"
        ]
        self.sp = create_spotify_client(scopes)
        
        # Get current user info
        try:
            user_info = self.sp.current_user()
            self.user_id = user_info['id']
            print_success(f"Logged in as: {user_info['display_name']} ({self.user_id})")
            return True
        except Exception as e:
            print_error(f"Failed to get user information: {e}")
            return False
    
    def get_playlists_by_size(self, max_tracks: int, use_cache: bool = True) -> List[Dict]:
        """
        Get all user's playlists with track count <= max_tracks.
        
        Args:
            max_tracks: Maximum number of tracks
            use_cache: Whether to use cached results
            
        Returns:
            List of playlist dictionaries with track counts
        """
        cache_key = f"{CACHE_KEY_PREFIX}_{self.user_id}_{max_tracks}"
        
        # Try to load from cache
        if use_cache:
            cached_data = load_from_cache(cache_key, expiration=CACHE_EXPIRATION)
            if cached_data:
                print_info("Using cached playlist data...")
                return cached_data
        
        print_info("Fetching your playlists...")
        all_playlists = fetch_user_playlists(self.sp, self.user_id)
        
        # Filter to only user-created playlists
        user_playlists = [p for p in all_playlists if p['owner']['id'] == self.user_id]
        
        print_info(f"Analyzing {len(user_playlists)} playlists...")
        
        matching_playlists = []
        
        for playlist in user_playlists:
            # Get track count
            track_count = playlist['tracks']['total']
            
            if track_count <= max_tracks:
                playlist_info = {
                    'id': playlist['id'],
                    'name': playlist['name'],
                    'track_count': track_count,
                    'public': playlist['public'],
                    'collaborative': playlist['collaborative'],
                    'description': playlist.get('description', ''),
                    'url': playlist['external_urls']['spotify']
                }
                matching_playlists.append(playlist_info)
        
        # Sort by track count (ascending) then by name
        matching_playlists.sort(key=lambda x: (x['track_count'], x['name'].lower()))
        
        # Save to cache
        if use_cache:
            save_to_cache(matching_playlists, cache_key)
        
        return matching_playlists
    
    def display_playlists_paginated(self, playlists: List[Dict]) -> Optional[List[Dict]]:
        """
        Display playlists with pagination.
        
        Args:
            playlists: List of playlist dictionaries
            
        Returns:
            List of selected playlists for deletion, or None if cancelled
        """
        if not playlists:
            print_warning("No playlists found matching your criteria.")
            return None
        
        total_pages = math.ceil(len(playlists) / PAGE_SIZE)
        current_page = 1
        selected_playlists = []
        
        while True:
            # Clear screen
            os.system('clear' if os.name != 'nt' else 'cls')
            
            print_header(f"Playlists with {playlists[0]['track_count']} to {playlists[-1]['track_count']} tracks")
            print(f"\nTotal playlists found: {len(playlists)}")
            print(f"Page {current_page} of {total_pages}")
            print("=" * 80)
            
            # Calculate page boundaries
            start_idx = (current_page - 1) * PAGE_SIZE
            end_idx = min(start_idx + PAGE_SIZE, len(playlists))
            
            # Display playlists for current page
            for i in range(start_idx, end_idx):
                playlist = playlists[i]
                selected_marker = "[X]" if playlist in selected_playlists else "[ ]"
                
                print(f"\n{selected_marker} {i + 1}. {Fore.CYAN}{playlist['name']}{Style.RESET_ALL}")
                print(f"    Tracks: {playlist['track_count']}")
                print(f"    Type: {'Public' if playlist['public'] else 'Private'}"
                      f"{', Collaborative' if playlist['collaborative'] else ''}")
                if playlist['description']:
                    print(f"    Description: {playlist['description'][:50]}{'...' if len(playlist['description']) > 50 else ''}")
            
            print("\n" + "=" * 80)
            print(f"Selected for deletion: {len(selected_playlists)} playlists")
            print("\nOptions:")
            print("  [n] Next page")
            print("  [p] Previous page")
            print("  [#] Toggle selection (enter playlist number)")
            print("  [a] Toggle all on current page")
            print("  [d] Delete selected playlists")
            print("  [q] Quit without deleting")
            
            choice = input("\nEnter your choice: ").strip().lower()
            
            if choice == 'q':
                return None
            elif choice == 'n' and current_page < total_pages:
                current_page += 1
            elif choice == 'p' and current_page > 1:
                current_page -= 1
            elif choice == 'a':
                # Toggle all on current page
                for i in range(start_idx, end_idx):
                    if playlists[i] in selected_playlists:
                        selected_playlists.remove(playlists[i])
                    else:
                        selected_playlists.append(playlists[i])
            elif choice == 'd':
                if selected_playlists:
                    return selected_playlists
                else:
                    print_warning("No playlists selected for deletion.")
                    input("Press Enter to continue...")
            elif choice.isdigit():
                # Toggle specific playlist
                playlist_num = int(choice) - 1
                if 0 <= playlist_num < len(playlists):
                    playlist = playlists[playlist_num]
                    if playlist in selected_playlists:
                        selected_playlists.remove(playlist)
                    else:
                        selected_playlists.append(playlist)
                else:
                    print_error("Invalid playlist number.")
                    input("Press Enter to continue...")
    
    def delete_playlists(self, playlists: List[Dict]):
        """
        Delete the selected playlists with confirmation.
        
        Args:
            playlists: List of playlist dictionaries to delete
        """
        print_header("Playlist Deletion Confirmation")
        print(f"\nYou are about to delete {len(playlists)} playlist(s):")
        
        total_tracks = 0
        for playlist in playlists:
            print(f"  - {playlist['name']} ({playlist['track_count']} tracks)")
            total_tracks += playlist['track_count']
        
        print(f"\nTotal tracks to be removed: {total_tracks}")
        print(f"{Fore.RED}{Style.BRIGHT}WARNING: This action cannot be undone!{Style.RESET_ALL}")
        
        confirmation = input("\nType 'DELETE' to confirm deletion: ").strip()
        
        if confirmation == 'DELETE':
            print_info("Deleting playlists...")
            
            deleted_count = 0
            failed_count = 0
            
            for playlist in playlists:
                try:
                    self.sp.current_user_unfollow_playlist(playlist['id'])
                    print_success(f"Deleted: {playlist['name']}")
                    deleted_count += 1
                    time.sleep(0.5)  # Rate limiting
                except Exception as e:
                    print_error(f"Failed to delete '{playlist['name']}': {e}")
                    failed_count += 1
            
            print(f"\n{Fore.GREEN}Successfully deleted: {deleted_count} playlists{Style.RESET_ALL}")
            if failed_count > 0:
                print(f"{Fore.RED}Failed to delete: {failed_count} playlists{Style.RESET_ALL}")
            
            # Clear cache after deletion
            cache_key_pattern = f"{CACHE_KEY_PREFIX}_{self.user_id}_"
            from cache_utils import list_caches, clear_cache
            
            # Find and clear all matching caches
            caches = list_caches()
            cleared_count = 0
            for cache in caches:
                if cache['name'].startswith(cache_key_pattern):
                    clear_cache(cache['name'])
                    cleared_count += 1
            
            if cleared_count > 0:
                print(f"Cleared {cleared_count} playlist search cache(s)")
            # If no caches found, don't show any message (this is normal)
            
        else:
            print_warning("Deletion cancelled.")
    
    def run(self):
        """Main execution flow."""
        if not self.setup():
            return
        
        while True:
            print_header("Playlist Size Manager")
            
            # Get threshold from user
            while True:
                try:
                    max_tracks = input("\nEnter maximum number of tracks (or 'q' to quit): ").strip()
                    
                    if max_tracks.lower() == 'q':
                        print_info("Exiting...")
                        return
                    
                    max_tracks = int(max_tracks)
                    if max_tracks < 0:
                        print_error("Please enter a non-negative number.")
                        continue
                    break
                except ValueError:
                    print_error("Please enter a valid number.")
            
            # Search for playlists
            matching_playlists = self.get_playlists_by_size(max_tracks)
            
            if not matching_playlists:
                print_warning(f"No playlists found with {max_tracks} or fewer tracks.")
                retry = input("\nSearch again? (y/n): ").strip().lower()
                if retry != 'y':
                    break
                continue
            
            print_success(f"Found {len(matching_playlists)} playlist(s) with {max_tracks} or fewer tracks.")
            
            # Display and potentially delete playlists
            selected_playlists = self.display_playlists_paginated(matching_playlists)
            
            if selected_playlists:
                self.delete_playlists(selected_playlists)
            
            # Ask if user wants to search again
            again = input("\nSearch for more playlists? (y/n): ").strip().lower()
            if again != 'y':
                break
        
        print_success("Done!")


def main():
    """Main entry point."""
    manager = PlaylistSizeManager()
    
    try:
        manager.run()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
    except Exception as e:
        print_error(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()