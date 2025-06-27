#!/usr/bin/env python3
"""
Script to find and follow artists similar to those you already follow on Spotify.

This script:
1. Authenticates with your Spotify account
2. Gets all artists you currently follow
3. Uses Last.fm API to find similar artists
4. Allows you to follow these similar artists on Spotify

Author: Matt Y
License: MIT
Version: 1.0.0

Requirements:
- Python 3.6+
- spotipy library (pip install spotipy)
- requests library (pip install requests)
"""

import os
import sys
import time
import json
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import random
import colorama
from colorama import Fore, Style
from pathlib import Path

# Initialize colorama for cross-platform color support
colorama.init(autoreset=True)

# Define constants
CACHE_EXPIRATION = 60 * 60 * 24 * 7  # 7 days in seconds
CONFIG_DIR = os.path.join(str(Path.home()), ".spotify-tools")
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, "credentials.json")

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from credentials_manager import get_spotify_credentials, get_lastfm_api_key
from cache_utils import save_to_cache, load_from_cache
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

# Spotify API scopes needed for this script
SPOTIFY_SCOPES = [
    "user-follow-read",
    "user-follow-modify",
    "user-top-read"  # Add this scope to access user's top artists
]

# Cache expiration (in seconds)
CACHE_EXPIRATION = 7 * 24 * 60 * 60  # 7 days

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
        
        # Set up authentication with a specific cache path
        cache_path = os.path.join(os.path.expanduser("~"), ".spotify-tools", "spotify_token_cache")
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=" ".join(SPOTIFY_SCOPES),
            open_browser=False,  # Don't open browser repeatedly
            cache_path=cache_path  # Use a specific cache path
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

def get_similar_artists(artist_name, artist_id, lastfm_api_key):
    """Get similar artists from Last.fm API."""
    # Try to load from cache
    cache_key = f"similar_artists_{artist_id}"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        return cached_data
    
    # Last.fm API endpoint
    url = "http://ws.audioscrobbler.com/2.0/"
    
    # Parameters
    params = {
        "method": "artist.getsimilar",
        "artist": artist_name,
        "api_key": lastfm_api_key,
        "format": "json",
        "limit": 10
    }
    
    try:
        # Make the request
        response = requests.get(url, params=params)
        data = response.json()
        
        # Extract similar artists
        similar_artists = []
        if "similarartists" in data and "artist" in data["similarartists"]:
            for artist in data["similarartists"]["artist"]:
                similar_artists.append({
                    "name": artist["name"],
                    "match": float(artist["match"]) * 100
                })
        
        # Save to cache
        save_to_cache(similar_artists, cache_key)
        
        return similar_artists
    
    except Exception as e:
        print_warning(f"Error getting similar artists for {artist_name}: {e}")
        return []

def search_artist_on_spotify(sp, artist_name):
    """Search for an artist on Spotify."""
    try:
        results = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
        
        if results["artists"]["items"]:
            return results["artists"]["items"][0]
        else:
            return None
    
    except Exception as e:
        print_warning(f"Error searching for artist {artist_name}: {e}")
        return None

def follow_artist(sp, artist_id):
    """Follow an artist on Spotify."""
    try:
        sp.user_follow_artists([artist_id])
        return True
    
    except Exception as e:
        print_error(f"Error following artist: {e}")
        return False

