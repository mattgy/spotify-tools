#!/usr/bin/env python3
"""
Spotify Skipped Songs Identifier

This script analyzes your listening history to identify songs you frequently skip.
It uses Spotify's Recently Played tracks API to detect patterns in your listening behavior.

Features:
- Analyze listening history to find skipped songs
- Calculate skip rates for tracks in your library
- Identify patterns in skipped songs (genre, artist, album)
- Suggest songs to remove from Liked Songs
- Export skip analysis to CSV for further review

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import time
import json
import csv
from collections import defaultdict, Counter
from datetime import datetime, timedelta
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
SCOPES = SPOTIFY_SCOPES['read_only']

# Skip detection thresholds
MINIMUM_PLAY_TIME = 30000  # 30 seconds in milliseconds
SKIP_THRESHOLD = 0.3  # Consider skipped if played less than 30% of track
MINIMUM_OCCURRENCES = 2  # Need at least 2 plays to consider skip rate (reduced for more data)

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        sp = create_spotify_client(SCOPES, "identify_skipped")
        
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

def get_recently_played_tracks(sp, limit=200):
    """Get recently played tracks from Spotify with enhanced data collection."""
    from spotify_utils import fetch_recently_played
    
    # Try to get more listening data by making multiple calls
    print_info("Fetching recently played tracks...")
    
    # Use the reusable function which handles multiple calls for more data
    all_tracks = fetch_recently_played(sp, limit=limit, show_progress=True, cache_key="recently_played_extended")
    
    if all_tracks:
        print_success(f"Found {len(all_tracks)} recently played tracks")
    else:
        print_warning("No recently played tracks found")
    
    return all_tracks

def get_liked_songs(sp):
    """Get all liked songs from the user's library."""
    from spotify_utils import fetch_user_saved_tracks
    
    # Fetch saved tracks using the reusable function
    saved_tracks = fetch_user_saved_tracks(sp, show_progress=True, cache_key="liked_songs_for_skip_analysis")
    
    # Convert to dictionary format for easier lookup
    liked_songs = {}
    for item in saved_tracks:
        if item['track'] and item['track']['id']:
            track_id = item['track']['id']
            liked_songs[track_id] = {
                'id': track_id,
                'name': item['track']['name'],
                'artists': [artist['name'] for artist in item['track']['artists']],
                'album': item['track']['album']['name'],
                'duration_ms': item['track']['duration_ms'],
                'popularity': item['track']['popularity'],
                'uri': item['track']['uri'],
                'added_at': item['added_at']
            }
    
    print_success(f"Found {len(liked_songs)} liked songs")
    return liked_songs

def analyze_listening_patterns(recently_played):
    """Analyze listening patterns to identify potentially skipped songs."""
    print_info("Analyzing listening patterns...")
    
    # Group plays by track
    track_plays = defaultdict(list)
    
    for track in recently_played:
        track_id = track['track']['id']
        played_at = datetime.fromisoformat(track['played_at'].replace('Z', '+00:00'))
        
        track_plays[track_id].append({
            'track': track['track'],
            'played_at': played_at
        })
    
    # Analyze each track's listening pattern
    skip_analysis = {}
    
    for track_id, plays in track_plays.items():
        if len(plays) < MINIMUM_OCCURRENCES:
            continue  # Not enough data
        
        track = plays[0]['track']
        duration_ms = track['duration_ms']
        
        # Analyze consecutive plays to detect skips
        play_sessions = []
        
        for i, play in enumerate(plays):
            played_at = play['played_at']
            
            # Look for the next different track to estimate listen duration
            next_different_track = None
            next_time = None
            
            # Check subsequent tracks in the recently played list
            for next_track in recently_played:
                next_track_time = datetime.fromisoformat(next_track['played_at'].replace('Z', '+00:00'))
                
                if (next_track_time > played_at and 
                    next_track['id'] != track_id):
                    next_different_track = next_track
                    next_time = next_track_time
                    break
            
            if next_time:
                listen_duration = (next_time - played_at).total_seconds() * 1000  # Convert to ms
                listen_duration = min(listen_duration, duration_ms)  # Cap at track duration
                
                play_sessions.append({
                    'played_at': played_at,
                    'estimated_listen_duration': listen_duration,
                    'track_duration': duration_ms,
                    'listen_percentage': listen_duration / duration_ms if duration_ms > 0 else 0
                })
        
        if play_sessions:
            # Calculate skip statistics
            total_plays = len(play_sessions)
            skipped_plays = sum(1 for session in play_sessions 
                              if session['listen_percentage'] < SKIP_THRESHOLD)
            
            skip_rate = skipped_plays / total_plays if total_plays > 0 else 0
            avg_listen_percentage = sum(session['listen_percentage'] for session in play_sessions) / total_plays
            
            skip_analysis[track_id] = {
                'track': track,
                'total_plays': total_plays,
                'skipped_plays': skipped_plays,
                'skip_rate': skip_rate,
                'avg_listen_percentage': avg_listen_percentage,
                'play_sessions': play_sessions
            }
    
    # Check if we have enough data for analysis
    if len(skip_analysis) < 5:  # Need at least 5 songs with sufficient plays for meaningful analysis
        print_warning(f"Only {len(skip_analysis)} songs have enough plays for analysis (need at least 5).")
        print_info("Try using the app more to generate more listening data, or check back later.")
        return None
    
    print_success(f"Analyzed {len(skip_analysis)} songs with sufficient play data")
    return skip_analysis

