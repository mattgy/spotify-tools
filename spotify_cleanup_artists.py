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
from spotify_utils import (create_spotify_client, safe_spotify_call,
                          print_success, print_error, print_warning, print_info, 
                          print_header, show_spotify_setup_help)
from constants import CACHE_EXPIRATION

# Spotify API scopes needed for this script
SPOTIFY_SCOPES = [
    "user-follow-read",
    "user-follow-modify", 
    "user-top-read",
    "user-read-recently-played"
]

# Use shared cache expiration for consistency
SCRIPT_CACHE_EXPIRATION = CACHE_EXPIRATION['long']  # 7 days

def display_artists_paginated(artists, title="Artists"):
    """Display artists with pagination support."""
    if not artists:
        print_warning("No artists to display.")
        return
    
    page_size = 20
    total_pages = (len(artists) + page_size - 1) // page_size
    current_page = 1
    
    while True:
        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, len(artists))
        page_artists = artists[start_idx:end_idx]
        
        print_header(f"{title} - Page {current_page}/{total_pages}")
        print(f"Showing {start_idx + 1}-{end_idx} of {len(artists)} artists")
        print(f"{Fore.CYAN}Score = Relevance based on popularity & followers | Pop = Spotify popularity | Followers = API count")
        print(f"{Fore.CYAN}⚠️ = Low followers but high popularity | Monthly listeners NOT available via API\n")
        
        for i, artist in enumerate(page_artists, start_idx + 1):
            # Enhanced display with better formatting and data explanations
            follower_display = f"{artist['followers']:,}" if artist['followers'] > 0 else "0"
            
            # Add warning indicators
            warning = ""
            
            # Check for warning (low followers, high popularity)
            if artist['followers'] < 100 and artist['popularity'] > 30:
                warning = f" {Fore.MAGENTA}⚠️"
            
            # Show simplified scoring information
            print(f"{i:3d}. {Fore.WHITE}{artist['name']:<40} " + 
                  f"{Fore.YELLOW}Pop: {artist['popularity']:2d}/100  " +
                  f"{Fore.GREEN}Followers: {follower_display:>10s}  " +
                  f"{Fore.CYAN}Score: {artist['relevance_score']:5.1f}{warning}")
        
        print(f"\n{Fore.WHITE}Navigation:")
        nav_options = []
        if current_page > 1:
            nav_options.append("p: Previous page")
        if current_page < total_pages:
            nav_options.append("n: Next page")
        nav_options.extend(["s: Show all", "q: Back to menu"])
        
        print(" | ".join(nav_options))
        
        choice = input(f"\n{Fore.CYAN}Enter choice: ").strip().lower()
        
        if choice == 'n' and current_page < total_pages:
            current_page += 1
        elif choice == 'p' and current_page > 1:
            current_page -= 1
        elif choice == 's':
            # Show all artists
            print_header(f"All {title}")
            for i, artist in enumerate(artists, 1):
                follower_display = f"{artist['followers']:,}" if artist['followers'] > 0 else "0"
                print(f"{i:3d}. {Fore.WHITE}{artist['name']:<40} " + 
                      f"{Fore.YELLOW}Pop: {artist['popularity']:2d}/100  " +
                      f"{Fore.GREEN}Followers: {follower_display:>10s}  " +
                      f"{Fore.CYAN}Score: {artist['relevance_score']:5.1f}")
            input(f"\n{Fore.CYAN}Press Enter to continue...")
            break
        elif choice == 'q':
            break
        else:
            print_warning("Invalid choice. Please try again.")

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        return create_spotify_client(SPOTIFY_SCOPES, "cleanup")
    except Exception as e:
        print_error(f"Error setting up Spotify client: {e}")
        show_spotify_setup_help()
        sys.exit(1)

def get_followed_artists(sp):
    """Get all artists the user follows on Spotify."""
    from spotify_utils import fetch_followed_artists
    return fetch_followed_artists(sp, show_progress=True, cache_key="followed_artists", cache_expiration=SCRIPT_CACHE_EXPIRATION)

