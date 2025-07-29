#!/usr/bin/env python3
"""
Spotify Playlist Reconciliation Tool

This script helps reconcile Spotify playlists with local playlist files by:
1. Finding extra tracks in Spotify playlists that aren't in the local versions
2. Detecting and handling duplicate Spotify playlists with the same name as local ones
3. Improved playlist matching logic to avoid false positives

Features:
- Cache system for processed playlists and user decisions (1 month expiration)
- Option to clear processed playlist cache
- Enhanced playlist name matching
- Batch processing with user confirmation
"""

import os
import sys
import re
import glob
import argparse
from pathlib import Path
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from thefuzz import fuzz
import time
import logging
import json
from tqdm import tqdm
import traceback
from datetime import datetime, timedelta
import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform color support
colorama.init(autoreset=True)

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from credentials_manager import get_spotify_credentials
from cache_utils import save_to_cache, load_from_cache
from spotify_playlist_converter import (
    parse_playlist_file as original_parse_playlist_file, authenticate_spotify, get_user_playlists, 
    get_playlist_tracks, normalize_string, SUPPORTED_EXTENSIONS,
    find_playlist_files as converter_find_playlist_files, 
    is_text_playlist_file as converter_is_text_playlist_file
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Constants
SCOPE = "playlist-read-private playlist-modify-private playlist-modify-public"
CACHE_EXPIRATION_LONG = 30 * 24 * 60 * 60  # 30 days for user decisions and processed playlists
SIMILARITY_THRESHOLD = 80  # Minimum similarity for considering playlists as potential duplicates

def create_processed_playlist_cache_key(local_path, spotify_playlist_id):
    """Create a cache key for tracking processed playlist pairs."""
    return f"processed_playlist_{hash(local_path + spotify_playlist_id) % 1000000}"

def mark_playlist_processed(local_path, spotify_playlist_id):
    """Mark a playlist pair as processed."""
    cache_key = create_processed_playlist_cache_key(local_path, spotify_playlist_id)
    processed_data = {
        'local_path': local_path,
        'spotify_playlist_id': spotify_playlist_id,
        'processed_at': time.time()
    }
    save_to_cache(processed_data, cache_key, force_expire=False)

def is_playlist_processed(local_path, spotify_playlist_id):
    """Check if a playlist pair has been processed."""
    cache_key = create_processed_playlist_cache_key(local_path, spotify_playlist_id)
    processed_data = load_from_cache(cache_key, CACHE_EXPIRATION_LONG)
    return processed_data is not None

def clear_processed_playlist_cache():
    """Clear all processed playlist cache entries."""
    from cache_utils import list_caches, clear_cache
    
    caches = list_caches()
    processed_caches = [c for c in caches if c['name'].startswith('processed_playlist_')]
    
    if not processed_caches:
        print(f"{Fore.YELLOW}No processed playlist cache entries found.")
        return
    
    print(f"{Fore.CYAN}Found {len(processed_caches)} processed playlist cache entries.")
    confirm = input(f"{Fore.CYAN}Clear all processed playlist cache? (y/n): ").lower().strip()
    
    if confirm == 'y':
        for cache in processed_caches:
            clear_cache(cache['name'])
        print(f"{Fore.GREEN}✅ Cleared {len(processed_caches)} processed playlist cache entries.")
    else:
        print(f"{Fore.YELLOW}Cache clearing cancelled.")

def create_reconcile_decision_cache_key(local_path, spotify_playlist_id, action_type):
    """Create a cache key for reconciliation decisions."""
    return f"reconcile_decision_{action_type}_{hash(local_path + spotify_playlist_id) % 1000000}"

def save_reconcile_decision(local_path, spotify_playlist_id, action_type, decision):
    """Save a reconciliation decision to cache."""
    cache_key = create_reconcile_decision_cache_key(local_path, spotify_playlist_id, action_type)
    decision_data = {
        'local_path': local_path,
        'spotify_playlist_id': spotify_playlist_id,
        'action_type': action_type,
        'decision': decision,
        'timestamp': time.time()
    }
    save_to_cache(decision_data, cache_key, force_expire=False)

def get_cached_reconcile_decision(local_path, spotify_playlist_id, action_type):
    """Get a previously cached reconciliation decision."""
    cache_key = create_reconcile_decision_cache_key(local_path, spotify_playlist_id, action_type)
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION_LONG)
    return cached_data.get('decision') if cached_data else None

def improved_playlist_name_matching(local_name, spotify_names):
    """
    Improved playlist matching logic that handles common variations.
    Returns exact matches and similar matches separately.
    """
    # Normalize the local name
    norm_local = normalize_string(local_name).lower()
    
    exact_matches = []
    similar_matches = []
    
    for spotify_name in spotify_names:
        norm_spotify = normalize_string(spotify_name).lower()
        
        # Check for exact match first
        if norm_local == norm_spotify:
            exact_matches.append(spotify_name)
            continue
        
        # Calculate similarity
        similarity = fuzz.ratio(norm_local, norm_spotify)
        
        # Special case for numbered variations (marco2 vs marco1, marco4)
        # If they're both short names with numbers, be more strict
        local_base = re.sub(r'\d+$', '', norm_local)
        spotify_base = re.sub(r'\d+$', '', norm_spotify)
        
        if (len(local_base) <= 6 and len(spotify_base) <= 6 and 
            local_base == spotify_base and local_base != norm_local and spotify_base != norm_spotify):
            # This is a numbered variation - only consider it similar if very high confidence
            if similarity >= 95:
                similar_matches.append((spotify_name, similarity))
        elif similarity >= SIMILARITY_THRESHOLD:
            similar_matches.append((spotify_name, similarity))
    
    # Sort similar matches by similarity
    similar_matches.sort(key=lambda x: x[1], reverse=True)
    
    return exact_matches, similar_matches