def main():
    print_header("Find Artists to Follow That You Probably Like")
    
    # Set up API clients
    print_info("Setting up Spotify client...")
    sp = setup_spotify_client()
    
    print_info("Setting up Last.fm client...")
    lastfm_api_key = get_lastfm_api_key()
    if not lastfm_api_key:
        print_error("Last.fm API key is required for this feature.")
        print_info("To get a Last.fm API key:")
        print("1. Go to https://www.last.fm/api/account/create")
        print("2. Fill out the form and submit")
        print("3. Copy the API key")
        
        # Prompt user to enter API key now
        print("\nWould you like to enter your Last.fm API key now? (y/n)")
        choice = input("> ").strip().lower()
        
        if choice == 'y':
            # Directly prompt for API key
            print("Please enter your Last.fm API key:")
            api_key = input("API Key: ").strip()
            
            if api_key:
                # Save the API key
                try:
                    # Create config directory if it doesn't exist
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                    
                    # Load existing credentials if available
                    credentials = {}
                    if os.path.exists(CREDENTIALS_FILE):
                        with open(CREDENTIALS_FILE, "r") as f:
                            credentials = json.load(f)
                    
                    # Update with new API key
                    credentials["LASTFM_API_KEY"] = api_key
                    
                    # Save updated credentials
                    with open(CREDENTIALS_FILE, "w") as f:
                        json.dump(credentials, f, indent=2)
                    
                    lastfm_api_key = api_key
                    print_success("Last.fm API key saved successfully!")
                except Exception as e:
                    print_error(f"Error saving Last.fm API key: {e}")
                    return
            else:
                print_warning("No API key entered. Exiting.")
                return
        else:
            return
    
    # Get artists the user follows
    followed_artists = get_followed_artists(sp)
    if not followed_artists:
        print_warning("You don't follow any artists on Spotify yet.")
        return
    
    # Get user's top artists to prioritize recommendations
    print_info("Fetching your top artists to improve recommendations...")
    top_artists = []
    try:
        # Get top artists for different time ranges
        for time_range in ["short_term", "medium_term"]:
            results = sp.current_user_top_artists(limit=20, time_range=time_range)
            top_artists.extend(results["items"])
    except Exception as e:
        print_warning(f"Could not fetch top artists: {e}")
        print_info("Continuing with random selection of followed artists...")
        # If we can't get top artists, just use random selection
        top_artists = []
    
    # Create a set of top artist IDs for quick lookup
    top_artist_ids = set()
    if top_artists:
        top_artist_ids = {artist["id"] for artist in top_artists}
    
    # Prioritize followed artists that are also in your top artists
    prioritized_artists = []
    for artist in followed_artists:
        if isinstance(artist, dict) and "id" in artist and artist["id"] in top_artist_ids:
            prioritized_artists.append(artist)
    
    # If we don't have enough prioritized artists, add some random ones
    if len(prioritized_artists) < 10:
        remaining_artists = []
        for artist in followed_artists:
            if isinstance(artist, dict) and "id" in artist and artist["id"] not in top_artist_ids:
                remaining_artists.append(artist)
        
        if remaining_artists:
            random_artists = random.sample(remaining_artists, min(10, len(remaining_artists)))
            prioritized_artists.extend(random_artists)
    
    # Limit to a reasonable sample size
    sample_size = min(15, len(prioritized_artists))
    sampled_artists = prioritized_artists[:sample_size]
    
    # Get similar artists
    print_info(f"\nFinding similar artists based on {sample_size} of your most relevant followed artists...")
    
    # Create progress bar
    progress_bar = create_progress_bar(total=sample_size, desc="Finding similar artists", unit="artist")
    
    all_similar_artists = []
    for artist in sampled_artists:
        artist_name = artist["name"]
        artist_id = artist["id"]
        
        # Get similar artists
        similar_artists = get_similar_artists(artist_name, artist_id, lastfm_api_key)
        
        # Add to list
        for similar_artist in similar_artists:
            similar_artist["source"] = artist_name
            # Add a boost if the source artist is in your top artists
            if artist_id in top_artist_ids:
                similar_artist["match"] = min(100, similar_artist["match"] * 1.2)  # 20% boost, max 100
            all_similar_artists.append(similar_artist)
        
        # Update progress bar
        update_progress_bar(progress_bar, 1)
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.2)
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    # Remove duplicates and sort by match score
    unique_similar_artists = {}
    for artist in all_similar_artists:
        name = artist["name"]
        if name not in unique_similar_artists or artist["match"] > unique_similar_artists[name]["match"]:
            unique_similar_artists[name] = artist
    
    # Convert back to list and sort
    similar_artists_list = list(unique_similar_artists.values())
    similar_artists_list.sort(key=lambda x: x["match"], reverse=True)
    
    # Get already followed artists
    followed_artist_names = {artist["name"].lower() for artist in followed_artists}
    
    # Filter out already followed artists
    new_similar_artists = [
        artist for artist in similar_artists_list
        if artist["name"].lower() not in followed_artist_names
    ]
    
    if not new_similar_artists:
        print_warning("\nNo new similar artists found that you don't already follow.")
        return
    
    # Filter for high-quality recommendations
    # First, get a threshold that will give us a reasonable number of recommendations
    match_thresholds = [90, 85, 80, 75, 70]
    selected_threshold = 70
    
    for threshold in match_thresholds:
        high_quality_artists = [artist for artist in new_similar_artists if artist["match"] >= threshold]
        if len(high_quality_artists) >= 10:
            selected_threshold = threshold
            new_similar_artists = high_quality_artists
            break
    
    # Further filter by popularity if we still have too many
    if len(new_similar_artists) > 20:
        # Get popularity data for each artist
        print_info("Getting popularity data for recommendations...")
        progress_bar = create_progress_bar(total=len(new_similar_artists), desc="Checking artists", unit="artist")
        
        for artist in new_similar_artists:
            spotify_artist = search_artist_on_spotify(sp, artist["name"])
            if spotify_artist:
                artist["popularity"] = spotify_artist["popularity"]
                artist["id"] = spotify_artist["id"]
            else:
                artist["popularity"] = 0
                artist["id"] = None
            
            update_progress_bar(progress_bar, 1)
            time.sleep(0.1)  # Avoid rate limits
        
        close_progress_bar(progress_bar)
        
        # Filter out artists with low popularity
        popularity_threshold = 40
        popular_artists = [artist for artist in new_similar_artists if artist["popularity"] >= popularity_threshold]
        
        if len(popular_artists) >= 10:
            new_similar_artists = popular_artists
    
    # Sort by match score
    new_similar_artists.sort(key=lambda x: x["match"], reverse=True)
    
    if not new_similar_artists:
        print_warning("\nNo high-quality similar artists found that you don't already follow.")
        return
    
    print_success(f"\nFound {len(new_similar_artists)} high-quality similar artists you don't follow yet.")
    print_info(f"Using match threshold: {selected_threshold}%")
    
    # Show top similar artists
    top_count = min(20, len(new_similar_artists))
    print_info(f"\nTop {top_count} similar artists:")
    
    for i, artist in enumerate(new_similar_artists[:top_count], 1):
        print(f"{i}. {artist['name']} (Match: {artist['match']:.1f}%, Similar to: {artist['source']})")
    
    # Ask if user wants to follow these artists
    follow_option = input("\nWould you like to follow some of these artists? (y/n): ").strip().lower()
    
    if follow_option == "y":
        # Ask which artists to follow
        follow_input = input("\nEnter the numbers of the artists to follow (comma-separated, or 'all'): ").strip().lower()
        
        artists_to_follow = []
        if follow_input == "all":
            artists_to_follow = new_similar_artists[:top_count]
        else:
            try:
                indices = [int(idx.strip()) - 1 for idx in follow_input.split(",")]
                for idx in indices:
                    if 0 <= idx < top_count:
                        artists_to_follow.append(new_similar_artists[idx])
            except ValueError:
                print_error("Invalid input. Please enter numbers separated by commas.")
                return
        
        if not artists_to_follow:
            print_warning("No artists selected to follow.")
            return
        
        # Follow selected artists
        print_info(f"\nFollowing {len(artists_to_follow)} artists...")
        
        # Create progress bar
        progress_bar = create_progress_bar(total=len(artists_to_follow), desc="Following artists", unit="artist")
        
        followed_count = 0
        for artist_info in artists_to_follow:
            artist_name = artist_info["name"]
            
            # Search for artist on Spotify
            spotify_artist = search_artist_on_spotify(sp, artist_name)
            
            if spotify_artist:
                # Follow artist
                if follow_artist(sp, spotify_artist["id"]):
                    followed_count += 1
            
            # Update progress bar
            update_progress_bar(progress_bar, 1)
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.2)
        
        # Close progress bar
        close_progress_bar(progress_bar)
        
        print_success(f"\nSuccessfully followed {followed_count} new artists.")
        
        # Clear the followed artists cache
        save_to_cache(None, "followed_artists", force_expire=True)

if __name__ == "__main__":
    main()