def get_top_artists(sp):
    """Get user's top artists from Spotify."""
    # Try to load from cache
    cache_key = "top_artists"
    cached_data = load_from_cache(cache_key, SCRIPT_CACHE_EXPIRATION)
    
    if cached_data:
        total_cached = sum(len(artists) for artists in cached_data.values())
        print_success(f"Using cached top artists data ({total_cached} total entries)")
        return cached_data
    
    print_info("Fetching your top artists...")
    
    # Get top artists for different time ranges with higher limits
    time_ranges = ["short_term", "medium_term", "long_term"]
    top_artists = {}
    
    # Create progress bar
    progress_bar = create_progress_bar(total=len(time_ranges), desc="Fetching top artists", unit="range")
    
    for time_range in time_ranges:
        @safe_spotify_call
        def get_top_artists_for_range(time_range):
            return sp.current_user_top_artists(limit=50, time_range=time_range)
        
        try:
            # Increase limit to get more comprehensive data with rate limiting
            results = get_top_artists_for_range(time_range)
            if results:
                top_artists[time_range] = results["items"]
                print_info(f"  • {time_range}: {len(results['items'])} artists")
            else:
                top_artists[time_range] = []
            
            # Update progress bar
            update_progress_bar(progress_bar, 1)
            
        except Exception as e:
            print_warning(f"Error getting top artists for {time_range}: {e}")
            top_artists[time_range] = []
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    total_fetched = sum(len(artists) for artists in top_artists.values())
    print_success(f"Fetched {total_fetched} top artist entries across all time ranges")
    
    # Save to cache
    save_to_cache(top_artists, cache_key)
    
    return top_artists

def get_recently_played(sp):
    """Get user's recently played tracks from Spotify."""
    # Try to load from cache
    cache_key = "recently_played"
    cached_data = load_from_cache(cache_key, SCRIPT_CACHE_EXPIRATION)
    
    if cached_data:
        unique_artists = len(set(a["id"] for track in cached_data for a in track["track"]["artists"]))
        print_success(f"Using cached recently played data ({len(cached_data)} tracks, {unique_artists} unique artists)")
        return cached_data
    
    print_info("Fetching your recently played tracks...")
    
    @safe_spotify_call 
    def get_recent_tracks():
        return sp.current_user_recently_played(limit=50)
    
    try:
        results = get_recent_tracks()
        if results:
            tracks = results["items"]
            
            # Count unique artists
            unique_artists = len(set(a["id"] for track in tracks for a in track["track"]["artists"]))
            print_success(f"Fetched {len(tracks)} recently played tracks with {unique_artists} unique artists")
            
            # Save to cache
            save_to_cache(tracks, cache_key)
            
            return tracks
        else:
            print_warning("Could not fetch recently played tracks (rate limited or permission issue)")
            return []
    except Exception as e:
        print_warning(f"Error getting recently played tracks: {e}")
        return []

def identify_inactive_artists(followed_artists, top_artists, recently_played):
    """Identify artists that the user rarely listens to with simplified scoring."""
    print_info("Analyzing your listening habits...")
    
    # Check for cache corruption and auto-repair if needed
    corrupted_count = 0
    for artist in followed_artists:
        if isinstance(artist, str) or not isinstance(artist, dict) or 'id' not in artist:
            corrupted_count += 1
    
    if corrupted_count > 0:
        print_warning(f"Detected {corrupted_count} corrupted artist entries in cache. Auto-repairing...")
        # Clear the corrupted cache to force fresh fetch
        save_to_cache(None, "followed_artists", force_expire=True)
        print_info("Cache cleared. Please restart the script to fetch fresh artist data.")
        return []
    
    # Create a set of active artist IDs
    active_artist_ids = set()
    
    # Add top artists from all time ranges
    total_top_artists = 0
    for time_range, artists in top_artists.items():
        for artist in artists:
            active_artist_ids.add(artist["id"])
            total_top_artists += 1
    
    # Add artists from recently played tracks  
    recent_artist_count = 0
    for item in recently_played:
        for artist in item["track"]["artists"]:
            if artist["id"] not in active_artist_ids:
                recent_artist_count += 1
            active_artist_ids.add(artist["id"])
    
    print_info(f"Active artists found: {len(active_artist_ids)} total")
    print_info(f"  • From top artists: {total_top_artists} entries across time ranges")
    print_info(f"  • From recently played: {recent_artist_count} additional artists")
    print_info(f"  • Unique active artists: {len(active_artist_ids)}")
    
    # Identify inactive artists with simplified scoring
    inactive_artists = []
    for artist in followed_artists:
        # At this point all artists should be valid dicts due to corruption check above
            
        if artist["id"] not in active_artist_ids:
            # Calculate simplified relevance score
            popularity = artist["popularity"]
            followers = artist["followers"]["total"]
            
            import math
            
            # Simplified scoring: popularity is main factor, followers provide context
            if followers > 0:
                follower_score = min(100, max(0, math.log10(followers + 1) * 12))
            else:
                follower_score = 0
            
            # Weight popularity more heavily, use followers as secondary factor
            # Add protection for well-known artists that might have lower follower counts
            base_score = (popularity * 0.7) + (follower_score * 0.3)
            
            # Apply conservative adjustment for potentially well-known artists
            # Don't suggest removal of artists with high popularity even if followers are low
            if popularity >= 50:  # Popular artists should be protected
                relevance_score = max(base_score, 50)  # Minimum score of 50 for popular artists
            elif popularity >= 30 and followers < 1000:  # Possible discrepancy between popularity and followers
                relevance_score = max(base_score, 35)  # Be more conservative
            else:
                relevance_score = base_score
            
            # Create artist record with simplified scoring
            artist_record = {
                "id": artist["id"],
                "name": artist["name"],
                "popularity": popularity,
                "followers": followers,
                "genres": artist.get("genres", []),
                "follower_score": follower_score,
                "relevance_score": relevance_score,
                "final_score": relevance_score,
                "artist_importance_score": relevance_score  # For backward compatibility
            }
            
            inactive_artists.append(artist_record)
    
    # Sort by relevance score (ascending, so least relevant first)
    inactive_artists.sort(key=lambda x: x["relevance_score"])
    
    print_success(f"Found {len(inactive_artists)} inactive artists (artists you follow but don't appear in your recent listening).")
    print_info(f"Note: These artists may still be worth keeping if they're seasonal, reunion bands, or you just haven't listened recently.")
    
    return inactive_artists