def get_local_playlist_track_ids(local_tracks, sp):
    """
    Convert local playlist tracks to Spotify track IDs using the existing search logic.
    Returns a set of track IDs that were successfully matched.
    """
    from spotify_playlist_converter import search_track_on_spotify
    
    track_ids = set()
    
    for track in local_tracks:
        match = search_track_on_spotify(sp, track['artist'], track['title'], track.get('album'))
        if match and match.get('id'):
            track_ids.add(match['id'])
    
    return track_ids

def get_local_playlist_track_ids_with_threshold(local_tracks, sp, similarity_threshold=85):
    """
    Convert local playlist tracks to Spotify track IDs using similarity matching.
    Returns a set of track IDs that were successfully matched above the threshold.
    """
    from spotify_playlist_converter import search_track_on_spotify
    
    track_ids = set()
    
    for track in local_tracks:
        # First try exact search
        match = search_track_on_spotify(sp, track['artist'], track['title'], track.get('album'))
        if match and match.get('id'):
            track_ids.add(match['id'])
        else:
            # If no exact match, try fuzzy matching with threshold
            search_query = f"{track['artist']} {track['title']}"
            try:
                results = sp.search(q=search_query, type='track', limit=10)
                
                if results['tracks']['items']:
                    for item in results['tracks']['items']:
                        # Calculate similarity for artist and title
                        artist_names = [a['name'] for a in item['artists']]
                        artist_match = max([fuzz.ratio(track['artist'].lower(), a.lower()) for a in artist_names])
                        title_match = fuzz.ratio(track['title'].lower(), item['name'].lower())
                        
                        # Average similarity
                        avg_similarity = (artist_match + title_match) / 2
                        
                        if avg_similarity >= similarity_threshold:
                            track_ids.add(item['id'])
                            break
            except Exception as e:
                logger.debug(f"Error in fuzzy search for {track['artist']} - {track['title']}: {e}")
    
    return track_ids

def find_extra_tracks_in_spotify_playlist(sp, spotify_playlist_id, local_tracks):
    """
    Find tracks in the Spotify playlist that don't exist in the local playlist.
    Returns a list of extra tracks with their details.
    """
    # Get Spotify playlist tracks
    spotify_track_uris = get_playlist_tracks(sp, spotify_playlist_id)
    spotify_track_ids = set()
    
    # Get detailed track info for Spotify tracks
    spotify_tracks_info = []
    batch_size = 50
    
    for i in range(0, len(spotify_track_uris), batch_size):
        batch_uris = spotify_track_uris[i:i + batch_size]
        track_ids = [uri.split(':')[-1] for uri in batch_uris]
        
        try:
            tracks_info = sp.tracks(track_ids)
            for track in tracks_info['tracks']:
                if track:
                    spotify_track_ids.add(track['id'])
                    spotify_tracks_info.append({
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [a['name'] for a in track['artists']],
                        'album': track['album']['name'],
                        'uri': track['uri']
                    })
        except Exception as e:
            logger.error(f"Error getting track details: {e}")
    
    # Get local playlist track IDs
    local_track_ids = get_local_playlist_track_ids(local_tracks, sp)
    
    # Find extra tracks
    extra_track_ids = spotify_track_ids - local_track_ids
    extra_tracks = [track for track in spotify_tracks_info if track['id'] in extra_track_ids]
    
    return extra_tracks

def find_extra_tracks_in_spotify_playlist_with_threshold(sp, spotify_playlist_id, local_tracks, similarity_threshold=85):
    """
    Find tracks in the Spotify playlist that don't exist in the local playlist,
    using similarity threshold for matching.
    Returns a list of extra tracks with their details.
    """
    # Get Spotify playlist tracks
    spotify_track_uris = get_playlist_tracks(sp, spotify_playlist_id)
    spotify_track_ids = set()
    
    # Get detailed track info for Spotify tracks
    spotify_tracks_info = []
    batch_size = 50
    
    for i in range(0, len(spotify_track_uris), batch_size):
        batch_uris = spotify_track_uris[i:i + batch_size]
        track_ids = [uri.split(':')[-1] for uri in batch_uris]
        
        try:
            tracks_info = sp.tracks(track_ids)
            for track in tracks_info['tracks']:
                if track:
                    spotify_track_ids.add(track['id'])
                    spotify_tracks_info.append({
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [a['name'] for a in track['artists']],
                        'album': track['album']['name'],
                        'uri': track['uri']
                    })
        except Exception as e:
            logger.error(f"Error getting track details: {e}")
    
    # Get local playlist track IDs with threshold
    local_track_ids = get_local_playlist_track_ids_with_threshold(local_tracks, sp, similarity_threshold)
    
    # Find extra tracks
    extra_track_ids = spotify_track_ids - local_track_ids
    extra_tracks = [track for track in spotify_tracks_info if track['id'] in extra_track_ids]
    
    return extra_tracks

