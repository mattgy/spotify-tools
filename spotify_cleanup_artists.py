#!/usr/bin/env python3
"""
Script to clean up followed artists on Spotify.

This script:
1. Authenticates with your Spotify account
2. Gets all artists you currently follow
3. Analyzes your listening history to identify artists you rarely listen to
4. Allows you to unfollow these artists

Requirements:
- Python 3.6+
- spotipy library (pip install spotipy)
"""

import os
import sys
import time
import json
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import random
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
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

# Spotify API scopes needed for this script
SPOTIFY_SCOPES = [
    "user-follow-read",
    "user-follow-modify",
    "user-top-read",
    "user-read-recently-played"
]

# Cache expiration (in seconds)
CACHE_EXPIRATION = 24 * 60 * 60  # 24 hours

def print_header(text):
    """Print a formatted header."""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}" + "="*50)
    print(f"{Fore.CYAN}{Style.BRIGHT}{text}")
    print(f"{Fore.CYAN}{Style.BRIGHT}" + "="*50)

def print_success(text):
    """Print a success message."""
    print(f"{Fore.GREEN}{text}")

def print_error(text):
    """Print an error message."""
    print(f"{Fore.RED}{text}")

def print_warning(text):
    """Print a warning message."""
    print(f"{Fore.YELLOW}{text}")

def print_info(text):
    """Print an info message."""
    print(f"{Fore.BLUE}{text}")

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        # Get credentials from credentials manager
        client_id, client_secret, redirect_uri = get_spotify_credentials()
        
        # Set up authentication
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=" ".join(SPOTIFY_SCOPES)
        )
        
        # Create Spotify client
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        # Test the connection
        sp.current_user()
        
        return sp
    
    except Exception as e:
        print_error(f"Error setting up Spotify client: {e}")
        print_info("\nTo set up a Spotify Developer account and create an app:")
        print("1. Go to https://developer.spotify.com/dashboard/")
        print("2. Log in and create a new app")
        print("3. Set the redirect URI to http://localhost:8888/callback")
        print("4. Copy the Client ID and Client Secret")
        sys.exit(1)

def get_followed_artists(sp):
    """Get all artists the user follows on Spotify."""
    # Try to load from cache
    cache_key = "followed_artists"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        print_success(f"Found {len(cached_data)} artists that you follow (from cache)")
        return cached_data
    
    artists = []
    after = None
    limit = 50
    
    print_info("Fetching artists you follow on Spotify...")
    
    # First, get the total count
    results = sp.current_user_followed_artists(limit=1)
    total_artists = results['artists']['total']
    
    # Create progress bar
    progress_bar = create_progress_bar(total=total_artists, desc="Fetching artists", unit="artist")
    
    while True:
        results = sp.current_user_followed_artists(limit=limit, after=after)
        batch_size = len(results['artists']['items'])
        
        artists.extend(results['artists']['items'])
        
        # Update progress bar
        update_progress_bar(progress_bar, batch_size)
        
        # Check if there are more artists to fetch
        if results['artists']['next']:
            after = results['artists']['cursors']['after']
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.1)
        else:
            break
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    print_success(f"Found {len(artists)} artists that you follow")
    
    # Save to cache
    save_to_cache(artists, cache_key)
    
    return artists

def get_top_artists(sp):
    """Get user's top artists from Spotify."""
    # Try to load from cache
    cache_key = "top_artists"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        return cached_data
    
    print_info("Fetching your top artists...")
    
    # Get top artists for different time ranges
    time_ranges = ["short_term", "medium_term", "long_term"]
    top_artists = {}
    
    # Create progress bar
    progress_bar = create_progress_bar(total=len(time_ranges), desc="Fetching top artists", unit="range")
    
    for time_range in time_ranges:
        try:
            results = sp.current_user_top_artists(limit=50, time_range=time_range)
            top_artists[time_range] = results["items"]
            
            # Update progress bar
            update_progress_bar(progress_bar, 1)
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.2)
        except Exception as e:
            print_warning(f"Error getting top artists for {time_range}: {e}")
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    # Save to cache
    save_to_cache(top_artists, cache_key)
    
    return top_artists

def get_recently_played(sp):
    """Get user's recently played tracks from Spotify."""
    # Try to load from cache
    cache_key = "recently_played"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        return cached_data
    
    print_info("Fetching your recently played tracks...")
    
    try:
        results = sp.current_user_recently_played(limit=50)
        tracks = results["items"]
        
        # Save to cache
        save_to_cache(tracks, cache_key)
        
        return tracks
    except Exception as e:
        print_warning(f"Error getting recently played tracks: {e}")
        return []