def unfollow_artist(sp, artist_id):
    """Unfollow an artist on Spotify."""
    try:
        sp.user_unfollow_artists([artist_id])
        return True
    except Exception as e:
        print_error(f"Error unfollowing artist: {e}")
        return False

def bulk_unfollow_by_criteria(sp, followed_artists, top_artists, recently_played):
    """Bulk unfollow artists based on user-defined criteria."""
    print_header("Bulk Artist Cleanup Options")
    
    # Identify inactive artists
    inactive_artists = identify_inactive_artists(followed_artists, top_artists, recently_played)
    
    if not inactive_artists:
        # Check if this was due to cache corruption auto-repair
        if len(followed_artists) > 0 and all(isinstance(artist, str) or not isinstance(artist, dict) for artist in followed_artists[:5]):
            print_info("Cache corruption detected and repaired. Restarting analysis...")
            return  # Exit early to allow restart
        print_success("You seem to be actively listening to all the artists you follow!")
        return
    
    print_info(f"Found {len(inactive_artists)} artists you follow but rarely listen to.")
    
    # Add important data disclaimers
    print(f"\n{Fore.YELLOW}⚠️  IMPORTANT DATA LIMITATIONS:")
    print(f"{Fore.YELLOW}• 'Followers' = API follower count (NOT monthly listeners)")
    print(f"{Fore.YELLOW}• 'Popularity' = Spotify's 0-100 algorithmic score") 
    print(f"{Fore.YELLOW}• Monthly listeners are only visible in app, not via API")
    print(f"{Fore.YELLOW}• Popular artists may show low followers but have high external popularity")
    
    # Show filtering options
    print(f"\n{Fore.WHITE}Artist Cleanup Options:")
    print("1. Set relevance score threshold (recommended)")
    print("2. Show candidates for manual review (with pagination)")
    print("3. Unfollow by raw follower count")
    print("4. Unfollow by Spotify popularity score")
    print("5. Back to main menu")
    
    choice = input(f"\n{Fore.CYAN}Enter your choice (1-5): ")
    
    if choice == "1":
        # Relevance score threshold
        print_header("Relevance Score Threshold")
        print(f"{Fore.CYAN}This scores artists based on:")
        print(f"{Fore.CYAN}• Spotify popularity score (0-100)")
        print(f"{Fore.CYAN}• Follower count (scaled logarithmically)")
        print(f"\n{Fore.YELLOW}Relevance score ranges:")
        print(f"{Fore.YELLOW}• 70-100: High relevance (very popular artists)")
        print(f"{Fore.YELLOW}• 40-69:  Moderate relevance (moderately popular)")
        print(f"{Fore.YELLOW}• 20-39:  Low relevance (emerging/niche artists)")
        print(f"{Fore.YELLOW}• 0-19:   Very low relevance (very small/inactive artists)")
        
        try:
            threshold = float(input(f"\n{Fore.CYAN}Set minimum relevance score to keep artists (recommended: 25): ") or "25")
            
            # Filter artists below threshold
            candidates = [a for a in inactive_artists if a.get('relevance_score', 0) < threshold]
            
            if not candidates:
                print_warning(f"No inactive artists found with relevance score below {threshold:.1f}.")
                return
            
            print_info(f"Found {len(candidates)} artists with relevance score below {threshold:.1f}:")
            
            # Options for handling the candidates
            print(f"\n{Fore.CYAN}Options:")
            print(f"{Fore.WHITE}1. Browse all candidates with pagination")
            print(f"{Fore.WHITE}2. Unfollow all {len(candidates)} candidates immediately")
            print(f"{Fore.WHITE}3. Cancel and go back")
            
            action = input(f"\n{Fore.CYAN}Choose action (1-3): ").strip()
            
            if action == "1":
                # Browse with pagination
                display_artists_paginated(candidates, f"Artists with Relevance Score < {threshold:.1f}")
            elif action == "2":
                # Immediate unfollow
                confirm = input(f"\n{Fore.CYAN}Are you sure you want to unfollow {len(candidates)} artists? (y/n): ").strip().lower()
                if confirm == 'y':
                    bulk_unfollow_artists(sp, candidates)
            elif action == "3":
                return
                
        except ValueError:
            print_error("Invalid score entered. Please enter a number between 0 and 100.")
            
    elif choice == "2":
        # Show candidates for manual review
        manual_review_artists(sp, inactive_artists[:50])
        
    elif choice == "3":
        # Unfollow by raw follower count
        try:
            max_followers = int(input("Unfollow all artists with fewer than how many followers? (e.g., 100): "))
            candidates = [a for a in inactive_artists if a['followers'] < max_followers]
            
            if not candidates:
                print_warning(f"No artists found with fewer than {max_followers:,} followers.")
                return
            
            print_info(f"Found {len(candidates)} artists with fewer than {max_followers:,} followers:")
            display_artists_paginated(candidates, f"Low Follower Artists (< {max_followers:,})")
            
        except ValueError:
            print_error("Invalid number entered.")
            
    elif choice == "4":
        # Unfollow by Spotify popularity score
        try:
            max_popularity = int(input("Unfollow all artists with popularity less than? (0-100, e.g., 20): "))
            
            if not 0 <= max_popularity <= 100:
                print_error("Popularity must be between 0 and 100.")
                return
            
            candidates = [a for a in inactive_artists if a['popularity'] < max_popularity]
            
            if not candidates:
                print_warning(f"No artists found with popularity less than {max_popularity}.")
                return
            
            print_info(f"Found {len(candidates)} artists with popularity less than {max_popularity}:")
            display_artists_paginated(candidates, f"Low Popularity Artists (< {max_popularity})")
            
        except ValueError:
            print_error("Invalid number entered.")
            
    elif choice == "5":
        # Back to main menu
        return