def find_duplicate_spotify_playlists(user_playlists, local_playlist_name):
    """
    Find Spotify playlists that have the same name as the local playlist.
    Returns exact matches and groups of similar matches.
    """
    exact_matches = []
    similar_groups = {}
    
    for playlist in user_playlists:
        if playlist['name'] == local_playlist_name:
            exact_matches.append(playlist)
    
    # If we have multiple exact matches, group them
    if len(exact_matches) > 1:
        similar_groups[local_playlist_name] = exact_matches
    
    return exact_matches, similar_groups

def remove_tracks_from_playlist(sp, playlist_id, track_uris):
    """Remove specified tracks from a Spotify playlist."""
    if not track_uris:
        return 0
    
    removed_count = 0
    batch_size = 100
    
    for i in range(0, len(track_uris), batch_size):
        batch = track_uris[i:i + batch_size]
        try:
            sp.playlist_remove_all_occurrences_of_items(playlist_id, batch)
            removed_count += len(batch)
        except Exception as e:
            logger.error(f"Error removing tracks from playlist: {e}")
    
    return removed_count

def delete_spotify_playlist(sp, playlist_id):
    """Delete a Spotify playlist."""
    try:
        sp.user_playlist_unfollow(sp.current_user()['id'], playlist_id)
        return True
    except Exception as e:
        logger.error(f"Error deleting playlist: {e}")
        return False