def identify_inactive_artists(followed_artists, top_artists, recently_played):
    """Identify artists that the user rarely listens to."""
    print_info("Analyzing your listening habits...")
    
    # Create a set of active artist IDs
    active_artist_ids = set()
    
    # Add top artists
    for time_range, artists in top_artists.items():
        for artist in artists:
            active_artist_ids.add(artist["id"])
    
    # Add artists from recently played tracks
    for item in recently_played:
        for artist in item["track"]["artists"]:
            active_artist_ids.add(artist["id"])
    
    # Identify inactive artists
    inactive_artists = []
    for artist in followed_artists:
        if artist["id"] not in active_artist_ids:
            # Calculate a "relevance score" based on popularity and follower count
            popularity = artist["popularity"]
            followers = artist["followers"]["total"]
            
            # Normalize followers (log scale)
            normalized_followers = min(1.0, max(0.0, (followers / 1000000)))
            
            # Calculate score (higher is more relevant)
            relevance_score = (popularity * 0.7) + (normalized_followers * 30)
            
            inactive_artists.append({
                "id": artist["id"],
                "name": artist["name"],
                "popularity": popularity,
                "followers": followers,
                "relevance_score": relevance_score
            })
    
    # Sort by relevance score (ascending, so least relevant first)
    inactive_artists.sort(key=lambda x: x["relevance_score"])
    
    return inactive_artists

def unfollow_artist(sp, artist_id):
    """Unfollow an artist on Spotify."""
    try:
        sp.user_unfollow_artists([artist_id])
        return True
    except Exception as e:
        print_error(f"Error unfollowing artist: {e}")
        return False

def main():
    print_header("Remove Followed Artists That You Probably Don't Like")
    
    # Set up API client
    print_info("Setting up Spotify client...")
    sp = setup_spotify_client()
    
    # Get artists the user follows
    followed_artists = get_followed_artists(sp)
    if not followed_artists:
        print_warning("You don't follow any artists on Spotify yet.")
        return
    
    # Get user's top artists
    top_artists = get_top_artists(sp)
    
    # Get recently played tracks
    recently_played = get_recently_played(sp)
    
    # Identify inactive artists
    inactive_artists = identify_inactive_artists(followed_artists, top_artists, recently_played)
    
    if not inactive_artists:
        print_success("\nYou seem to be actively listening to all the artists you follow!")
        return
    
    print_success(f"\nFound {len(inactive_artists)} artists you follow but rarely listen to.")
    
    # Show top inactive artists
    top_count = min(20, len(inactive_artists))
    print_info(f"\nTop {top_count} candidates for unfollowing:")
    
    for i, artist in enumerate(inactive_artists[:top_count], 1):
        print(f"{i}. {artist['name']} (Popularity: {artist['popularity']}/100, Followers: {artist['followers']:,})")
    
    # Ask if user wants to unfollow these artists
    unfollow_option = input("\nWould you like to unfollow some of these artists? (y/n): ").strip().lower()
    
    if unfollow_option == "y":
        # Ask which artists to unfollow
        unfollow_input = input("\nEnter the numbers of the artists to unfollow (comma-separated, or 'all'): ").strip().lower()
        
        artists_to_unfollow = []
        if unfollow_input == "all":
            artists_to_unfollow = inactive_artists[:top_count]
        else:
            try:
                indices = [int(idx.strip()) - 1 for idx in unfollow_input.split(",")]
                for idx in indices:
                    if 0 <= idx < top_count:
                        artists_to_unfollow.append(inactive_artists[idx])
            except ValueError:
                print_error("Invalid input. Please enter numbers separated by commas.")
                return
        
        if not artists_to_unfollow:
            print_warning("No artists selected to unfollow.")
            return
        
        # Unfollow selected artists
        print_info(f"\nUnfollowing {len(artists_to_unfollow)} artists...")
        
        # Create progress bar
        progress_bar = create_progress_bar(total=len(artists_to_unfollow), desc="Unfollowing artists", unit="artist")
        
        unfollowed_count = 0
        for artist_info in artists_to_unfollow:
            # Unfollow artist
            if unfollow_artist(sp, artist_info["id"]):
                unfollowed_count += 1
            
            # Update progress bar
            update_progress_bar(progress_bar, 1)
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.2)
        
        # Close progress bar
        close_progress_bar(progress_bar)
        
        print_success(f"\nSuccessfully unfollowed {unfollowed_count} artists.")
        
        # Clear the followed artists cache
        save_to_cache(None, "followed_artists", force_expire=True)

if __name__ == "__main__":
    main()