def identify_problematic_songs(skip_analysis, liked_songs):
    """Identify songs with high skip rates that are in the user's library."""
    print_info("Identifying problematic songs in your library...")
    
    problematic_songs = []
    
    for track_id, analysis in skip_analysis.items():
        # Only consider songs in the user's liked songs
        if track_id in liked_songs:
            skip_rate = analysis['skip_rate']
            total_plays = analysis['total_plays']
            
            # Consider problematic if skip rate > 60% and played at least 3 times
            if skip_rate > 0.6 and total_plays >= MINIMUM_OCCURRENCES:
                problematic_songs.append({
                    'track_id': track_id,
                    'track': analysis['track'],
                    'skip_rate': skip_rate,
                    'total_plays': total_plays,
                    'skipped_plays': analysis['skipped_plays'],
                    'avg_listen_percentage': analysis['avg_listen_percentage']
                })
    
    # Sort by skip rate (highest first)
    problematic_songs.sort(key=lambda x: x['skip_rate'], reverse=True)
    
    return problematic_songs

def analyze_skip_patterns(skip_analysis):
    """Analyze patterns in skipped songs (genres, artists, etc.)."""
    print_info("Analyzing skip patterns...")
    
    artist_skip_rates = defaultdict(list)
    album_skip_rates = defaultdict(list)
    
    for track_id, analysis in skip_analysis.items():
        track = analysis['track']
        skip_rate = analysis['skip_rate']
        total_plays = analysis['total_plays']
        
        if total_plays >= MINIMUM_OCCURRENCES:
            # Analyze by artist
            for artist in track['artists']:
                artist_skip_rates[artist].append(skip_rate)
            
            # Analyze by album
            album_skip_rates[track['album']].append(skip_rate)
    
    # Calculate average skip rates
    artist_averages = {}
    for artist, rates in artist_skip_rates.items():
        if len(rates) >= 2:  # Need at least 2 songs
            artist_averages[artist] = {
                'avg_skip_rate': sum(rates) / len(rates),
                'song_count': len(rates),
                'total_skip_rate': sum(rates)
            }
    
    album_averages = {}
    for album, rates in album_skip_rates.items():
        if len(rates) >= 2:  # Need at least 2 songs
            album_averages[album] = {
                'avg_skip_rate': sum(rates) / len(rates),
                'song_count': len(rates),
                'total_skip_rate': sum(rates)
            }
    
    return artist_averages, album_averages

def display_results(problematic_songs, artist_patterns, album_patterns):
    """Display the analysis results."""
    print_header("Skip Analysis Results")
    
    print(f"Found {len(problematic_songs)} problematic songs in your Liked Songs")
    
    if problematic_songs:
        print(f"\n{Fore.RED}Songs You Frequently Skip:")
        print(f"{'#':<3} {'Skip Rate':<10} {'Plays':<6} {'Artist - Song'}")
        print("-" * 70)
        
        for i, song in enumerate(problematic_songs[:20], 1):  # Show top 20
            track = song['track']
            skip_rate = song['skip_rate']
            total_plays = song['total_plays']
            skipped_plays = song['skipped_plays']
            
            print(f"{i:<3} {skip_rate*100:>6.1f}%   {skipped_plays:>2}/{total_plays:<2}  {' '.join(track['artists'])} - {track['name']}")
    
    # Show artist patterns
    if artist_patterns:
        print(f"\n{Fore.YELLOW}Artists You Tend to Skip:")
        artist_list = sorted(artist_patterns.items(), key=lambda x: x[1]['avg_skip_rate'], reverse=True)
        
        for artist, data in artist_list[:10]:  # Show top 10
            if data['avg_skip_rate'] > 0.5:  # Only show if >50% skip rate
                print(f"  {artist}: {data['avg_skip_rate']*100:.1f}% skip rate ({data['song_count']} songs)")
    
    # Show album patterns
    if album_patterns:
        print(f"\n{Fore.YELLOW}Albums You Tend to Skip:")
        album_list = sorted(album_patterns.items(), key=lambda x: x[1]['avg_skip_rate'], reverse=True)
        
        for album, data in album_list[:10]:  # Show top 10
            if data['avg_skip_rate'] > 0.5:  # Only show if >50% skip rate
                print(f"  {album}: {data['avg_skip_rate']*100:.1f}% skip rate ({data['song_count']} songs)")