def reconcile_playlist_pair(sp, local_path, spotify_playlists, user_id):
    """
    Reconcile a local playlist with its Spotify counterparts.
    Handles both extra tracks and duplicate playlists.
    """
    local_name = os.path.splitext(os.path.basename(local_path))[0]
    
    # Parse local playlist
    try:
        local_tracks = parse_playlist_file(local_path)
        if not local_tracks:
            logger.warning(f"No tracks found in local playlist: {local_path}")
            return
    except Exception as e:
        logger.error(f"Error parsing local playlist {local_path}: {e}")
        return
    
    # Find matching Spotify playlists
    spotify_names = [p['name'] for p in spotify_playlists]
    exact_matches, similar_matches = improved_playlist_name_matching(local_name, spotify_names)
    
    # Get the actual playlist objects
    exact_playlists = [p for p in spotify_playlists if p['name'] in exact_matches]
    similar_playlists = [(p, sim) for p in spotify_playlists for name, sim in similar_matches if p['name'] == name]
    
    if not exact_playlists and not similar_playlists:
        logger.info(f"No matching Spotify playlists found for: {local_name}")
        return
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}Processing: {local_name}")
    print(f"{Fore.CYAN}Local tracks: {len(local_tracks)}")
    print(f"{Fore.CYAN}{'='*60}")
    
    # Handle exact matches
    if exact_playlists:
        if len(exact_playlists) == 1:
            playlist = exact_playlists[0]
            
            # Check if already processed
            if is_playlist_processed(local_path, playlist['id']):
                cached_decision = get_cached_reconcile_decision(local_path, playlist['id'], 'extra_tracks')
                if cached_decision:
                    print(f"{Fore.YELLOW}⏭️  Already processed (cached decision: {cached_decision})")
                    return
            
            print(f"{Fore.GREEN}✅ Found exact match: {playlist['name']} ({playlist['tracks']['total']} tracks)")
            
            # Find extra tracks
            extra_tracks = find_extra_tracks_in_spotify_playlist(sp, playlist['id'], local_tracks)
            
            if extra_tracks:
                print(f"\n{Fore.YELLOW}⚠️  Found {len(extra_tracks)} extra tracks in Spotify playlist:")
                for i, track in enumerate(extra_tracks[:5], 1):
                    artists = ', '.join(track['artists'])
                    print(f"  {i}. {artists} - {track['name']}")
                if len(extra_tracks) > 5:
                    print(f"  ... and {len(extra_tracks) - 5} more")
                
                # Check for cached decision
                cached_decision = get_cached_reconcile_decision(local_path, playlist['id'], 'extra_tracks')
                if cached_decision:
                    print(f"{Fore.CYAN}Using cached decision: {cached_decision}")
                    decision = cached_decision
                else:
                    decision = input(f"\n{Fore.CYAN}Remove these extra tracks? (y/n): ").lower().strip()
                    save_reconcile_decision(local_path, playlist['id'], 'extra_tracks', decision)
                
                if decision == 'y':
                    track_uris = [track['uri'] for track in extra_tracks]
                    removed = remove_tracks_from_playlist(sp, playlist['id'], track_uris)
                    print(f"{Fore.GREEN}✅ Removed {removed} extra tracks")
                else:
                    print(f"{Fore.YELLOW}Extra tracks kept in playlist")
            else:
                print(f"{Fore.GREEN}✅ No extra tracks found - playlist is in sync")
            
            mark_playlist_processed(local_path, playlist['id'])
            
        else:
            # Multiple exact matches - handle duplicates
            print(f"\n{Fore.YELLOW}⚠️  Found {len(exact_playlists)} duplicate playlists with exact name: {local_name}")
            
            # Check if we've already processed this duplicate set
            playlist_ids = [p['id'] for p in exact_playlists]
            cache_key = f"duplicate_set_{hash('_'.join(sorted(playlist_ids))) % 1000000}"
            cached_decision = load_from_cache(cache_key, CACHE_EXPIRATION_LONG)
            
            if cached_decision:
                print(f"{Fore.CYAN}Using cached decision for duplicate set")
                return
            
            # Show the duplicates
            for i, playlist in enumerate(exact_playlists, 1):
                print(f"  {i}. {playlist['name']} ({playlist['tracks']['total']} tracks)")
            
            # Find the best match based on track count and content similarity
            best_playlist = None
            best_score = -1
            
            for playlist in exact_playlists:
                # Simple heuristic: playlist closest to local track count
                track_count_diff = abs(playlist['tracks']['total'] - len(local_tracks))
                score = 1000 - track_count_diff  # Higher score is better
                
                if score > best_score:
                    best_score = score
                    best_playlist = playlist
            
            print(f"\n{Fore.CYAN}Recommended: Keep '{best_playlist['name']}' with {best_playlist['tracks']['total']} tracks")
            print(f"{Fore.CYAN}(Closest to local playlist with {len(local_tracks)} tracks)")
            
            decision = input(f"\n{Fore.CYAN}Delete duplicate playlists and keep the recommended one? (y/n): ").lower().strip()
            
            if decision == 'y':
                kept_playlist = best_playlist
                deleted_count = 0
                
                for playlist in exact_playlists:
                    if playlist['id'] != kept_playlist['id']:
                        if delete_spotify_playlist(sp, playlist['id']):
                            deleted_count += 1
                            print(f"{Fore.GREEN}✅ Deleted duplicate: {playlist['name']}")
                        else:
                            print(f"{Fore.RED}❌ Failed to delete: {playlist['name']}")
                
                print(f"{Fore.GREEN}✅ Kept playlist: {kept_playlist['name']}")
                print(f"{Fore.GREEN}✅ Deleted {deleted_count} duplicate playlists")
                
                # Now check for extra tracks in the kept playlist
                extra_tracks = find_extra_tracks_in_spotify_playlist(sp, kept_playlist['id'], local_tracks)
                
                if extra_tracks:
                    print(f"\n{Fore.YELLOW}Found {len(extra_tracks)} extra tracks in kept playlist")
                    decision = input(f"{Fore.CYAN}Remove these extra tracks? (y/n): ").lower().strip()
                    
                    if decision == 'y':
                        track_uris = [track['uri'] for track in extra_tracks]
                        removed = remove_tracks_from_playlist(sp, kept_playlist['id'], track_uris)
                        print(f"{Fore.GREEN}✅ Removed {removed} extra tracks")
                
                mark_playlist_processed(local_path, kept_playlist['id'])
            else:
                print(f"{Fore.YELLOW}Duplicate playlists kept")
            
            # Cache the decision for this duplicate set
            save_to_cache({'decision': decision, 'timestamp': time.time()}, cache_key)
    
    # Handle similar matches (only if no exact matches were found)
    elif similar_playlists:
        print(f"\n{Fore.YELLOW}⚠️  Found similar playlists that might be related:")
        for i, (playlist, similarity) in enumerate(similar_playlists[:3], 1):
            print(f"  {i}. {playlist['name']} ({similarity:.0f}% similar, {playlist['tracks']['total']} tracks)")
        
        # For similar matches, especially numbered variations like marco2 vs marco1/marco4,
        # we should be more careful and not auto-suggest actions
        print(f"\n{Fore.CYAN}These appear to be different playlists with similar names.")
        print(f"{Fore.CYAN}No automatic action recommended.")
        
        decision = input(f"\n{Fore.CYAN}Would you like to manually check any of these? (y/n): ").lower().strip()
        
        if decision == 'y':
            for i, (playlist, similarity) in enumerate(similar_playlists[:3], 1):
                check = input(f"Check '{playlist['name']}' for extra tracks? (y/n): ").lower().strip()
                
                if check == 'y':
                    extra_tracks = find_extra_tracks_in_spotify_playlist(sp, playlist['id'], local_tracks)
                    
                    if extra_tracks:
                        print(f"\n{Fore.YELLOW}Found {len(extra_tracks)} tracks in '{playlist['name']}' not in local '{local_name}':")
                        for j, track in enumerate(extra_tracks[:3], 1):
                            artists = ', '.join(track['artists'])
                            print(f"  {j}. {artists} - {track['name']}")
                        if len(extra_tracks) > 3:
                            print(f"  ... and {len(extra_tracks) - 3} more")
                        
                        remove = input(f"Remove these tracks? (y/n): ").lower().strip()
                        if remove == 'y':
                            track_uris = [track['uri'] for track in extra_tracks]
                            removed = remove_tracks_from_playlist(sp, playlist['id'], track_uris)
                            print(f"{Fore.GREEN}✅ Removed {removed} tracks from '{playlist['name']}'")
                    else:
                        print(f"{Fore.GREEN}✅ No extra tracks found in '{playlist['name']}'")

