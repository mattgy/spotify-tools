#!/usr/bin/env python3
"""
Spotify Duplicate Song Remover

This script identifies and removes duplicate songs from your Liked Songs library.
Duplicates are identified by track ID, name similarity, or artist-title matching.

Features:
- Find exact duplicates (same track ID)
- Find similar tracks (fuzzy matching)
- Preview duplicates before removal
- Backup functionality before making changes
- Safe removal with user confirmation

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import time
import json
from collections import defaultdict, Counter
from difflib import SequenceMatcher
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
from constants import CACHE_EXPIRATION, CONFIDENCE_THRESHOLDS, BATCH_SIZES, SPOTIFY_SCOPES

# Spotify API scopes needed for this script
SCOPES = SPOTIFY_SCOPES['modify']

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        sp = create_spotify_client(SCOPES, "remove_duplicates")
        
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

def get_liked_songs(sp):
    """Get all liked songs from the user's library."""
    from spotify_utils import fetch_user_saved_tracks
    
    # Fetch saved tracks using the reusable function with progress bar
    saved_tracks_data = fetch_user_saved_tracks(sp, show_progress=True, cache_key="all_liked_songs", cache_expiration=CACHE_EXPIRATION['personal'])
    
    # Convert to our expected format
    liked_songs = []
    for item in saved_tracks_data:
        if item['track'] and item['track']['id']:
            track = {
                'id': item['track']['id'],
                'name': item['track']['name'],
                'artists': [artist['name'] for artist in item['track']['artists']],
                'album': item['track']['album']['name'],
                'duration_ms': item['track']['duration_ms'],
                'popularity': item['track']['popularity'],
                'uri': item['track']['uri'],
                'added_at': item['added_at']
            }
            liked_songs.append(track)
    
    print_success(f"Found {len(liked_songs)} liked songs")
    return liked_songs

def find_exact_duplicates(tracks):
    """Find tracks with exactly the same ID."""
    track_counts = Counter(track['id'] for track in tracks)
    exact_duplicates = {}
    
    for track_id, count in track_counts.items():
        if count > 1:
            # Find all instances of this track
            duplicate_tracks = [track for track in tracks if track['id'] == track_id]
            exact_duplicates[track_id] = duplicate_tracks
    
    return exact_duplicates

def normalize_string(s):
    """Normalize string for better duplicate detection."""
    if not s:
        return ""
    import re
    # Remove special characters, convert to lowercase, remove extra spaces
    s = re.sub(r'[^\w\s]', '', s.lower())
    s = re.sub(r'\s+', ' ', s).strip()
    # Remove common words that might interfere
    common_words = ['the', 'a', 'an', 'and', 'or', 'feat', 'featuring', 'ft', 'remix', 'remaster']
    words = [w for w in s.split() if w not in common_words]
    return ' '.join(words)

def calculate_similarity(track1, track2):
    """Calculate similarity score between two tracks."""
    # Create signatures for comparison
    signature1 = f"{' '.join(track1['artists'])} {track1['name']}".lower()
    signature2 = f"{' '.join(track2['artists'])} {track2['name']}".lower()
    
    # Calculate similarity ratio
    similarity = SequenceMatcher(None, signature1, signature2).ratio()
    
    # Bonus points for same artist
    if any(artist.lower() in [a.lower() for a in track2['artists']] for artist in track1['artists']):
        similarity += 0.1
    
    # Penalty for very different durations
    duration_diff = abs(track1['duration_ms'] - track2['duration_ms'])
    if duration_diff > 30000:  # More than 30 seconds difference
        similarity -= 0.2
    
    return min(1.0, max(0.0, similarity))

