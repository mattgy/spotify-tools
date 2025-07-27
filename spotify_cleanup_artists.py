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
from spotify_utils import (create_spotify_client, COMMON_SCOPES, safe_spotify_call,
                          print_success, print_error, print_warning, print_info, 
                          print_header, show_spotify_setup_help, CACHE_EXPIRATION)

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
        print(f"{Fore.CYAN}Personal Score = Personal taste relevance | Pop = Spotify popularity | Followers = API count")
        print(f"{Fore.CYAN}🎯 = High personal relevance | ⚠️ = Low followers but high popularity | 🚫 = Do NOT unfollow")
        print(f"{Fore.CYAN}🔍 = Check manually | Monthly listeners NOT available via API\n")
        
        for i, artist in enumerate(page_artists, start_idx + 1):
            # Enhanced display with better formatting and data explanations
            follower_display = f"{artist['followers']:,}" if artist['followers'] > 0 else "0"
            
            # Add personal relevance and warning indicators
            warning = ""
            external_warning = ""
            personal_indicator = ""
            
            # Check for high personal relevance
            if 'personal_relevance_score' in artist and artist['personal_relevance_score'] > 50:
                personal_indicator = f" {Fore.GREEN}🎯"
            
            # Check for traditional warning (low followers, high popularity)
            if artist['followers'] < 100 and artist['popularity'] > 30:
                warning = f" {Fore.MAGENTA}⚠️"
            
            # Check for external popularity validation if available
            if 'external_validation' in artist:
                ext_data = artist['external_validation']
                if not ext_data.get('recommendation', {}).get('safe_to_unfollow', True):
                    external_warning = f" {Fore.RED}🚫"
                elif ext_data.get('recommendation', {}).get('should_check_manually', False):
                    external_warning = f" {Fore.YELLOW}🔍"
            
            # Show personal relevance score if available, otherwise use old score
            if 'personal_relevance_score' in artist:
                personal_score = artist['personal_relevance_score']
                final_score = artist.get('final_score', artist['relevance_score'])
                print(f"{i:3d}. {Fore.WHITE}{artist['name']:<40} " + 
                      f"{Fore.MAGENTA}Personal: {personal_score:4.1f}  " +
                      f"{Fore.YELLOW}Pop: {artist['popularity']:2d}  " +
                      f"{Fore.GREEN}Followers: {follower_display:>8s}  " +
                      f"{Fore.CYAN}Final: {final_score:5.1f}{personal_indicator}{warning}{external_warning}")
            else:
                # Fallback for artists without personal scoring
                print(f"{i:3d}. {Fore.WHITE}{artist['name']:<40} " + 
                      f"{Fore.YELLOW}Pop: {artist['popularity']:2d}/100  " +
                      f"{Fore.GREEN}Followers: {follower_display:>10s}  " +
                      f"{Fore.CYAN}Score: {artist['relevance_score']:5.1f}{warning}{external_warning}")
        
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
    """Identify artists that the user rarely listens to with personal relevance analysis."""
    print_info("Analyzing your listening habits with personalized relevance scoring...")
    
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
    
    # Build personal listening profile for relevance analysis
    print_info("Building your personal taste profile...")
    from personal_relevance import PersonalTasteAnalyzer
    
    # Get Spotify client for personal analysis
    sp = setup_spotify_client()
    taste_analyzer = PersonalTasteAnalyzer(sp)
    user_profile = taste_analyzer.get_comprehensive_listening_profile()
    
    print_success(f"✅ Personal taste profile created!")
    print(f"   • Discovery style: {user_profile.get('discovery_patterns', {}).get('discovery_style', 'unknown')}")
    print(f"   • Top genres: {', '.join(list(user_profile.get('genre_preferences', {}).get('top_genres', {}).keys())[:5])}")
    print(f"   • Niche preference: {user_profile.get('genre_preferences', {}).get('niche_preference_ratio', 0):.1%}")
    
    # Identify inactive artists with personal relevance scoring
    inactive_artists = []
    for artist in followed_artists:
        if artist["id"] not in active_artist_ids:
            # Calculate traditional scores for comparison
            popularity = artist["popularity"]
            followers = artist["followers"]["total"]
            
            import math
            spotify_score = popularity
            
            if followers > 0:
                follower_score = min(100, max(0, math.log10(followers + 1) * 12))
            else:
                follower_score = 0
            
            base_score = (spotify_score * 0.85) + (follower_score * 0.15)
            
            # Add base scores to artist data for personal relevance calculation
            artist_data = {
                "id": artist["id"],
                "name": artist["name"],
                "popularity": popularity,
                "followers": followers,
                "genres": artist.get("genres", []),
                "base_score": base_score,
                "follower_score": follower_score
            }
            
            # Calculate personal relevance score
            from personal_relevance import calculate_personal_relevance_score
            relevance_analysis = calculate_personal_relevance_score(artist_data, user_profile)
            
            # Create comprehensive artist record
            artist_record = {
                "id": artist["id"],
                "name": artist["name"],
                "popularity": popularity,
                "followers": followers,
                "genres": artist.get("genres", []),
                "follower_score": follower_score,
                "base_score": base_score,
                "personal_relevance_score": relevance_analysis["personal_relevance_score"],
                "final_score": relevance_analysis["final_score"],
                "confidence": relevance_analysis["confidence"],
                "scoring_breakdown": relevance_analysis["scoring_breakdown"],
                "recommendation": relevance_analysis["recommendation"],
                "relevance_score": relevance_analysis["final_score"],  # For backward compatibility
                "artist_importance_score": relevance_analysis["final_score"]  # For backward compatibility
            }
            
            inactive_artists.append(artist_record)
    
    # Sort by final score (ascending, so least relevant first)
    inactive_artists.sort(key=lambda x: x["final_score"])
    
    print_success(f"Found {len(inactive_artists)} inactive artists with personalized scoring.")
    
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
    print(f"\n{Fore.WHITE}Personal Relevance Cleanup Options:")
    print("1. Set personal relevance threshold (recommended - uses your taste profile)")
    print("2. Run external popularity validation on all candidates")
    print("3. Show candidates for manual review (with pagination)")
    print("4. Show personal taste profile summary")
    print("5. Legacy: Unfollow by raw follower count")
    print("6. Legacy: Unfollow by Spotify popularity score")
    print("7. Debug specific artist data")
    print("8. Back to main menu")
    
    choice = input(f"\n{Fore.CYAN}Enter your choice (1-8): ")
    
    if choice == "1":
        # Personal relevance threshold
        print_header("Personal Relevance Scoring")
        print(f"{Fore.CYAN}This uses your personal listening profile to score artists based on:")
        print(f"{Fore.CYAN}• Genre similarity to your preferences")
        print(f"{Fore.CYAN}• Alignment with your discovery style (niche vs mainstream)")
        print(f"{Fore.CYAN}• Popularity patterns that match your listening habits")
        print(f"{Fore.CYAN}• External validation when available")
        print(f"\n{Fore.YELLOW}Personal relevance score ranges:")
        print(f"{Fore.YELLOW}• 60-100: High personal relevance (strong match to your taste)")
        print(f"{Fore.YELLOW}• 40-59:  Moderate relevance (some alignment with your preferences)")
        print(f"{Fore.YELLOW}• 20-39:  Low relevance (limited alignment)")
        print(f"{Fore.YELLOW}• 0-19:   Very low relevance (doesn't match your taste)")
        
        try:
            threshold = float(input(f"\n{Fore.CYAN}Set minimum final score to keep artists (recommended: 30): ") or "30")
            
            # Filter artists below threshold
            candidates = [a for a in inactive_artists if a.get('final_score', a.get('artist_importance_score', 0)) < threshold]
            
            if not candidates:
                print_warning(f"No inactive artists found with final score below {threshold:.1f}.")
                return
            
            print_info(f"Found {len(candidates)} artists with final score below {threshold:.1f}:")
            
            # Show breakdown of candidates by personal relevance
            if any('personal_relevance_score' in a for a in candidates):
                high_personal = len([a for a in candidates if a.get('personal_relevance_score', 0) > 50])
                if high_personal > 0:
                    print(f"\n{Fore.RED}⚠️ WARNING: {high_personal} artists have high personal relevance but low final scores!")
                    print(f"{Fore.RED}   These might be unpopular artists that match your taste. Review carefully.")
            
            # Options for handling the candidates
            print(f"\n{Fore.CYAN}Options:")
            print(f"{Fore.WHITE}1. Browse all candidates with pagination")
            print(f"{Fore.WHITE}2. Unfollow all {len(candidates)} candidates immediately")
            print(f"{Fore.WHITE}3. Cancel and go back")
            
            action = input(f"\n{Fore.CYAN}Choose action (1-3): ").strip()
            
            if action == "1":
                # Browse with pagination
                display_artists_paginated(candidates, f"Artists with Final Score < {threshold:.1f}")
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
        # Run external popularity validation
        run_external_validation(sp, inactive_artists)
            
    elif choice == "3":
        # Show candidates for manual review
        manual_review_artists(sp, inactive_artists[:50])
        
    elif choice == "4":
        # Show personal taste profile summary
        show_personal_taste_summary(inactive_artists)
        
    elif choice == "5":
        # Legacy: Unfollow by raw follower count
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
            
    elif choice == "6":
        # Legacy: Unfollow by Spotify popularity score
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
            
    elif choice == "7":
        # Debug specific artist data
        artist_name = input("Enter artist name to debug: ").strip()
        if artist_name:
            debug_specific_artist(sp, artist_name)
        
    elif choice == "8":
        # Back to main menu
        return

