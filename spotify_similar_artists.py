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
from spotify_utils import create_spotify_client, print_success, print_error, print_info
from credentials_manager import get_lastfm_api_key
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

# Import print functions from spotify_utils
from spotify_utils import print_header, print_warning, print_success, print_error, print_info

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        return create_spotify_client(SPOTIFY_SCOPES, "similar_artists")
    except Exception as e:
        print_error(f"Error setting up Spotify client: {e}")
        print_info("\nTo set up a Spotify Developer account and create an app:")
        print("1. Go to https://developer.spotify.com/dashboard/")
        print("2. Log in and create a new app")
        print("3. Set the redirect URI to http://127.0.0.1:8888/callback")
        print("4. Copy the Client ID and Client Secret")
        sys.exit(1)

def get_followed_artists(sp):
    """Get all artists the user follows on Spotify."""
    from spotify_utils import fetch_followed_artists
    from constants import CACHE_EXPIRATION
    return fetch_followed_artists(sp, show_progress=True, cache_key="followed_artists", cache_expiration=CACHE_EXPIRATION['long'])

def get_similar_artists(artist_name, artist_id, lastfm_api_key):
    """Get similar artists from Last.fm API with enhanced scoring."""
    # Try to load from cache
    cache_key = f"similar_artists_{artist_id}"
    cached_data = load_from_cache(cache_key, CACHE_EXPIRATION)
    
    if cached_data:
        return cached_data
    
    # Last.fm API endpoint
    url = "http://ws.audioscrobbler.com/2.0/"
    
    # Parameters - increased limit for better diversity
    params = {
        "method": "artist.getsimilar",
        "artist": artist_name,
        "api_key": lastfm_api_key,
        "format": "json",
        "limit": 20  # Increased from 10 for better selection
    }
    
    try:
        # Make the request
        response = requests.get(url, params=params)
        data = response.json()
        
        # Extract similar artists with enhanced metadata
        similar_artists = []
        if "similarartists" in data and "artist" in data["similarartists"]:
            for artist in data["similarartists"]["artist"]:
                # Calculate adjusted match score based on position
                base_match = float(artist["match"]) * 100
                
                similar_artists.append({
                    "name": artist["name"],
                    "match": base_match,
                    "lastfm_url": artist.get("url", ""),
                    "listeners": int(artist.get("streamable", "0")) if artist.get("streamable", "0").isdigit() else 0
                })
        
        # Save to cache
        save_to_cache(similar_artists, cache_key)
        
        return similar_artists
    
    except Exception as e:
        print_warning(f"Error getting similar artists for {artist_name}: {e}")
        return []

def search_artist_on_spotify(sp, artist_name):
    """Search for an artist on Spotify with enhanced matching."""
    try:
        # Try exact artist search first
        results = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
        
        if results["artists"]["items"]:
            return results["artists"]["items"][0]
        
        # If exact search fails, try broader search
        results = sp.search(q=artist_name, type="artist", limit=3)
        
        if results["artists"]["items"]:
            # Find the best match using simple string similarity
            best_match = None
            best_score = 0
            
            for artist in results["artists"]["items"]:
                # Simple similarity check (case-insensitive)
                query_lower = artist_name.lower()
                name_lower = artist["name"].lower()
                
                if query_lower == name_lower:
                    return artist  # Exact match
                elif query_lower in name_lower or name_lower in query_lower:
                    # Partial match - calculate basic similarity
                    similarity = len(set(query_lower.split()) & set(name_lower.split())) / max(len(query_lower.split()), len(name_lower.split()))
                    if similarity > best_score:
                        best_score = similarity
                        best_match = artist
            
            if best_match and best_score > 0.5:  # At least 50% similarity
                return best_match
        
        return None
    
    except Exception as e:
        print_warning(f"Error searching for artist {artist_name}: {e}")
        return None