def find_similar_duplicates(tracks, similarity_threshold=None):
    """Find tracks that are very similar but not exact duplicates using efficient grouping."""
    if similarity_threshold is None:
        similarity_threshold = CONFIDENCE_THRESHOLDS['fuzzy_matching']
    
    print_info(f"Finding similar tracks with {similarity_threshold*100:.0f}% similarity threshold...")
    print_info("Using efficient duplicate detection algorithm...")
    
    # Group tracks by normalized artist-title combinations for efficient comparison
    normalized_groups = defaultdict(list)
    
    progress = create_progress_bar(len(tracks), "Grouping tracks", "track")
    
    for track in tracks:
        # Create normalized key for efficient grouping
        title = normalize_string(track['name'])
        artists = normalize_string(' '.join([artist['name'] for artist in track['artists']]))
        
        # Create multiple keys to catch variations
        key1 = f"{artists}_{title}"
        key2 = f"{title}_{artists}"
        key3 = title  # For title-only matching
        
        normalized_groups[key1].append(track)
        if key2 != key1:
            normalized_groups[key2].append(track)
        if len(title) > 3:  # Avoid very short titles
            normalized_groups[key3].append(track)
        
        update_progress_bar(progress, 1)
    
    close_progress_bar(progress)
    
    # Find groups with multiple tracks and verify similarity
    similar_groups = []
    processed_tracks = set()
    
    print_info(f"Analyzing {len(normalized_groups)} grouped combinations...")
    
    for key, group_tracks in normalized_groups.items():
        if len(group_tracks) > 1:
            # Remove already processed tracks
            group_tracks = [t for t in group_tracks if t['id'] not in processed_tracks]
            
            if len(group_tracks) > 1:
                # Verify similarity within the group
                verified_group = []
                for track in group_tracks:
                    if not verified_group:
                        verified_group.append(track)
                        continue
                    
                    # Check if this track is similar to any in the verified group
                    for verified_track in verified_group:
                        similarity = calculate_similarity(track, verified_track)
                        if similarity >= similarity_threshold:
                            verified_group.append(track)
                            break
                
                if len(verified_group) > 1:
                    similar_groups.append(verified_group)
                    for track in verified_group:
                        processed_tracks.add(track['id'])
    
    return similar_groups

def display_duplicates(exact_duplicates, similar_groups):
    """Display found duplicates to the user."""
    print_header("Duplicate Analysis Results")
    
    total_exact = sum(len(tracks) - 1 for tracks in exact_duplicates.values())
    total_similar = sum(len(group) - 1 for group in similar_groups)
    
    print(f"Exact duplicates found: {len(exact_duplicates)} groups ({total_exact} duplicate tracks)")
    print(f"Similar duplicates found: {len(similar_groups)} groups ({total_similar} similar tracks)")
    
    if exact_duplicates:
        print(f"\n{Fore.YELLOW}Exact Duplicates:")
        for i, (track_id, tracks) in enumerate(exact_duplicates.items(), 1):
            track = tracks[0]  # All tracks in this group are identical
            print(f"{i:2d}. {' '.join(track['artists'])} - {track['name']}")
            print(f"    Album: {track['album']}")
            print(f"    Found {len(tracks)} times")
            print(f"    Added dates: {', '.join(track['added_at'][:10] for track in tracks)}")
    
    if similar_groups:
        print(f"\n{Fore.YELLOW}Similar Duplicates:")
        for i, group in enumerate(similar_groups, 1):
            print(f"Group {i}:")
            for j, track in enumerate(group):
                print(f"  {j+1}. {' '.join(track['artists'])} - {track['name']}")
                print(f"     Album: {track['album']} | Duration: {track['duration_ms']//1000}s | Added: {track['added_at'][:10]}")

def select_tracks_to_remove(exact_duplicates, similar_groups):
    """Let user select which tracks to remove."""
    tracks_to_remove = []
    
    # Handle exact duplicates
    if exact_duplicates:
        print_header("Exact Duplicate Removal")
        print("For exact duplicates, we'll keep the first added and remove the rest.")
        
        for track_id, tracks in exact_duplicates.items():
            # Sort by added date, keep the earliest
            tracks_sorted = sorted(tracks, key=lambda x: x['added_at'])
            tracks_to_remove.extend(tracks_sorted[1:])  # Remove all but the first
            
            print(f"Keeping: {' '.join(tracks_sorted[0]['artists'])} - {tracks_sorted[0]['name']} (added {tracks_sorted[0]['added_at'][:10]})")
            print(f"Removing: {len(tracks_sorted[1:])} duplicate(s)")
    
    # Handle similar duplicates
    if similar_groups:
        print_header("Similar Duplicate Removal")
        print("For similar tracks, please choose which ones to keep:")
        
        for i, group in enumerate(similar_groups, 1):
            print(f"\nGroup {i} - Choose tracks to KEEP (others will be removed):")
            
            for j, track in enumerate(group):
                print(f"  {j+1}. {' '.join(track['artists'])} - {track['name']}")
                print(f"     Album: {track['album']} | Popularity: {track['popularity']} | Added: {track['added_at'][:10]}")
            
            while True:
                choice = input(f"\nEnter numbers to keep (e.g., '1,3' or 'all' or 'skip'): ").strip().lower()
                
                if choice == 'skip':
                    print_info("Skipping this group.")
                    break
                elif choice == 'all':
                    print_info("Keeping all tracks in this group.")
                    break
                else:
                    try:
                        keep_indices = [int(x.strip()) - 1 for x in choice.split(',')]
                        
                        # Validate indices
                        if all(0 <= idx < len(group) for idx in keep_indices):
                            # Add tracks not in keep_indices to removal list
                            for j, track in enumerate(group):
                                if j not in keep_indices:
                                    tracks_to_remove.append(track)
                            
                            kept_tracks = [group[idx] for idx in keep_indices]
                            print_success(f"Will keep {len(kept_tracks)} track(s), remove {len(group) - len(kept_tracks)} track(s)")
                            break
                        else:
                            print_error("Invalid indices. Please try again.")
                    except ValueError:
                        print_error("Invalid input. Please enter numbers separated by commas.")
    
    return tracks_to_remove