# Using converter's is_text_playlist_file instead
is_text_playlist_file = converter_is_text_playlist_file

def parse_text_playlist_file(file_path):
    """Parse a text file containing artist/song pairs."""
    tracks = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line:  # Skip empty lines
                continue
            
            # Try different separator patterns
            separators = [' - ', ' – ', ' — ', ' : ', ' :: ', '\t']
            artist = None
            title = None
            
            for sep in separators:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2:
                        artist = parts[0].strip()
                        title = parts[1].strip()
                        break
            
            # If no separator found, assume space-separated (artist first words, song rest)
            if not artist and len(line.split()) >= 2:
                words = line.split()
                # Simple heuristic: first 1-2 words are artist, rest is title
                if len(words) > 4:
                    artist = ' '.join(words[:2])
                    title = ' '.join(words[2:])
                else:
                    artist = words[0]
                    title = ' '.join(words[1:])
            
            if artist and title:
                tracks.append({
                    'artist': artist,
                    'title': title,
                    'album': None,
                    'duration': None
                })
    
    except Exception as e:
        logger.error(f"Error parsing text playlist file {file_path}: {e}")
    
    return tracks

def parse_playlist_file(file_path):
    """Parse a playlist file, supporting both standard formats and text files."""
    ext = os.path.splitext(file_path)[1].lower()
    
    # Try standard parser first
    if ext in SUPPORTED_EXTENSIONS:
        return original_parse_playlist_file(file_path)
    else:
        # For non-standard files, check if it's a text playlist
        if is_text_playlist_file(file_path):
            return parse_text_playlist_file(file_path)
        else:
            # Fall back to original parser
            return original_parse_playlist_file(file_path)

# Removed - using converter's find_playlist_files instead

def cleanup_spotify_playlists_to_match_local(sp, directory, user_id, similarity_threshold=None):
    """Clean up Spotify playlists to match local ones exactly (remove extra tracks)."""
    # Find playlist files - use the converter's function which already handles text files
    playlist_files = converter_find_playlist_files(directory)
    
    if not playlist_files:
        logger.info(f"No playlist files found in {directory}")
        return
    
    logger.info(f"Found {len(playlist_files)} playlist files")
    
    # Get all user playlists
    user_playlists = get_user_playlists(sp, user_id)
    
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"{Fore.CYAN}CLEANUP MODE - MATCH SPOTIFY TO LOCAL")
    print(f"{Fore.CYAN}{'='*70}")
    print(f"{Fore.WHITE}This will remove tracks from Spotify playlists that aren't in local versions")
    print(f"{Fore.CYAN}{'='*70}\n")
    
    # Ask for similarity threshold if not provided
    if similarity_threshold is None:
        print(f"\n{Fore.CYAN}Set the minimum similarity threshold for matching tracks (0-100).")
        print(f"{Fore.WHITE}• 100 = Exact match only (track must have identical artist and title)")
        print(f"{Fore.WHITE}• 90  = Very similar (allows minor differences like 'feat.' vs 'ft.')")
        print(f"{Fore.WHITE}• 80  = Similar (allows some variation in spelling/punctuation)")
        print(f"{Fore.WHITE}• 70  = Loose match (may include remixes or live versions)")
        print(f"{Fore.WHITE}• Default: 85 (recommended)\n")
        
        threshold_input = input(f"{Fore.CYAN}Enter threshold (or press Enter for default 85): ").strip()
        
        if threshold_input:
            try:
                similarity_threshold = int(threshold_input)
                if similarity_threshold < 0 or similarity_threshold > 100:
                    print(f"{Fore.YELLOW}Invalid threshold. Using default: 85")
                    similarity_threshold = 85
            except ValueError:
                print(f"{Fore.YELLOW}Invalid input. Using default: 85")
                similarity_threshold = 85
        else:
            similarity_threshold = 85
        
        print(f"\n{Fore.GREEN}Using similarity threshold: {similarity_threshold}%")
    
    total_cleaned = 0
    total_removed = 0
    
    for file_path in playlist_files:
        local_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Find exact matching Spotify playlist
        matching_playlist = None
        for playlist in user_playlists:
            if playlist['name'] == local_name:
                matching_playlist = playlist
                break
        
        if not matching_playlist:
            continue
        
        # Parse local playlist
        try:
            local_tracks = parse_playlist_file(file_path)
            if not local_tracks:
                continue
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            continue
        
        print(f"\n{Fore.CYAN}Processing: {local_name}")
        
        # Find extra tracks with similarity threshold
        extra_tracks = find_extra_tracks_in_spotify_playlist_with_threshold(
            sp, matching_playlist['id'], local_tracks, similarity_threshold
        )
        
        if extra_tracks:
            print(f"{Fore.YELLOW}Found {len(extra_tracks)} extra tracks to remove")
            
            # Auto-remove without asking
            track_uris = [track['uri'] for track in extra_tracks]
            removed = remove_tracks_from_playlist(sp, matching_playlist['id'], track_uris)
            
            if removed > 0:
                print(f"{Fore.GREEN}✅ Removed {removed} extra tracks")
                total_removed += removed
                total_cleaned += 1
            else:
                print(f"{Fore.RED}❌ Failed to remove tracks")
        else:
            print(f"{Fore.GREEN}✅ Already in sync - no extra tracks")
    
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"{Fore.CYAN}CLEANUP COMPLETE")
    print(f"{Fore.CYAN}{'='*50}")
    print(f"{Fore.WHITE}Playlists cleaned: {total_cleaned}")
    print(f"{Fore.WHITE}Total tracks removed: {total_removed}")
    print(f"{Fore.GREEN}✅ Cleanup completed successfully!")