def analyze_genre_diversity(artists_list, followed_artists):
    """Analyze genre diversity and suggest adjustments."""
    # Get genres from followed artists
    followed_genres = []
    for artist in followed_artists:
        if isinstance(artist, dict) and "genres" in artist:
            followed_genres.extend(artist["genres"])
    
    # Count genre frequency in followed artists
    from collections import Counter
    followed_genre_counts = Counter(followed_genres)
    
    # Analyze genres in recommendations
    recommendation_genres = []
    for artist in artists_list:
        if artist.get("genres"):
            recommendation_genres.extend(artist["genres"])
    
    recommendation_genre_counts = Counter(recommendation_genres)
    
    # Calculate diversity score
    total_genres = len(set(followed_genres + recommendation_genres))
    unique_new_genres = len(set(recommendation_genres) - set(followed_genres))
    
    diversity_score = unique_new_genres / max(1, total_genres) * 100
    
    return {
        "diversity_score": diversity_score,
        "new_genres": unique_new_genres,
        "total_genres": total_genres,
        "top_recommended_genres": recommendation_genre_counts.most_common(5),
        "underrepresented_genres": [genre for genre, count in followed_genre_counts.items() if count == 1]
    }

def follow_artist(sp, artist_id):
    """Follow an artist on Spotify."""
    try:
        sp.user_follow_artists([artist_id])
        return True
    
    except Exception as e:
        print_error(f"Error following artist: {e}")
        return False

def display_artists_paginated(artists_list, page_size=25):
    """Display artists with pagination support."""
    total_artists = len(artists_list)
    total_pages = (total_artists + page_size - 1) // page_size
    current_page = 1
    
    while True:
        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_artists)
        page_artists = artists_list[start_idx:end_idx]
        
        print_info(f"\n📄 Page {current_page} of {total_pages} (Artists {start_idx + 1}-{end_idx} of {total_artists})")
        print_info("─" * 60)
        
        for i, artist in enumerate(page_artists, start_idx + 1):
            # Enhanced display with more context
            match_score = artist['match']
            source = artist['source']
            
            # Add quality indicators
            quality_indicators = []
            if artist.get('popularity', 0) >= 60:
                quality_indicators.append("🔥 Popular")
            elif artist.get('popularity', 0) >= 40:
                quality_indicators.append("⭐ Rising")
            
            if artist.get('boost_applied', 1.0) > 1.2:
                quality_indicators.append("💎 High Relevance")
            
            if artist.get('genres'):
                main_genre = artist['genres'][0] if artist['genres'] else "Unknown"
                quality_indicators.append(f"🎵 {main_genre.title()}")
            
            quality_str = " ".join(quality_indicators[:2])  # Limit to 2 indicators for readability
            
            print(f"{i:3d}. {artist['name']} (Match: {match_score:.1f}% ← {source})")
            if quality_str:
                print(f"     {quality_str}")
        
        # Navigation options
        print(f"\n📊 Navigation:")
        nav_options = []
        if current_page > 1:
            nav_options.append("'p' for previous page")
        if current_page < total_pages:
            nav_options.append("'n' for next page")
        nav_options.extend(["'f' to follow artists", "'q' to quit pagination"])
        
        print(f"Options: {', '.join(nav_options)}")
        
        choice = input("\nEnter your choice: ").strip().lower()
        
        if choice == 'n' and current_page < total_pages:
            current_page += 1
        elif choice == 'p' and current_page > 1:
            current_page -= 1
        elif choice == 'f':
            return 'follow', start_idx, end_idx
        elif choice == 'q':
            return 'quit', None, None
        else:
            print_warning("Invalid choice. Please try again.")

