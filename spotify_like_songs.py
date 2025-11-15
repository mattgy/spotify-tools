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
from spotify_utils import (
    create_spotify_client, COMMON_SCOPES, print_success, print_error, print_warning, print_info,
    fetch_user_playlists, fetch_user_saved_tracks, fetch_playlist_tracks, fetch_followed_artists
)
from constants import BATCH_SIZES, CONFIDENCE_THRESHOLDS

# Import tqdm_utils for progress bars
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

# Spotify API scopes needed for this script
SCOPES = [
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "user-follow-read",
    "user-follow-modify"
]

# Import cache expiration from constants
from constants import DEFAULT_CACHE_EXPIRATION, STANDARD_CACHE_KEYS

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
    all_playlists = fetch_user_playlists(sp, show_progress=True, cache_key=STANDARD_CACHE_KEYS['user_playlists'], cache_expiration=DEFAULT_CACHE_EXPIRATION)
    
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
            cache_expiration=DEFAULT_CACHE_EXPIRATION
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
    saved_tracks_data = fetch_user_saved_tracks(sp, show_progress=True, cache_key=STANDARD_CACHE_KEYS['liked_songs'], cache_expiration=DEFAULT_CACHE_EXPIRATION)
    
    # Convert to set of track IDs for efficient lookup
    saved_tracks = {item['track']['id'] for item in saved_tracks_data if item['track']}
    
    print(f"You have {len(saved_tracks)} saved tracks")
    return saved_tracks

def like_tracks(sp, tracks, saved_tracks):
    """Like tracks that the user hasn't already saved."""
    # Filter out tracks already saved
    new_tracks = [t for t in tracks if t['id'] not in saved_tracks]
    
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
    processed = 0
    
    for i in range(0, len(new_tracks), batch_size):
        batch = new_tracks[i:i+batch_size]
        track_ids = [t['id'] for t in batch]
        
        try:
            sp.current_user_saved_tracks_add(track_ids)
            processed += len(batch)
            
            # Update progress bar
            update_progress_bar(progress_bar, len(batch))
            
            # SafeSpotifyClient handles rate limiting automatically
        except Exception as e:
            print(f"Error liking tracks: {e}")
            print("Continuing with next batch...")
            # Still update progress even on error
            update_progress_bar(progress_bar, len(batch))
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    print(f"Successfully liked {len(new_tracks)} new tracks!")
    
    # Invalidate the saved tracks cache
    save_to_cache(None, "all_liked_songs", force_expire=True)
    
    return new_tracks  # Return the liked tracks for analysis

def analyze_artist_frequency(tracks):
    """Analyze which artists appear frequently in liked tracks."""
    artist_counts = defaultdict(int)
    artist_tracks = defaultdict(list)
    
    for track in tracks:
        for artist in track['artists']:
            # Handle backwards compatibility with old cache format (artist as string)
            if isinstance(artist, str):
                # Old cached data had artists as strings (just names)
                # Skip these for analysis since we need artist IDs
                continue

            # Validate artist data structure
            if not isinstance(artist, dict) or 'id' not in artist or 'name' not in artist:
                # Malformed artist data - skip silently
                continue
                
            artist_id = artist['id']
            artist_name = artist['name']
            artist_counts[artist_id] += 1
            artist_tracks[artist_id].append({
                'track_name': track['name'],
                'artist_name': artist_name
            })
    
    return artist_counts, artist_tracks

def get_followed_artists(sp):
    """Get list of currently followed artists using centralized fetch function."""
    # Use centralized function which handles caching, progress, and rate limiting
    followed_artists_data = fetch_followed_artists(
        sp,
        show_progress=False,
        cache_key="followed_artists_for_autofollow",
        cache_expiration=3600  # Cache for 1 hour
    )
    
    # Convert to set of artist IDs for efficient lookup
    followed_artists = {artist['id'] for artist in followed_artists_data}
    
    return followed_artists

def suggest_artists_to_follow(sp, liked_tracks, min_songs=3):
    """Suggest artists to follow based on liked songs frequency."""
    print(f"\nAnalyzing artists from your newly liked songs...")
    
    # Analyze artist frequency
    artist_counts, artist_tracks = analyze_artist_frequency(liked_tracks)
    
    # Get currently followed artists
    followed_artists = get_followed_artists(sp)
    
    # Find artists with multiple songs that aren't followed
    candidate_artist_ids = [artist_id for artist_id, count in artist_counts.items() 
                           if count >= min_songs and artist_id not in followed_artists]
    
    if not candidate_artist_ids:
        return []
    
    # Use batch function to get artist details efficiently
    from spotify_utils import batch_get_artist_details
    
    artist_details = batch_get_artist_details(
        sp, 
        candidate_artist_ids, 
        show_progress=True, 
        cache_key_prefix="follow_suggestion_artist_details",
        cache_expiration=7 * 24 * 60 * 60  # 7 days
    )
    
    # Build suggestions from batch results
    suggestions = []
    for artist_id in candidate_artist_ids:
        if artist_id in artist_details:
            artist = artist_details[artist_id]
            suggestions.append({
                'id': artist_id,
                'name': artist['name'],
                'song_count': artist_counts[artist_id],
                'popularity': artist['popularity'],
                'genres': artist['genres'],
                'tracks': artist_tracks[artist_id]
            })
    
    # Sort by song count (most frequent first)
    suggestions.sort(key=lambda x: x['song_count'], reverse=True)
    
    return suggestions