def remove_playlist_suffixes(sp, user_id):
    """Remove .m3u and other file suffixes from Spotify playlist names."""
    # Get all user playlists
    user_playlists = get_user_playlists(sp, user_id)
    
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"{Fore.CYAN}REMOVE PLAYLIST SUFFIXES")
    print(f"{Fore.CYAN}{'='*70}")
    print(f"{Fore.WHITE}This will remove file extensions like .m3u from playlist names")
    print(f"{Fore.CYAN}{'='*70}\n")
    
    # Find playlists with suffixes
    playlists_with_suffixes = []
    suffixes = ['.m3u', '.m3u8', '.pls', '.txt']
    
    for playlist in user_playlists:
        for suffix in suffixes:
            if playlist['name'].lower().endswith(suffix):
                playlists_with_suffixes.append(playlist)
                break
    
    if not playlists_with_suffixes:
        print(f"{Fore.GREEN}No playlists found with file suffixes!")
        return
    
    print(f"{Fore.YELLOW}Found {len(playlists_with_suffixes)} playlists with file suffixes:")
    for playlist in playlists_with_suffixes:
        print(f"  • {playlist['name']} ({playlist['tracks']['total']} tracks)")
    
    confirm = input(f"\n{Fore.CYAN}Remove suffixes from all these playlists? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print(f"{Fore.YELLOW}Cancelled.")
        return
    
    # Process each playlist
    renamed_count = 0
    for playlist in playlists_with_suffixes:
        old_name = playlist['name']
        # Find and remove the suffix
        new_name = old_name
        for suffix in suffixes:
            if old_name.lower().endswith(suffix):
                new_name = old_name[:-len(suffix)]
                break
        
        try:
            sp.playlist_change_details(playlist['id'], name=new_name)
            print(f"{Fore.GREEN}✅ Renamed '{old_name}' to '{new_name}'")
            renamed_count += 1
        except Exception as e:
            print(f"{Fore.RED}❌ Failed to rename '{old_name}': {e}")
    
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"{Fore.CYAN}SUFFIX REMOVAL COMPLETE")
    print(f"{Fore.CYAN}{'='*50}")
    print(f"{Fore.WHITE}Playlists renamed: {renamed_count}")
    print(f"{Fore.GREEN}✅ Suffix removal completed successfully!")