def main():
    print_header("Find Artists to Follow That You Probably Like")
    
    # Get user preferences
    print_info("\n🎛️ Discovery Preferences:")
    
    # Ask for maximum recommendations
    max_recs_input = input("Maximum recommendations to find (default: 50, max: 200): ").strip()
    try:
        max_recommendations = int(max_recs_input) if max_recs_input else 50
        max_recommendations = min(max(max_recommendations, 10), 200)  # Clamp between 10-200
    except ValueError:
        max_recommendations = 50
        print_info("Using default: 50 recommendations")
    
    # Ask for page size
    page_size_input = input("Artists per page (default: 25): ").strip()
    try:
        page_size = int(page_size_input) if page_size_input else 25
        page_size = min(max(page_size, 5), 50)  # Clamp between 5-50
    except ValueError:
        page_size = 25
        print_info("Using default: 25 per page")
    
    # Ask for discovery breadth
    breadth_input = input("Discovery breadth - more source artists (1=focused, 2=balanced, 3=wide): ").strip()
    try:
        discovery_breadth = int(breadth_input) if breadth_input else 2
        discovery_breadth = min(max(discovery_breadth, 1), 3)
    except ValueError:
        discovery_breadth = 2
    
    # Calculate sample size based on breadth
    breadth_multipliers = {1: 15, 2: 25, 3: 40}  # Number of source artists to analyze
    sample_size = breadth_multipliers[discovery_breadth]
    
    print_success(f"\n🎯 Configuration: {max_recommendations} recommendations, {page_size} per page, {sample_size} source artists")
    
    # Set up API clients
    print_info("\nSetting up Spotify client...")
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
    
    # Get user's top artists and recent listening history for better recommendations
    print_info("Fetching your listening patterns to improve recommendations...")
    top_artists = []
    listening_frequency = {}
    
    try:
        # Get top artists for all time ranges with weights
        time_ranges = {
            "short_term": 3.0,    # Recent listening gets highest weight
            "medium_term": 2.0,   # Medium-term gets good weight
            "long_term": 1.0      # Long-term gets base weight
        }
        
        for time_range, weight in time_ranges.items():
            results = sp.current_user_top_artists(limit=30, time_range=time_range)
            for i, artist in enumerate(results["items"]):
                # Higher weight for higher positions and recent listening
                position_weight = (30 - i) / 30  # Position 1 = 1.0, position 30 = 0.03
                total_weight = weight * position_weight
                
                if artist["id"] in listening_frequency:
                    listening_frequency[artist["id"]] += total_weight
                else:
                    listening_frequency[artist["id"]] = total_weight
                    
            top_artists.extend(results["items"])
            
    except Exception as e:
        print_warning(f"Could not fetch top artists: {e}")
        print_info("Continuing with followed artists only...")
        top_artists = []
    
    # Create weighted selection of artists based on listening frequency
    top_artist_ids = set()
    if top_artists:
        top_artist_ids = {artist["id"] for artist in top_artists}
    
    # Prioritize followed artists with intelligent weighting
    artist_weights = []
    for artist in followed_artists:
        if isinstance(artist, dict) and "id" in artist:
            # Base weight
            weight = 1.0
            
            # Boost weight based on listening frequency
            if artist["id"] in listening_frequency:
                weight += listening_frequency[artist["id"]] * 2  # Double the listening weight
            
            # Additional boost for top artists
            if artist["id"] in top_artist_ids:
                weight += 1.5
            
            artist_weights.append((artist, weight))
    
    # Sort by weight and select top artists for analysis
    artist_weights.sort(key=lambda x: x[1], reverse=True)
    
    # Use weighted selection based on user preference
    actual_sample_size = min(sample_size, len(artist_weights))
    sampled_artists = [artist for artist, weight in artist_weights[:actual_sample_size]]
    
    # Get similar artists
    print_info(f"\nFinding similar artists based on {actual_sample_size} of your most relevant followed artists...")
    
    # Create progress bar
    progress_bar = create_progress_bar(total=actual_sample_size, desc="Finding similar artists", unit="artist")
    
    all_similar_artists = []
    for artist in sampled_artists:
        artist_name = artist["name"]
        artist_id = artist["id"]
        
        # Get similar artists
        similar_artists = get_similar_artists(artist_name, artist_id, lastfm_api_key)
        
        # Add to list with enhanced scoring
        for similar_artist in similar_artists:
            similar_artist["source"] = artist_name
            
            # Calculate comprehensive boost based on multiple factors
            boost_multiplier = 1.0
            
            # Boost based on source artist listening frequency
            if artist_id in listening_frequency:
                frequency_boost = min(0.5, listening_frequency[artist_id] * 0.1)  # Up to 50% boost
                boost_multiplier += frequency_boost
            
            # Additional boost for top artists
            if artist_id in top_artist_ids:
                boost_multiplier += 0.3  # 30% boost for top artists
            
            # Apply boost while maintaining reasonable limits
            similar_artist["match"] = min(100, similar_artist["match"] * boost_multiplier)
            similar_artist["boost_applied"] = boost_multiplier
            
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
    
    # Enhanced filtering with multiple quality metrics
    print_info("Applying quality filters and diversity checks...")
    
    # First pass: Match score filtering with adaptive thresholds based on target count
    target_count = min(max_recommendations * 2, len(new_similar_artists))  # Aim for 2x target for good filtering
    match_thresholds = [92, 88, 85, 82, 78, 75, 70, 65, 60]
    selected_threshold = 60
    
    for threshold in match_thresholds:
        high_quality_artists = [artist for artist in new_similar_artists if artist["match"] >= threshold]
        if len(high_quality_artists) >= target_count:
            selected_threshold = threshold
            new_similar_artists = high_quality_artists
            break
    
    # Second pass: Diversity enhancement
    # Group by source artist to ensure diversity
    source_groups = {}
    for artist in new_similar_artists:
        source = artist["source"]
        if source not in source_groups:
            source_groups[source] = []
        source_groups[source].append(artist)
    
    # Limit recommendations per source artist to improve diversity (scale with user's max)
    base_per_source = max(2, max_recommendations // len(source_groups)) if source_groups else 5
    max_per_source = min(base_per_source, 8)  # Cap at 8 per source to maintain diversity
    diversified_artists = []
    
    for source, artists in source_groups.items():
        # Sort by match score and take top ones from each source
        artists.sort(key=lambda x: x["match"], reverse=True)
        diversified_artists.extend(artists[:max_per_source])
    
    new_similar_artists = diversified_artists
    
    # Enhanced popularity and genre analysis
    if len(new_similar_artists) > max_recommendations:
        print_info("Analyzing artist popularity and genres for final selection...")
        progress_bar = create_progress_bar(total=len(new_similar_artists), desc="Analyzing artists", unit="artist")
        
        # Get detailed Spotify data for each artist
        for artist in new_similar_artists:
            spotify_artist = search_artist_on_spotify(sp, artist["name"])
            if spotify_artist:
                artist["popularity"] = spotify_artist["popularity"]
                artist["id"] = spotify_artist["id"]
                artist["genres"] = spotify_artist.get("genres", [])
                artist["followers"] = spotify_artist["followers"]["total"]
            else:
                artist["popularity"] = 0
                artist["id"] = None
                artist["genres"] = []
                artist["followers"] = 0
            
            update_progress_bar(progress_bar, 1)
            time.sleep(0.1)  # Avoid rate limits
        
        close_progress_bar(progress_bar)
        
        # Multi-factor filtering based on user's target
        # 1. Remove very unpopular artists (but not too strictly to allow discovery)
        min_popularity = 25  # Lower threshold to allow emerging artists
        popularity_filtered = [artist for artist in new_similar_artists if artist["popularity"] >= min_popularity]
        
        # 2. If still too many, apply progressive filtering
        if len(popularity_filtered) > max_recommendations:
            # Try follower count threshold
            min_followers = 1000
            follower_filtered = [artist for artist in popularity_filtered if artist["followers"] >= min_followers]
            
            if len(follower_filtered) >= max_recommendations // 2:
                new_similar_artists = follower_filtered[:max_recommendations]
            else:
                new_similar_artists = popularity_filtered[:max_recommendations]
        else:
            new_similar_artists = popularity_filtered
    
    # Sort by match score
    new_similar_artists.sort(key=lambda x: x["match"], reverse=True)
    
    if not new_similar_artists:
        print_warning("\nNo high-quality similar artists found that you don't already follow.")
        return
    
    print_success(f"\n🎉 Found {len(new_similar_artists)} high-quality similar artists you don't follow yet!")
    print_info(f"📊 Match threshold used: {selected_threshold}%")
    print_info(f"🎯 Showing all {len(new_similar_artists)} recommendations with pagination")
    
    # Analyze genre diversity
    if len(new_similar_artists) > 5:
        print_info("\n📊 Genre Diversity Analysis:")
        diversity_analysis = analyze_genre_diversity(new_similar_artists, followed_artists)
        
        print(f"🎯 Diversity Score: {diversity_analysis['diversity_score']:.1f}%")
        print(f"🆕 New Genres Introduced: {diversity_analysis['new_genres']}")
        
        if diversity_analysis['top_recommended_genres']:
            print("🎵 Top Recommended Genres:")
            for genre, count in diversity_analysis['top_recommended_genres'][:3]:
                print(f"   • {genre.title()}: {count} artists")
        
        if diversity_analysis['underrepresented_genres'] and len(diversity_analysis['underrepresented_genres']) > 0:
            underrep_sample = diversity_analysis['underrepresented_genres'][:3]
            print(f"💡 Tip: You have few artists in: {', '.join(g.title() for g in underrep_sample)}")
    
    # Display artists with pagination
    action, start_idx, end_idx = display_artists_paginated(new_similar_artists, page_size)
    
    if action == 'quit':
        print_info("Exiting discovery mode.")
        return
    
    # Follow artists functionality
    follow_option = 'y'
    
    if follow_option == "y":
        # Ask which artists to follow with enhanced options
        print_info(f"\n🎯 Follow Options:")
        print(f"• 'all' - Follow all {len(new_similar_artists)} artists")
        print(f"• 'page' - Follow current page ({start_idx + 1}-{end_idx})")
        print(f"• 'top N' - Follow top N artists (e.g., 'top 10')")
        print(f"• Numbers - Specific artists (e.g., '1,3,5,12')")
        print(f"• 'range' - Artist range (e.g., '1-20')")
        
        follow_input = input("\nEnter your choice: ").strip().lower()
        
        artists_to_follow = []
        
        try:
            if follow_input == "all":
                artists_to_follow = new_similar_artists
            elif follow_input == "page":
                artists_to_follow = new_similar_artists[start_idx:end_idx]
            elif follow_input.startswith("top "):
                try:
                    top_n = int(follow_input.split()[1])
                    artists_to_follow = new_similar_artists[:min(top_n, len(new_similar_artists))]
                except (IndexError, ValueError):
                    print_error("Invalid 'top N' format. Use 'top 10' for example.")
                    return
            elif "-" in follow_input and follow_input.replace("-", "").replace(" ", "").isdigit():
                # Range format: "1-20"
                start_num, end_num = map(int, follow_input.split("-"))
                start_idx_range = max(0, start_num - 1)
                end_idx_range = min(len(new_similar_artists), end_num)
                artists_to_follow = new_similar_artists[start_idx_range:end_idx_range]
            else:
                # Comma-separated numbers
                indices = [int(idx.strip()) - 1 for idx in follow_input.split(",")]
                for idx in indices:
                    if 0 <= idx < len(new_similar_artists):
                        artists_to_follow.append(new_similar_artists[idx])
                    else:
                        print_warning(f"Index {idx + 1} is out of range (1-{len(new_similar_artists)})")
        except ValueError:
            print_error("Invalid input format. Please check the examples above.")
            return
        
        if not artists_to_follow:
            print_warning("No valid artists selected to follow.")
            return
        
        print_success(f"\n✅ Selected {len(artists_to_follow)} artists to follow")
        
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
        
        print_success(f"\n🎉 Successfully followed {followed_count} out of {len(artists_to_follow)} artists!")
        
        if followed_count < len(artists_to_follow):
            failed_count = len(artists_to_follow) - followed_count
            print_warning(f"⚠️ {failed_count} artists could not be followed (may not exist on Spotify)")
        
        # Clear the followed artists cache to reflect new follows
        save_to_cache(None, "followed_artists", force_expire=True)
        
        # Offer to discover more
        if followed_count > 0:
            more_discovery = input(f"\n🔄 Discover more artists based on your new follows? (y/n): ").strip().lower()
            if more_discovery == 'y':
                print_info("Restarting discovery with updated library...")
                main()  # Restart with updated followed artists

if __name__ == "__main__":
    main()