def auto_follow_artists(sp, suggestions, auto_threshold=5):
    """Auto-follow artists based on suggestions."""
    if not suggestions:
        print("No new artists to follow based on your liked songs.")
        return
    
    print(f"\nFound {len(suggestions)} artists you might want to follow:")
    
    auto_follow_list = []
    manual_review_list = []
    
    # Categorize suggestions
    for suggestion in suggestions:
        song_count = suggestion['song_count']
        if song_count >= auto_threshold:
            auto_follow_list.append(suggestion)
        else:
            manual_review_list.append(suggestion)
    
    # Auto-follow artists with high song count
    if auto_follow_list:
        print(f"\nAuto-following {len(auto_follow_list)} artists (you liked {auto_threshold}+ songs from them):")
        
        for artist in auto_follow_list:
            print(f"  ✓ {artist['name']} ({artist['song_count']} songs)")
        
        confirm_auto = input(f"\nProceed with auto-following these {len(auto_follow_list)} artists? (y/n): ")
        
        if confirm_auto.lower() == 'y':
            try:
                # Follow artists in batches
                artist_ids = [artist['id'] for artist in auto_follow_list]
                batch_size = BATCH_SIZES['spotify_artists']
                
                for i in range(0, len(artist_ids), batch_size):
                    batch = artist_ids[i:i + batch_size]
                    sp.user_follow_artists(batch)
                    # SafeSpotifyClient handles rate limiting automatically
                
                print(f"Successfully followed {len(auto_follow_list)} artists!")
                
                # Clear followed artists cache
                save_to_cache(None, "followed_artists_for_autofollow", force_expire=True)
                
            except Exception as e:
                print(f"Error following artists: {e}")
    
    # Present manual review list
    if manual_review_list:
        print(f"\nArtists to review manually ({len(manual_review_list)} artists with {auto_threshold-1} or fewer songs):")
        
        for i, artist in enumerate(manual_review_list[:10], 1):  # Show top 10
            print(f"{i:2d}. {artist['name']} ({artist['song_count']} songs)")
            if artist['genres']:
                print(f"     Genres: {', '.join(artist['genres'][:3])}")
            print(f"     Tracks: {', '.join([t['track_name'] for t in artist['tracks'][:3]])}")
        
        if len(manual_review_list) > 10:
            print(f"     ... and {len(manual_review_list) - 10} more")
        
        follow_manual = input(f"\nWould you like to manually select artists to follow? (y/n): ")
        
        if follow_manual.lower() == 'y':
            manual_follow_selection(sp, manual_review_list)

def manual_follow_selection(sp, artists):
    """Allow user to manually select artists to follow."""
    print("\nEnter the numbers of artists you want to follow (e.g., '1,3,5' or 'all' or 'none'):")
    
    choice = input("Your selection: ").strip().lower()
    
    if choice == 'none':
        print("No artists selected for following.")
        return
    elif choice == 'all':
        selected_artists = artists
    else:
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(',')]
            selected_artists = [artists[i] for i in indices if 0 <= i < len(artists)]
        except ValueError:
            print("Invalid selection. No artists followed.")
            return
    
    if selected_artists:
        print(f"\nFollowing {len(selected_artists)} selected artists...")
        
        try:
            artist_ids = [artist['id'] for artist in selected_artists]
            batch_size = BATCH_SIZES['spotify_artists']
            
            for i in range(0, len(artist_ids), batch_size):
                batch = artist_ids[i:i + batch_size]
                sp.user_follow_artists(batch)
                # SafeSpotifyClient handles rate limiting automatically
            
            print(f"Successfully followed {len(selected_artists)} artists!")
            
            # Clear followed artists cache
            save_to_cache(None, "followed_artists_for_autofollow", force_expire=True)
            
        except Exception as e:
            print(f"Error following artists: {e}")

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
    search_text = f"{track['name']} {' '.join(track['artists'])} {track['album']}".lower()
    
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
    print("Spotify Like Songs")
    print("=================")
    
    # Ask user about Christmas filtering
    print("\nOptions:")
    print("1. Add all songs from playlists (including Christmas songs)")
    print("2. Add all songs except Christmas songs")
    
    while True:
        choice = input("\nEnter your choice (1-2): ").strip()
        if choice in ['1', '2']:
            break
        print("Please enter 1 or 2")
    
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
    liked_tracks = like_tracks(sp, tracks, saved_tracks)
    
    # Auto-follow artists based on liked tracks
    if liked_tracks and len(liked_tracks) > 0:
        try:
            suggestions = suggest_artists_to_follow(sp, liked_tracks, min_songs=3)
            if suggestions:
                auto_follow_artists(sp, suggestions, auto_threshold=5)
        except Exception as e:
            print_error(f"Error analyzing artists for auto-follow: {e}")
            print_warning("This may be due to cache corruption. Try clearing caches with menu option 9.")
            print_info("The track liking operation completed successfully despite this error.")

if __name__ == "__main__":
    main()