def delete_duplicate_spotify_playlists(sp, directory, user_id):
    """Delete duplicate Spotify playlists that have the same name as local ones."""
    # Find playlist files - the converter's find_playlist_files already handles text files
    playlist_files = converter_find_playlist_files(directory)
    
    if not playlist_files:
        logger.info(f"No playlist files found in {directory}")
        return
    
    # Get local playlist names
    local_playlist_names = set()
    for file_path in playlist_files:
        local_name = os.path.splitext(os.path.basename(file_path))[0]
        local_playlist_names.add(local_name)
    
    logger.info(f"Found {len(local_playlist_names)} unique local playlist names")
    
    # Get all user playlists
    user_playlists = get_user_playlists(sp, user_id)
    
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"{Fore.CYAN}DELETE DUPLICATES MODE")
    print(f"{Fore.CYAN}{'='*70}")
    print(f"{Fore.WHITE}This will detect and handle duplicate Spotify playlists")
    print(f"{Fore.WHITE}including those with file extensions like .m3u")
    print(f"{Fore.WHITE}(Keeps the one with most tracks, offers to delete the rest)")
    print(f"{Fore.CYAN}{'='*70}\n")
    
    # Group playlists by base name (without extensions)
    playlist_groups = {}
    processed_names = set()  # Track which playlists we've already grouped
    
    for playlist in user_playlists:
        name = playlist['name']
        
        # Skip if already processed as part of another group
        if name in processed_names:
            continue
            
        # Check if this playlist name matches any local playlist
        base_name = None
        for local_name in local_playlist_names:
            # Check exact match
            if name == local_name:
                base_name = local_name
                break
            # Check if it's the local name with an extension
            elif name.startswith(local_name + '.'):
                base_name = local_name
                break
            # Check if the playlist name without extension matches
            elif name.endswith(('.m3u', '.m3u8', '.pls', '.txt')):
                name_without_ext = name.rsplit('.', 1)[0]
                if name_without_ext == local_name:
                    base_name = local_name
                    break
        
        if base_name:
            if base_name not in playlist_groups:
                playlist_groups[base_name] = []
            
            # Add this playlist
            playlist_groups[base_name].append(playlist)
            processed_names.add(name)
            
            # Look for other playlists with similar names
            for other_playlist in user_playlists:
                other_name = other_playlist['name']
                if other_name in processed_names:
                    continue
                    
                # Check if it's the same base name with different extension
                if (other_name == base_name or 
                    other_name.startswith(base_name + '.') or
                    (other_name.endswith(('.m3u', '.m3u8', '.pls', '.txt')) and 
                     other_name.rsplit('.', 1)[0] == base_name)):
                    playlist_groups[base_name].append(other_playlist)
                    processed_names.add(other_name)
    
    total_deleted = 0
    duplicates_to_process = []
    
    # First, collect all duplicate groups
    for base_name, playlists in playlist_groups.items():
        if len(playlists) > 1:
            duplicates_to_process.append((base_name, playlists))
    
    if not duplicates_to_process:
        print(f"\n{Fore.GREEN}No duplicate playlists found!")
        return
    
    # Show summary
    print(f"\n{Fore.YELLOW}Found {len(duplicates_to_process)} groups of duplicate playlists")
    total_duplicates = sum(len(playlists) - 1 for _, playlists in duplicates_to_process)
    print(f"{Fore.YELLOW}Total duplicate playlists that can be removed: {total_duplicates}")
    
    # Ask for bulk action
    print(f"\n{Fore.CYAN}Options:")
    print(f"1. Remove ALL duplicates automatically (keep the one with most tracks)")
    print(f"2. Review each group individually")
    print(f"3. Cancel")
    
    bulk_choice = input(f"\n{Fore.CYAN}Choose option (1-3): ").strip()
    
    if bulk_choice == "1":
        # Bulk remove all duplicates
        print(f"\n{Fore.YELLOW}Removing all duplicate playlists...")
        for base_name, playlists in duplicates_to_process:
            # Sort by track count (keep the one with most tracks)
            playlists.sort(key=lambda p: p['tracks']['total'], reverse=True)
            kept_playlist = playlists[0]
            
            print(f"\n{Fore.CYAN}Processing '{base_name}':")
            print(f"  Keeping: {kept_playlist['name']} ({kept_playlist['tracks']['total']} tracks)")
            
            # Check if the kept playlist needs renaming (has .m3u suffix)
            if kept_playlist['name'].endswith(('.m3u', '.m3u8', '.pls', '.txt')):
                # Rename to remove suffix
                new_name = kept_playlist['name'].rsplit('.', 1)[0]
                try:
                    sp.playlist_change_details(kept_playlist['id'], name=new_name)
                    print(f"{Fore.GREEN}  ✅ Renamed '{kept_playlist['name']}' to '{new_name}'")
                    kept_playlist['name'] = new_name
                except Exception as e:
                    print(f"{Fore.RED}  ❌ Failed to rename: {e}")
            
            # Delete the rest
            for playlist in playlists[1:]:
                if delete_spotify_playlist(sp, playlist['id']):
                    print(f"  {Fore.GREEN}✅ Deleted: {playlist['name']} ({playlist['tracks']['total']} tracks)")
                    total_deleted += 1
                else:
                    print(f"  {Fore.RED}❌ Failed to delete: {playlist['name']}")
    
    elif bulk_choice == "2":
        # Individual review
        for base_name, playlists in duplicates_to_process:
            if len(playlists) > 1:
                print(f"\n{Fore.YELLOW}Found {len(playlists)} duplicate playlists for '{base_name}':")
                
                # Sort by track count (keep the one with most tracks)
                playlists.sort(key=lambda p: p['tracks']['total'], reverse=True)
                
                for i, playlist in enumerate(playlists):
                    suffix_note = ""
                    if playlist['name'] != base_name:
                        suffix_note = f" {Fore.YELLOW}(with suffix)"
                    print(f"  {i+1}. {playlist['name']} ({playlist['tracks']['total']} tracks){suffix_note}")
                
                print(f"\n{Fore.CYAN}These appear to be the same playlist with different names/extensions.")
                print(f"{Fore.CYAN}The playlist with most tracks has {playlists[0]['tracks']['total']} tracks: {playlists[0]['name']}")
                print(f"\n{Fore.CYAN}Options:")
                print(f"1. Keep the playlist with most tracks, delete others")
                print(f"2. Keep all playlists as separate")
                print(f"3. Skip this group")
                
                choice = input(f"\n{Fore.CYAN}Choose option (1-3): ").strip()
                
                if choice == "1":
                    # Delete all but the first (largest) playlist
                    kept_playlist = playlists[0]
                    
                    # Check if the kept playlist needs renaming (has .m3u suffix)
                    if kept_playlist['name'].endswith(('.m3u', '.m3u8', '.pls', '.txt')):
                        # Rename to remove suffix
                        new_name = kept_playlist['name'].rsplit('.', 1)[0]
                        try:
                            sp.playlist_change_details(kept_playlist['id'], name=new_name)
                            print(f"{Fore.GREEN}✅ Renamed '{kept_playlist['name']}' to '{new_name}'")
                            kept_playlist['name'] = new_name
                        except Exception as e:
                            print(f"{Fore.RED}❌ Failed to rename: {e}")
                    
                    for playlist in playlists[1:]:
                        if delete_spotify_playlist(sp, playlist['id']):
                            print(f"{Fore.GREEN}✅ Deleted duplicate: {playlist['name']} ({playlist['tracks']['total']} tracks)")
                            total_deleted += 1
                        else:
                            print(f"{Fore.RED}❌ Failed to delete: {playlist['name']}")
                    print(f"{Fore.GREEN}✅ Kept: {kept_playlist['name']} ({kept_playlist['tracks']['total']} tracks)")
                elif choice == "2":
                    print(f"{Fore.YELLOW}Keeping all playlists as separate.")
                else:
                    print(f"{Fore.YELLOW}Skipping this group.")
    
    elif bulk_choice == "3":
        print(f"{Fore.YELLOW}Cancelled.")
        return
    
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"{Fore.CYAN}DUPLICATE DELETION COMPLETE")
    print(f"{Fore.CYAN}{'='*50}")
    print(f"{Fore.WHITE}Duplicates deleted: {total_deleted}")
    print(f"{Fore.GREEN}✅ Duplicate deletion completed successfully!")