def create_backup(sp, tracks_to_remove):
    """Create a backup playlist with tracks that will be removed."""
    if not tracks_to_remove:
        return None
    
    try:
        user = sp.current_user()
        user_id = user['id']
        
        # Create backup playlist
        backup_name = f"Removed Duplicates Backup - {time.strftime('%Y-%m-%d %H:%M')}"
        backup_playlist = sp.user_playlist_create(
            user=user_id,
            name=backup_name,
            public=False,
            description="Backup of duplicate tracks removed from Liked Songs"
        )
        
        # Add tracks to backup playlist in batches
        track_uris = [track['uri'] for track in tracks_to_remove]
        batch_size = BATCH_SIZES['spotify_tracks']
        
        for i in range(0, len(track_uris), batch_size):
            batch = track_uris[i:i + batch_size]
            sp.playlist_add_items(backup_playlist['id'], batch)
            time.sleep(0.1)  # Rate limiting
        
        print_success(f"Created backup playlist: {backup_name}")
        return backup_playlist['id']
    
    except Exception as e:
        print_error(f"Error creating backup: {e}")
        return None

def remove_tracks_from_library(sp, tracks_to_remove):
    """Remove selected tracks from the user's Liked Songs."""
    if not tracks_to_remove:
        print_info("No tracks to remove.")
        return
    
    print_info(f"Removing {len(tracks_to_remove)} tracks from Liked Songs...")
    
    try:
        # Remove tracks in batches
        track_ids = [track['id'] for track in tracks_to_remove]
        batch_size = BATCH_SIZES['spotify_tracks']
        
        progress = create_progress_bar(len(track_ids), "Removing tracks", "track")
        
        for i in range(0, len(track_ids), batch_size):
            batch = track_ids[i:i + batch_size]
            sp.current_user_saved_tracks_delete(batch)
            
            update_progress_bar(progress, min(i + batch_size, len(track_ids)))
            time.sleep(0.2)  # Rate limiting
        
        close_progress_bar(progress)
        print_success(f"Successfully removed {len(tracks_to_remove)} duplicate tracks!")
        
        # Clear cache so next run gets fresh data
        cache_key = "all_liked_songs"
        save_to_cache(None, cache_key, force_expire=True)
        
    except Exception as e:
        print_error(f"Error removing tracks: {e}")

def main():
    """Main function to run the duplicate remover."""
    print_header("Spotify Duplicate Song Remover")
    
    # Set up Spotify client
    sp = setup_spotify_client()
    if not sp:
        return
    
    # Get liked songs
    liked_songs = get_liked_songs(sp)
    if not liked_songs:
        print_warning("No liked songs found.")
        return
    
    # Find duplicates
    print_info("Analyzing tracks for duplicates...")
    exact_duplicates = find_exact_duplicates(liked_songs)
    similar_groups = find_similar_duplicates(liked_songs)
    
    # Display results
    display_duplicates(exact_duplicates, similar_groups)
    
    if not exact_duplicates and not similar_groups:
        print_success("No duplicates found! Your library is clean.")
        return
    
    # Ask user if they want to proceed
    print_warning(f"\nThis will modify your Liked Songs library.")
    proceed = input("Do you want to proceed with duplicate removal? (y/n): ").strip().lower()
    
    if proceed != 'y':
        print_info("Operation cancelled.")
        return
    
    # Select tracks to remove
    tracks_to_remove = select_tracks_to_remove(exact_duplicates, similar_groups)
    
    if not tracks_to_remove:
        print_info("No tracks selected for removal.")
        return
    
    # Create backup
    print_info("Creating backup playlist...")
    backup_playlist_id = create_backup(sp, tracks_to_remove)
    
    # Final confirmation
    print_warning(f"\nReady to remove {len(tracks_to_remove)} duplicate tracks from Liked Songs.")
    if backup_playlist_id:
        print_info("Backup playlist created successfully.")
    
    final_confirm = input("Are you sure? This action cannot be undone (y/n): ").strip().lower()
    
    if final_confirm == 'y':
        remove_tracks_from_library(sp, tracks_to_remove)
    else:
        print_info("Operation cancelled.")

if __name__ == "__main__":
    main()