#!/usr/bin/env python3
"""
Spotify Library Cleanup Tool

Analyzes and cleans up your Spotify library by removing:
- Songs you've never played
- Songs from artists you don't follow
- Unavailable/grayed out tracks
- Orphaned songs (not in any playlist)
- Old songs you haven't listened to in years

Features smart cleanup modes and integrates with exclusion list to prevent
re-adding cleaned songs.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from credentials_manager import get_spotify_credentials
from cache_utils import save_to_cache, load_from_cache, validate_artist_data
from spotify_utils import (
    create_spotify_client, print_success, print_error, print_warning, print_info, print_header,
    fetch_user_playlists, fetch_user_saved_tracks, fetch_playlist_tracks,
    fetch_followed_artists, fetch_recently_played
)
from constants import CACHE_EXPIRATION, BATCH_SIZES, SPOTIFY_SCOPES
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
from exclusion_manager import add_bulk_exclusions, is_excluded, get_exclusion_count
from preferences_manager import get_cleanup_mode, should_create_backup, should_always_confirm

# Spotify API scopes needed
SCOPES = SPOTIFY_SCOPES['modify']

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        return create_spotify_client(SCOPES, "library_cleanup")
    except Exception as e:
        print_error(f"Error setting up Spotify client: {e}")
        sys.exit(1)

def analyze_library_health(sp):
    """
    Analyze the health of the user's Spotify library.

    Returns dict with:
    - total_liked_songs
    - songs_in_playlists
    - orphaned_songs (not in any playlist)
    - categorized issues
    """
    print_header("Analyzing Library Health")

    # Get all liked songs
    print_info("Fetching your liked songs...")
    saved_tracks_data = fetch_user_saved_tracks(
        sp,
        show_progress=True,
        cache_key="liked_songs_cleanup",
        cache_expiration=CACHE_EXPIRATION['short']  # 1 hour cache
    )

    total_liked = len(saved_tracks_data)
    print_success(f"Found {total_liked} liked songs")

    # Get all user playlists
    print_info("Fetching your playlists...")
    playlists = fetch_user_playlists(
        sp,
        show_progress=True,
        cache_key="user_playlists_cleanup",
        cache_expiration=CACHE_EXPIRATION['short']
    )

    # Filter to only user's own playlists
    user_id = sp.current_user()['id']
    user_playlists = [p for p in playlists if p['owner']['id'] == user_id]
    print_success(f"Found {len(user_playlists)} playlists you created")

    # Build set of all tracks in playlists
    print_info("Analyzing which liked songs are in playlists...")
    tracks_in_playlists = set()

    progress_bar = create_progress_bar(total=len(user_playlists), desc="Scanning playlists", unit="playlist")

    for playlist in user_playlists:
        playlist_tracks = fetch_playlist_tracks(
            sp,
            playlist['id'],
            show_progress=False,
            cache_key=f"playlist_tracks_cleanup_{playlist['id']}",
            cache_expiration=CACHE_EXPIRATION['medium']
        )

        for item in playlist_tracks:
            if item.get('track') and item['track'].get('id'):
                tracks_in_playlists.add(item['track']['id'])

        update_progress_bar(progress_bar, 1)

    close_progress_bar(progress_bar)

    # Find orphaned songs
    orphaned_songs = []
    for item in saved_tracks_data:
        if item.get('track') and item['track'].get('id'):
            track_id = item['track']['id']
            if track_id not in tracks_in_playlists:
                orphaned_songs.append({
                    'id': track_id,
                    'name': item['track']['name'],
                    'artists': item['track'].get('artists', []),
                    'added_at': item.get('added_at'),
                    'track_data': item['track']
                })

    print_success(f"Analysis complete!")
    print_info(f"\nResults:")
    print_info(f"  Total liked songs: {total_liked}")
    print_info(f"  Songs in your playlists: {len(tracks_in_playlists)}")
    print_info(f"  Orphaned songs (not in playlists): {len(orphaned_songs)}")
    print_info(f"  Percentage orphaned: {len(orphaned_songs)/total_liked*100:.1f}%")

    return {
        'total_liked_songs': total_liked,
        'songs_in_playlists': len(tracks_in_playlists),
        'orphaned_songs': orphaned_songs,
        'all_liked_songs': saved_tracks_data,
        'playlist_track_ids': tracks_in_playlists
    }

def categorize_songs_by_criteria(sp, songs_data):
    """
    Categorize songs by various cleanup criteria.

    Returns dict with categorized lists.
    """
    print_info("\nCategorizing songs by cleanup criteria...")

    categories = {
        'never_played': [],
        'played_once': [],
        'not_played_2years': [],
        'from_unfollowed_artists': [],
        'unavailable': [],
        'podcasts': [],
        'already_excluded': []
    }

    # Get followed artists (using cached version with progress bar)
    try:
        followed_artists = fetch_followed_artists(
            sp,
            show_progress=True,
            cache_key="followed_artists_cleanup",
            cache_expiration=CACHE_EXPIRATION['medium']  # 6 hours
        )
        followed_artist_ids = {artist['id'] for artist in followed_artists}
        print_success(f"You follow {len(followed_artist_ids)} artists")
    except Exception as e:
        print_warning(f"Could not fetch followed artists: {e}")
        followed_artist_ids = set()

    # Get recently played to determine play counts (Spotify doesn't expose play counts directly)
    # We can only check if a song appears in recently played (using cached version)
    try:
        recently_played = fetch_recently_played(
            sp,
            limit=50,
            show_progress=False,  # Don't show progress for this quick API call
            cache_key="recently_played_cleanup",
            cache_expiration=CACHE_EXPIRATION['short']  # 1 hour
        )
        recently_played_ids = {item['track']['id'] for item in recently_played if item.get('track')}
    except Exception as e:
        print_warning(f"Could not fetch recently played: {e}")
        recently_played_ids = set()

    # Calculate date threshold for "not played in 2 years"
    two_years_ago = datetime.now() - timedelta(days=730)

    progress_bar = create_progress_bar(total=len(songs_data), desc="Categorizing songs", unit="song")

    for item in songs_data:
        if not item.get('track') or not item['track'].get('id'):
            update_progress_bar(progress_bar, 1)
            continue

        track = item['track']
        track_id = track['id']

        # Check if already excluded
        if is_excluded(track_id, 'track'):
            categories['already_excluded'].append(track)
            update_progress_bar(progress_bar, 1)
            continue

        # Check if unavailable
        if track.get('is_playable') is False or not track.get('uri'):
            categories['unavailable'].append(track)

        # Check if podcast episode
        if track.get('type') == 'episode':
            categories['podcasts'].append(track)

        # Check if from unfollowed artist
        track_artists = track.get('artists', [])
        is_from_followed = False
        for artist in track_artists:
            validated_artist = validate_artist_data(artist)
            if validated_artist and validated_artist['id'] in followed_artist_ids:
                is_from_followed = True
                break

        if not is_from_followed and track_artists:
            categories['from_unfollowed_artists'].append(track)

        # Check play status (heuristic based on recently played)
        if track_id not in recently_played_ids:
            # Not in recent plays - likely never played or rarely played
            # This is a heuristic since Spotify doesn't expose play counts
            categories['never_played'].append(track)

        # Check added date for old songs
        added_at_str = item.get('added_at')
        if added_at_str:
            try:
                added_date = datetime.fromisoformat(added_at_str.replace('Z', '+00:00'))
                if added_date.replace(tzinfo=None) < two_years_ago:
                    if track_id not in recently_played_ids:
                        categories['not_played_2years'].append(track)
            except (ValueError, AttributeError):
                pass

        update_progress_bar(progress_bar, 1)

    close_progress_bar(progress_bar)

    return categories

def show_category_selection_menu(analysis, categories):
    """
    Display category-based cleanup options and allow user to select.

    Returns list of selected category names, or None if cancelled.
    """
    print_header("Smart Cleanup - Choose Categories")

    # Show available categories with counts
    available_options = []

    # High priority categories
    print_info("🔴 High Priority:")
    if len(categories['unavailable']) > 0:
        available_options.append(('unavailable', f"Remove {len(categories['unavailable'])} unavailable tracks (can't be played)"))
        print_info(f"  [1] Remove {len(categories['unavailable'])} unavailable tracks")

    if len(categories['podcasts']) > 0:
        available_options.append(('podcasts', f"Remove {len(categories['podcasts'])} podcast episodes"))
        print_info(f"  [{len(available_options) + 1}] Remove {len(categories['podcasts'])} podcast episodes")

    if len(analysis['orphaned_songs']) > 0:
        available_options.append(('orphaned', f"Remove {len(analysis['orphaned_songs'])} orphaned songs (not in playlists)"))
        print_info(f"  [{len(available_options) + 1}] Remove {len(analysis['orphaned_songs'])} orphaned songs")

    # Medium priority categories
    if categories['from_unfollowed_artists'] or categories['not_played_2years']:
        print_info("\n🟡 Medium Priority:")

    if len(categories['from_unfollowed_artists']) > 0:
        available_options.append(('unfollowed_artists', f"Remove {len(categories['from_unfollowed_artists'])} songs from artists you don't follow"))
        print_info(f"  [{len(available_options) + 1}] Remove {len(categories['from_unfollowed_artists'])} songs from unfollowed artists")

    if len(categories['not_played_2years']) > 0:
        available_options.append(('old_unplayed', f"Remove {len(categories['not_played_2years'])} old songs (2+ years, not recently played)"))
        print_info(f"  [{len(available_options) + 1}] Remove {len(categories['not_played_2years'])} old unplayed songs")

    # Already handled
    if len(categories['already_excluded']) > 0:
        print_info("\n✅ Already Handled:")
        print_info(f"  • {len(categories['already_excluded'])} songs in exclusion list")

    # No issues found
    if not available_options:
        print_success("\n🎉 No cleanup needed! Your library is in great shape.")
        return None

    # Selection options
    print_info(f"\n  [{len(available_options) + 1}] Custom: Select multiple categories")
    print_info(f"  [{len(available_options) + 2}] Cancel")

    # Get user selection
    choice = input(f"\nEnter your choice (1-{len(available_options) + 2}): ").strip()

    try:
        choice_num = int(choice)

        # Single category selection
        if 1 <= choice_num <= len(available_options):
            selected_category = available_options[choice_num - 1][0]
            return [selected_category]

        # Custom multi-select
        elif choice_num == len(available_options) + 1:
            print_info("\nSelect categories to remove (comma-separated numbers):")
            for i, (_, desc) in enumerate(available_options, 1):
                print_info(f"  [{i}] {desc}")

            selections = input(f"\nEnter numbers (e.g., 1,2,3): ").strip()
            selected_nums = [int(n.strip()) for n in selections.split(',') if n.strip().isdigit()]

            selected_categories = []
            for num in selected_nums:
                if 1 <= num <= len(available_options):
                    selected_categories.append(available_options[num - 1][0])

            if selected_categories:
                return selected_categories
            else:
                print_warning("No valid categories selected")
                return None

        # Cancel
        else:
            print_info("Cleanup cancelled")
            return None

    except (ValueError, IndexError):
        print_warning("Invalid selection")
        return None

def unlike_tracks(sp, track_ids, add_to_exclusions=True):
    """
    Unlike tracks and optionally add to exclusion list.

    Returns number of tracks successfully unliked.
    """
    if not track_ids:
        print_warning("No tracks to unlike")
        return 0

    print_info(f"\nUnliking {len(track_ids)} tracks...")

    # Process in batches
    batch_size = BATCH_SIZES['spotify_tracks']
    unliked_count = 0
    failed_count = 0

    progress_bar = create_progress_bar(total=len(track_ids), desc="Unliking tracks", unit="track")

    for i in range(0, len(track_ids), batch_size):
        batch = track_ids[i:i + batch_size]

        try:
            sp.current_user_saved_tracks_delete(batch)
            unliked_count += len(batch)

            # Small delay between batches
            if i + batch_size < len(track_ids):
                time.sleep(0.05)
        except Exception as e:
            print_warning(f"Error unliking batch: {e}")
            failed_count += len(batch)

        update_progress_bar(progress_bar, len(batch))

    close_progress_bar(progress_bar)

    # Add to exclusion list
    if add_to_exclusions and unliked_count > 0:
        print_info("Adding unliked tracks to exclusion list...")
        excluded_count = add_bulk_exclusions(
            track_ids[:unliked_count],
            item_type="track",
            reason="Library cleanup"
        )

    # Invalidate cache
    save_to_cache(None, "liked_songs_cleanup", force_expire=True)

    print_success(f"\nSuccessfully unliked {unliked_count} tracks")
    if failed_count > 0:
        print_warning(f"Failed to unlike {failed_count} tracks")

    return unliked_count

def execute_cleanup(sp, selected_categories, analysis, categories):
    """
    Execute cleanup based on selected categories.

    Args:
        sp: Spotify client
        selected_categories: List of category names to clean (e.g., ['unavailable', 'podcasts'])
        analysis: Dict from analyze_library_health()
        categories: Dict from categorize_songs_by_criteria()

    Returns:
        Number of tracks successfully unliked
    """
    tracks_to_remove = []
    category_names = []

    # Category mapping
    category_map = {
        'unavailable': ('unavailable', 'unavailable tracks'),
        'podcasts': ('podcasts', 'podcast episodes'),
        'orphaned': ('orphaned_songs', 'orphaned songs'),  # From analysis, not categories
        'unfollowed_artists': ('from_unfollowed_artists', 'songs from unfollowed artists'),
        'old_unplayed': ('not_played_2years', 'old unplayed songs')
    }

    # Build tracks list from selected categories
    for cat_key in selected_categories:
        if cat_key not in category_map:
            continue

        source_key, display_name = category_map[cat_key]
        category_names.append(display_name)

        # Special handling for orphaned songs (from analysis dict)
        if cat_key == 'orphaned':
            tracks_to_remove.extend(analysis['orphaned_songs'])
        else:
            # From categories dict
            tracks_to_remove.extend(categories[source_key])

    if not tracks_to_remove:
        print_warning("No tracks selected for cleanup")
        return 0

    # Build reason string
    reason = f"Cleanup: {', '.join(category_names)}"

    # Extract track IDs (handling different data structures)
    track_ids = []
    for track in tracks_to_remove:
        if isinstance(track, dict):
            if 'id' in track:
                track_ids.append(track['id'])
            elif 'track_data' in track and track['track_data'].get('id'):
                track_ids.append(track['track_data']['id'])

    # Remove duplicates
    track_ids = list(set(track_ids))

    if not track_ids:
        print_warning("No tracks to remove")
        return 0

    # Show preview
    print_info(f"\nYou're about to unlike {len(track_ids)} songs")
    print_info(f"Categories: {', '.join(category_names)}")
    print_info(f"\nFirst 10 tracks:")
    for i, track_id in enumerate(track_ids[:10]):
        for track in tracks_to_remove:
            t = track if isinstance(track, dict) and 'id' in track else track.get('track_data', {})
            if t.get('id') == track_id:
                artist_names = [a.get('name', 'Unknown') for a in t.get('artists', [])]
                print_info(f"  {i+1}. {t.get('name', 'Unknown')} - {', '.join(artist_names)}")
                break

    if len(track_ids) > 10:
        print_info(f"  ... and {len(track_ids) - 10} more")

    # Confirm
    if should_always_confirm():
        response = input("\nProceed with cleanup? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print_info("Cleanup cancelled")
            return 0

    # Execute
    return unlike_tracks(sp, track_ids, add_to_exclusions=True)

def main_menu():
    """Display main cleanup menu and handle user choice."""
    while True:
        print_header("Library Cleanup")
        print_info("\nWhat would you like to do?\n")
        print_info("  1. Smart cleanup (choose categories to remove)")
        print_info("  2. Remove orphaned songs only")
        print_info("  3. Remove unavailable tracks only")
        print_info("  4. Remove podcast episodes only")
        print_info("  5. View exclusion list stats")
        print_info("  6. Back to main menu")

        choice = input("\nEnter your choice (1-6): ").strip()

        if choice == "6":
            break

        # Set up Spotify client
        sp = setup_spotify_client()

        if choice == "1":
            # Smart cleanup with category selection
            analysis = analyze_library_health(sp)
            categories = categorize_songs_by_criteria(sp, analysis['all_liked_songs'])

            # Show category selection menu (will be implemented next)
            selected_categories = show_category_selection_menu(analysis, categories)

            if selected_categories:
                execute_cleanup(sp, selected_categories, analysis, categories)

            input("\nPress Enter to continue...")

        elif choice == "2":
            # Orphaned songs only
            analysis = analyze_library_health(sp)
            orphaned_ids = [song['id'] for song in analysis['orphaned_songs']]

            if orphaned_ids:
                print_info(f"\nFound {len(orphaned_ids)} orphaned songs")
                response = input("Remove all orphaned songs? (yes/no): ").strip().lower()
                if response in ['yes', 'y']:
                    unlike_tracks(sp, orphaned_ids, add_to_exclusions=True)
            else:
                print_success("No orphaned songs found!")

            input("\nPress Enter to continue...")

        elif choice == "3":
            # Unavailable tracks only
            analysis = analyze_library_health(sp)
            categories = categorize_songs_by_criteria(sp, analysis['all_liked_songs'])
            unavailable_ids = [t['id'] for t in categories['unavailable'] if t.get('id')]

            if unavailable_ids:
                print_info(f"\nFound {len(unavailable_ids)} unavailable tracks")
                response = input("Remove all unavailable tracks? (yes/no): ").strip().lower()
                if response in ['yes', 'y']:
                    unlike_tracks(sp, unavailable_ids, add_to_exclusions=True)
            else:
                print_success("No unavailable tracks found!")

            input("\nPress Enter to continue...")

        elif choice == "4":
            # Podcasts only
            analysis = analyze_library_health(sp)
            categories = categorize_songs_by_criteria(sp, analysis['all_liked_songs'])
            podcast_ids = [t['id'] for t in categories['podcasts'] if t.get('id')]

            if podcast_ids:
                print_info(f"\nFound {len(podcast_ids)} podcast episodes")
                response = input("Remove all podcast episodes? (yes/no): ").strip().lower()
                if response in ['yes', 'y']:
                    unlike_tracks(sp, podcast_ids, add_to_exclusions=True)
            else:
                print_success("No podcast episodes found!")

            input("\nPress Enter to continue...")

        elif choice == "5":
            # Exclusion stats
            from exclusion_manager import show_exclusion_stats
            show_exclusion_stats()
            input("\nPress Enter to continue...")

        else:
            print_warning("Invalid choice")

def main():
    """Main entry point."""
    try:
        main_menu()
    except KeyboardInterrupt:
        print_warning("\n\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