def main():
    """Main function to run the playlist reconciliation."""
    parser = argparse.ArgumentParser(description="Reconcile Spotify playlists with local playlist files")
    parser.add_argument("directory", nargs="?", default=".", help="Directory containing local playlist files (default: current directory)")
    parser.add_argument("--clear-cache", action="store_true", help="Clear processed playlist cache")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--max-playlists", type=int, help="Maximum number of playlists to process")
    
    # New mode arguments
    parser.add_argument("--cleanup-mode", action="store_true", help="Clean up Spotify playlists to match local ones exactly")
    parser.add_argument("--delete-duplicates-mode", action="store_true", help="Delete duplicate Spotify playlists")
    parser.add_argument("--remove-suffixes-mode", action="store_true", help="Remove .m3u and other file suffixes from playlist names")
    
    args = parser.parse_args()
    
    # Set up logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Handle cache clearing
    if args.clear_cache:
        clear_processed_playlist_cache()
        return
    
    # Resolve directory path
    directory = os.path.abspath(args.directory)
    
    if not os.path.isdir(directory):
        logger.error(f"Directory not found: {directory}")
        sys.exit(1)
    
    # Find playlist files - use converter's function which handles the prompting
    logger.info(f"Searching for playlist files in: {directory}")
    playlist_files = converter_find_playlist_files(directory)
    
    if not playlist_files:
        logger.info(f"No playlist files found in {directory}")
        sys.exit(0)
    
    logger.info(f"Found {len(playlist_files)} playlist files")
    
    # Limit number of playlists if specified
    if args.max_playlists:
        playlist_files = playlist_files[:args.max_playlists]
        logger.info(f"Limited to {len(playlist_files)} playlists")
    
    # Authenticate with Spotify
    logger.info("Authenticating with Spotify...")
    sp = authenticate_spotify()
    
    if not sp:
        logger.error("Failed to authenticate with Spotify")
        sys.exit(1)
    
    # Get user info
    user_info = sp.current_user()
    user_id = user_info['id']
    logger.info(f"Authenticated as: {user_info['display_name']} ({user_id})")
    
    # Handle different modes
    if args.cleanup_mode:
        # Cleanup mode - remove extra tracks
        cleanup_spotify_playlists_to_match_local(sp, directory, user_id)
        return
    
    elif args.delete_duplicates_mode:
        # Delete duplicates mode
        delete_duplicate_spotify_playlists(sp, directory, user_id)
        return
    
    elif args.remove_suffixes_mode:
        # Remove suffixes mode
        remove_playlist_suffixes(sp, user_id)
        return
    
    # Default reconciliation mode
    # Get all user playlists
    logger.info("Fetching user playlists...")
    user_playlists = get_user_playlists(sp, user_id)
    logger.info(f"Found {len(user_playlists)} Spotify playlists")
    
    # Process each local playlist
    processed_count = 0
    
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"{Fore.CYAN}SPOTIFY PLAYLIST RECONCILIATION")
    print(f"{Fore.CYAN}{'='*70}")
    print(f"{Fore.WHITE}This tool will:")
    print(f"{Fore.WHITE}• Find extra tracks in Spotify playlists vs local versions")
    print(f"{Fore.WHITE}• Detect and handle duplicate Spotify playlists")
    print(f"{Fore.WHITE}• Use improved matching to avoid false positives")
    print(f"{Fore.CYAN}{'='*70}")
    
    for i, file_path in enumerate(playlist_files, 1):
        try:
            logger.info(f"\nProcessing playlist {i}/{len(playlist_files)}: {os.path.basename(file_path)}")
            reconcile_playlist_pair(sp, file_path, user_playlists, user_id)
            processed_count += 1
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            if args.debug:
                traceback.print_exc()
    
    # Print summary
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"{Fore.CYAN}RECONCILIATION COMPLETE")
    print(f"{Fore.CYAN}{'='*50}")
    print(f"{Fore.WHITE}Playlists processed: {processed_count}/{len(playlist_files)}")
    print(f"{Fore.WHITE}Use --clear-cache to reset processed playlist tracking")
    print(f"{Fore.GREEN}✅ Reconciliation completed successfully!")

if __name__ == "__main__":
    main()