def show_personal_taste_summary(inactive_artists):
    """Show a summary of the user's personal taste profile and how it affects scoring."""
    print_header("Personal Taste Profile Summary")
    
    # Check if we have personal relevance data
    artists_with_personal_data = [a for a in inactive_artists if 'personal_relevance_score' in a]
    
    if not artists_with_personal_data:
        print_warning("No personal relevance data available. Run the main analysis first.")
        return
    
    # Analyze the distribution of personal relevance scores
    personal_scores = [a['personal_relevance_score'] for a in artists_with_personal_data]
    final_scores = [a['final_score'] for a in artists_with_personal_data]
    
    avg_personal = sum(personal_scores) / len(personal_scores)
    avg_final = sum(final_scores) / len(final_scores)
    
    high_personal = len([s for s in personal_scores if s > 50])
    low_personal = len([s for s in personal_scores if s < 20])
    
    print(f"{Fore.CYAN}Personal Taste Analysis:")
    print(f"  • Average personal relevance score: {avg_personal:.1f}")
    print(f"  • Average final score: {avg_final:.1f}")
    print(f"  • Artists with high personal relevance (>50): {high_personal}")
    print(f"  • Artists with low personal relevance (<20): {low_personal}")
    
    # Show scoring breakdown for a few example artists
    print(f"\n{Fore.YELLOW}Example Scoring Breakdowns:")
    
    # Show highest personal relevance artist
    highest_personal = max(artists_with_personal_data, key=lambda x: x['personal_relevance_score'])
    print(f"\n{Fore.GREEN}🎯 Highest Personal Relevance: {highest_personal['name']}")
    if 'scoring_breakdown' in highest_personal:
        breakdown = highest_personal['scoring_breakdown']
        print(f"  • Genre similarity: {breakdown.get('genre_similarity', 0):.1f}")
        print(f"  • Popularity alignment: {breakdown.get('popularity_alignment', 0):.1f}")
        print(f"  • Discovery style match: {breakdown.get('discovery_style_match', 0):.1f}")
        print(f"  • Personal relevance total: {highest_personal['personal_relevance_score']:.1f}")
        print(f"  • Final score: {highest_personal['final_score']:.1f}")
        print(f"  • Recommendation: {highest_personal.get('recommendation', {}).get('reasoning', 'N/A')}")
    
    # Show lowest personal relevance artist
    lowest_personal = min(artists_with_personal_data, key=lambda x: x['personal_relevance_score'])
    print(f"\n{Fore.RED}❌ Lowest Personal Relevance: {lowest_personal['name']}")
    if 'scoring_breakdown' in lowest_personal:
        breakdown = lowest_personal['scoring_breakdown']
        print(f"  • Genre similarity: {breakdown.get('genre_similarity', 0):.1f}")
        print(f"  • Popularity alignment: {breakdown.get('popularity_alignment', 0):.1f}")
        print(f"  • Discovery style match: {breakdown.get('discovery_style_match', 0):.1f}")
        print(f"  • Personal relevance total: {lowest_personal['personal_relevance_score']:.1f}")
        print(f"  • Final score: {lowest_personal['final_score']:.1f}")
        print(f"  • Recommendation: {lowest_personal.get('recommendation', {}).get('reasoning', 'N/A')}")
    
    # Show artists with high personal relevance but low final scores (potential false positives)
    conflicted_artists = [a for a in artists_with_personal_data 
                         if a['personal_relevance_score'] > 50 and a['final_score'] < 30]
    
    if conflicted_artists:
        print(f"\n{Fore.MAGENTA}⚠️ Artists with High Personal Relevance but Low Final Scores:")
        print(f"{Fore.MAGENTA}These are likely niche artists that match your taste but aren't generally popular.")
        for artist in conflicted_artists[:5]:
            print(f"  • {artist['name']}: Personal {artist['personal_relevance_score']:.1f}, Final {artist['final_score']:.1f}")
        if len(conflicted_artists) > 5:
            print(f"  ... and {len(conflicted_artists) - 5} more")
    
    input(f"\n{Fore.CYAN}Press Enter to continue...")