# This function has been removed to simplify the scoring system

# This function has been removed to simplify the external dependencies

# This function has been removed to simplify external dependencies

def manual_review_artists(sp, inactive_artists):
    """Show artists for manual review and unfollowing."""
    if not inactive_artists:
        print_warning("No artists to review.")
        return
    
    # Use the new paginated display
    display_artists_paginated(inactive_artists, "Inactive Artists - Manual Review")
    
    # Ask if user wants to unfollow these artists
    unfollow_option = input("\nWould you like to unfollow some of these artists? (y/n): ").strip().lower()
    
    if unfollow_option == "y":
        # Ask which artists to unfollow
        unfollow_input = input("\nEnter the numbers of the artists to unfollow (comma-separated, or 'all'): ").strip().lower()
        
        artists_to_unfollow = []
        if unfollow_input == "all":
            artists_to_unfollow = inactive_artists
        else:
            try:
                indices = [int(idx.strip()) - 1 for idx in unfollow_input.split(",")]
                for idx in indices:
                    if 0 <= idx < len(inactive_artists):
                        artists_to_unfollow.append(inactive_artists[idx])
            except ValueError:
                print_error("Invalid input. Please enter numbers separated by commas.")
                return
        
        if not artists_to_unfollow:
            print_warning("No artists selected to unfollow.")
            return
        
        bulk_unfollow_artists(sp, artists_to_unfollow)

def bulk_unfollow_artists(sp, artists_to_unfollow):
    """Unfollow a list of artists with progress tracking."""
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

def main():
    print_header("Spotify Artist Cleanup Tool")
    print(f"{Fore.CYAN}This tool identifies artists you follow but haven't listened to recently.")
    print(f"{Fore.CYAN}It uses simplified scoring based on popularity and follower count.")
    
    # Set up API client
    print_info("Setting up Spotify client...")
    sp = setup_spotify_client()
    
    # Get artists the user follows
    followed_artists = get_followed_artists(sp)
    if not followed_artists:
        print_warning("You don't follow any artists on Spotify yet.")
        return
    
    print_success(f"You follow {len(followed_artists)} artists on Spotify.")
    
    # Get user's top artists
    top_artists = get_top_artists(sp)
    
    # Get recently played tracks
    recently_played = get_recently_played(sp)
    
    # Use the bulk cleanup interface
    bulk_unfollow_by_criteria(sp, followed_artists, top_artists, recently_played)

if __name__ == "__main__":
    main()