def export_results(problematic_songs, artist_patterns, album_patterns):
    """Export results to CSV files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # Export problematic songs
        songs_file = f"skipped_songs_{timestamp}.csv"
        with open(songs_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Artist', 'Song', 'Album', 'Skip Rate', 'Total Plays', 'Skipped Plays', 'Avg Listen %'])
            
            for song in problematic_songs:
                track = song['track']
                writer.writerow([
                    ' & '.join(track['artists']),
                    track['name'],
                    track['album'],
                    f"{song['skip_rate']*100:.1f}%",
                    song['total_plays'],
                    song['skipped_plays'],
                    f"{song['avg_listen_percentage']*100:.1f}%"
                ])
        
        print_success(f"Exported {len(problematic_songs)} problematic songs to {songs_file}")
        
        # Export artist patterns
        if artist_patterns:
            artists_file = f"skipped_artists_{timestamp}.csv"
            with open(artists_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Artist', 'Avg Skip Rate', 'Song Count'])
                
                artist_list = sorted(artist_patterns.items(), key=lambda x: x[1]['avg_skip_rate'], reverse=True)
                for artist, data in artist_list:
                    writer.writerow([
                        artist,
                        f"{data['avg_skip_rate']*100:.1f}%",
                        data['song_count']
                    ])
            
            print_success(f"Exported artist patterns to {artists_file}")
        
        return songs_file
    
    except Exception as e:
        print_error(f"Error exporting results: {e}")
        return None

def suggest_removal_actions(sp, problematic_songs):
    """Suggest actions for removing problematic songs."""
    if not problematic_songs:
        return
    
    print_header("Removal Suggestions")
    
    high_skip_songs = [song for song in problematic_songs if song['skip_rate'] > 0.8]
    medium_skip_songs = [song for song in problematic_songs if 0.6 < song['skip_rate'] <= 0.8]
    
    if high_skip_songs:
        print(f"\n{Fore.RED}Recommend removing ({len(high_skip_songs)} songs with >80% skip rate):")
        for song in high_skip_songs[:10]:
            track = song['track']
            print(f"  • {' '.join(track['artists'])} - {track['name']} ({song['skip_rate']*100:.0f}% skipped)")
    
    if medium_skip_songs:
        print(f"\n{Fore.YELLOW}Consider reviewing ({len(medium_skip_songs)} songs with 60-80% skip rate):")
        for song in medium_skip_songs[:5]:
            track = song['track']
            print(f"  • {' '.join(track['artists'])} - {track['name']} ({song['skip_rate']*100:.0f}% skipped)")
    
    # Ask if user wants to remove high-skip songs
    if high_skip_songs:
        print_warning(f"\nWould you like to remove the {len(high_skip_songs)} songs with >80% skip rate from Liked Songs?")
        choice = input("This will help clean up your library (y/n): ").strip().lower()
        
        if choice == 'y':
            remove_songs_from_library(sp, high_skip_songs)

def remove_songs_from_library(sp, songs_to_remove):
    """Remove selected songs from the user's Liked Songs."""
    print_info(f"Removing {len(songs_to_remove)} frequently skipped songs from Liked Songs...")
    
    try:
        # Remove tracks in batches
        track_ids = [song['track_id'] for song in songs_to_remove]
        batch_size = BATCH_SIZES['spotify_tracks']
        
        progress = create_progress_bar(len(track_ids), "Removing tracks", "track")
        
        for i in range(0, len(track_ids), batch_size):
            batch = track_ids[i:i + batch_size]
            sp.current_user_saved_tracks_delete(batch)
            
            update_progress_bar(progress, min(i + batch_size, len(track_ids)))
            time.sleep(0.2)  # Rate limiting
        
        close_progress_bar(progress)
        print_success(f"Successfully removed {len(songs_to_remove)} frequently skipped songs!")
        
        # Clear cache so next run gets fresh data
        save_to_cache(None, "liked_songs_for_skip_analysis", force_expire=True)
        
    except Exception as e:
        print_error(f"Error removing tracks: {e}")

def main():
    """Main function to run the skipped songs identifier."""
    print_header("Spotify Skipped Songs Identifier")
    
    # Set up Spotify client
    sp = setup_spotify_client()
    if not sp:
        return
    
    # Get data
    recently_played = get_recently_played_tracks(sp, limit=50)
    if not recently_played:
        print_warning("No recently played tracks found. This feature requires listening history.")
        return
    
    liked_songs = get_liked_songs(sp)
    if not liked_songs:
        print_warning("No liked songs found.")
        return
    
    # Analyze listening patterns
    skip_analysis = analyze_listening_patterns(recently_played)
    
    if not skip_analysis:
        print_warning("Not enough listening data to analyze skip patterns.")
        return
    
    # Identify problematic songs
    problematic_songs = identify_problematic_songs(skip_analysis, liked_songs)
    artist_patterns, album_patterns = analyze_skip_patterns(skip_analysis)
    
    # Display results
    display_results(problematic_songs, artist_patterns, album_patterns)
    
    # Export results
    print_info("\nWould you like to export the analysis to CSV files? (y/n): ")
    export_choice = input().strip().lower()
    
    if export_choice == 'y':
        export_results(problematic_songs, artist_patterns, album_patterns)
    
    # Suggest removal actions
    suggest_removal_actions(sp, problematic_songs)

if __name__ == "__main__":
    main()