def run_external_validation(sp, inactive_artists):
    """Run external popularity validation on inactive artists."""
    from external_popularity import validate_artist_for_unfollowing
    
    print_header("External Popularity Validation")
    print(f"{Fore.YELLOW}This will check {len(inactive_artists)} artists against external APIs")
    print(f"{Fore.YELLOW}(Last.fm, MusicBrainz) to find potentially popular artists.")
    print(f"{Fore.CYAN}This may take a few minutes...")
    
    confirm = input("\nProceed with external validation? (y/n): ").strip().lower()
    if confirm != 'y':
        return
    
    # Create progress tracking
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    validated_artists = []
    progress = create_progress_bar(len(inactive_artists), "Validating artists")
    
    for i, artist in enumerate(inactive_artists):
        try:
            # Add external validation data to artist
            validation = validate_artist_for_unfollowing(artist['name'], artist)
            artist['external_validation'] = validation
            validated_artists.append(artist)
            
            update_progress_bar(progress, i + 1)
            
            # Add small delay to be respectful to external APIs
            time.sleep(0.5)
            
        except Exception as e:
            print_warning(f"Failed to validate {artist['name']}: {e}")
            validated_artists.append(artist)  # Keep without validation
            update_progress_bar(progress, i + 1)
    
    close_progress_bar(progress)
    
    # Analyze results
    safe_to_unfollow = []
    should_not_unfollow = []
    needs_manual_check = []
    
    for artist in validated_artists:
        if 'external_validation' in artist:
            recommendation = artist['external_validation'].get('recommendation', {})
            if not recommendation.get('safe_to_unfollow', True):
                should_not_unfollow.append(artist)
            elif recommendation.get('should_check_manually', False):
                needs_manual_check.append(artist)
            else:
                safe_to_unfollow.append(artist)
        else:
            safe_to_unfollow.append(artist)  # Default to safe if no validation
    
    # Display results
    print_header("External Validation Results")
    
    if should_not_unfollow:
        print(f"\n{Fore.RED}🚫 DO NOT UNFOLLOW ({len(should_not_unfollow)} artists):")
        print(f"{Fore.RED}These artists are popular on external platforms!")
        for artist in should_not_unfollow[:10]:  # Show first 10
            ext_data = artist['external_validation']['external_data']
            score = ext_data.get('cross_platform_score', 0)
            print(f"  • {artist['name']} (External score: {score:.1f})")
        if len(should_not_unfollow) > 10:
            print(f"  ... and {len(should_not_unfollow) - 10} more")
    
    if needs_manual_check:
        print(f"\n{Fore.YELLOW}🔍 MANUAL CHECK RECOMMENDED ({len(needs_manual_check)} artists):")
        for artist in needs_manual_check[:5]:  # Show first 5
            print(f"  • {artist['name']}")
        if len(needs_manual_check) > 5:
            print(f"  ... and {len(needs_manual_check) - 5} more")
    
    if safe_to_unfollow:
        print(f"\n{Fore.GREEN}✅ PROBABLY SAFE TO UNFOLLOW ({len(safe_to_unfollow)} artists)")
    
    # Ask if user wants to see detailed results with pagination
    if should_not_unfollow or needs_manual_check:
        show_details = input(f"\n{Fore.CYAN}Show detailed results with pagination? (y/n): ").strip().lower()
        if show_details == 'y':
            all_validated = should_not_unfollow + needs_manual_check + safe_to_unfollow
            display_artists_paginated(all_validated, "External Validation Results")

def debug_specific_artist(sp, artist_name):
    """Debug specific artist data to help understand API vs app discrepancies."""
    try:
        # Search for the artist
        results = sp.search(q=artist_name, type='artist', limit=5)
        
        if not results['artists']['items']:
            print_warning(f"No artists found for '{artist_name}'")
            return
        
        print_header(f"Artist Data Debug: {artist_name}")
        
        for i, artist in enumerate(results['artists']['items']):
            print(f"\n{i+1}. {Fore.WHITE}{artist['name']}")
            print(f"   {Fore.CYAN}Spotify ID: {artist['id']}")
            print(f"   {Fore.GREEN}API Followers: {artist['followers']['total']:,}")
            print(f"   {Fore.YELLOW}Popularity Score: {artist['popularity']}/100")
            print(f"   {Fore.BLUE}Genres: {', '.join(artist['genres']) if artist['genres'] else 'None'}")
            print(f"   {Fore.MAGENTA}Spotify URL: {artist['external_urls']['spotify']}")
            
            # Check if user follows this artist
            is_following = sp.current_user_following_artists([artist['id']])[0]
            status = f"{Fore.GREEN}✅ Following" if is_following else f"{Fore.RED}❌ Not following"
            print(f"   {status}")
            
            # Run comprehensive analysis for the first (most relevant) result
            if i == 0:
                print(f"\n{Fore.CYAN}Running comprehensive analysis...")
                
                # External validation
                from external_popularity import print_artist_popularity_report
                print_artist_popularity_report(artist['name'], artist)
                
                # Personal relevance analysis if we have the profile
                try:
                    from personal_relevance import PersonalTasteAnalyzer, calculate_personal_relevance_score
                    
                    sp_client = setup_spotify_client()
                    taste_analyzer = PersonalTasteAnalyzer(sp_client)
                    user_profile = taste_analyzer.get_comprehensive_listening_profile()
                    
                    print(f"\n{Fore.MAGENTA}Personal Relevance Analysis:")
                    print(f"═" * 50)
                    
                    # Calculate personal relevance
                    artist_data = {
                        "id": artist["id"],
                        "name": artist["name"],
                        "popularity": artist["popularity"],
                        "followers": artist["followers"]["total"],
                        "genres": artist.get("genres", []),
                        "base_score": artist["popularity"]  # Simplified for debug
                    }
                    
                    relevance_analysis = calculate_personal_relevance_score(artist_data, user_profile)
                    
                    print(f"Personal Relevance Score: {relevance_analysis['personal_relevance_score']:.1f}/100")
                    print(f"Final Combined Score: {relevance_analysis['final_score']:.1f}/100")
                    print(f"Confidence Level: {relevance_analysis['confidence']}")
                    
                    breakdown = relevance_analysis['scoring_breakdown']
                    print(f"\nScoring Breakdown:")
                    print(f"  • Genre similarity: {breakdown.get('genre_similarity', 0):.1f}/40")
                    print(f"  • Popularity alignment: {breakdown.get('popularity_alignment', 0):.1f}/30")
                    print(f"  • Discovery style match: {breakdown.get('discovery_style_match', 0):.1f}/30")
                    
                    rec = relevance_analysis['recommendation']
                    color = Fore.RED if not rec['safe_to_unfollow'] else Fore.GREEN
                    print(f"\n{color}Personal Recommendation:")
                    print(f"{color}  Safe to unfollow: {'No' if not rec['safe_to_unfollow'] else 'Yes'}")
                    print(f"{color}  Reasoning: {rec['reasoning']}")
                    
                except Exception as e:
                    print(f"{Fore.YELLOW}Could not run personal relevance analysis: {e}")
                
                break
        
        input(f"\n{Fore.CYAN}Press Enter to continue...")
        
    except Exception as e:
        print_error(f"Error debugging artist: {e}")

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
    print_header("Personal Relevance-Based Artist Cleanup")
    print(f"{Fore.CYAN}This tool analyzes your personal listening patterns to identify artists")
    print(f"{Fore.CYAN}you follow but rarely listen to, while preserving those that match your taste.")
    
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
    
    # Use the new bulk cleanup interface
    bulk_unfollow_by_criteria(sp, followed_artists, top_artists, recently_played)

if __name__ == "__main__":
    main()
