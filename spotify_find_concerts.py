#!/usr/bin/env python3
"""
Script to find upcoming concerts for artists you follow on Spotify.

This script:
1. Authenticates with your Spotify account
2. Gets all artists you currently follow
3. Uses alternative APIs or web scraping to find upcoming concerts for those artists
4. Displays concert information including venue, date, and ticket links

Requirements:
- Python 3.6+
- spotipy library (pip install spotipy)
- requests library (pip install requests)
- beautifulsoup4 library (pip install beautifulsoup4)
"""

import os
import sys
import time
import datetime
import json
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from collections import defaultdict
import re
from bs4 import BeautifulSoup
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

# Spotify API scopes needed for this script
SPOTIFY_SCOPES = [
    "user-follow-read"
]

# Cache expiration (in seconds)
CACHE_EXPIRATION = 24 * 60 * 60  # 24 hours

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
        print(f"Error setting up Spotify client: {e}")
        print("\nTo set up a Spotify Developer account and create an app:")
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
        print(f"Found {len(cached_data)} artists that you follow (from cache)")
        return cached_data
    
    artists = []
    after = None
    limit = 50
    total_processed = 0
    
    print("Fetching artists you follow on Spotify...")
    
    # Import tqdm utilities
    sys.path.insert(0, script_dir)
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    # First, get the total count
    results = sp.current_user_followed_artists(limit=1)
    total_artists = results['artists']['total']
    
    # Create progress bar
    progress_bar = create_progress_bar(total=total_artists, desc="Fetching artists", unit="artist")
    
    while True:
        results = sp.current_user_followed_artists(limit=limit, after=after)
        batch_size = len(results['artists']['items'])
        total_processed += batch_size
        
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
    
    print(f"{Fore.GREEN}Found {len(artists)} artists that you follow")
    
    # Save to cache
    save_to_cache(artists, cache_key)
    
    return artists

def get_concerts_from_web_search(artist_name):
    """
    Get concerts by searching for them on the web using web scraping.
    This is a basic implementation that could be expanded.
    """
    concerts = []
    
    # Create a cache key based on artist name
    cache_key = f"concerts_{artist_name}".replace(" ", "_").lower()
    
    # Try to load from cache first
    cached_result = load_from_cache(cache_key, CACHE_EXPIRATION)
    if cached_result:
        return cached_result
    
    try:
        # Use Bandsintown as the primary source
        url = f"https://www.bandsintown.com/a/{artist_name.replace(' ', '%20')}"
        
        # Add a user agent to avoid being blocked
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Make the request with a shorter timeout
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for event listings
            event_elements = soup.select('.event-row, .event-listing, .tour-date')
            
            for element in event_elements:
                try:
                    # Extract date - look for common date formats
                    date_element = element.select_one('.date, .event-date, .datetime')
                    date_str = date_element.text.strip() if date_element else "Date not found"
                    
                    # Extract venue
                    venue_element = element.select_one('.venue, .event-venue, .location')
                    venue = venue_element.text.strip() if venue_element else "Venue not found"
                    
                    # Extract city/country
                    location_element = element.select_one('.location, .event-location, .city')
                    location = location_element.text.strip() if location_element else ""
                    
                    # Try to split location into city and country
                    city = location
                    country = ""
                    if "," in location:
                        parts = location.split(",")
                        city = parts[0].strip()
                        country = parts[-1].strip()
                    
                    # Extract ticket URL
                    ticket_element = element.select_one('a.tickets, a.ticket-link, a[href*="ticket"]')
                    ticket_url = ticket_element['href'] if ticket_element and 'href' in ticket_element.attrs else ""
                    
                    # Create concert object
                    concert = {
                        "artist": artist_name,
                        "date": date_str,
                        "venue": venue,
                        "city": city,
                        "country": country,
                        "url": ticket_url
                    }
                    
                    concerts.append(concert)
                except Exception as e:
                    # Skip this element if there's an error parsing it
                    continue
        
        # Save to cache to avoid repeated requests
        save_to_cache(concerts, cache_key)
        
    except requests.exceptions.Timeout:
        pass  # Silently handle timeout
    except requests.exceptions.ConnectionError:
        pass  # Silently handle connection error
    except Exception:
        pass  # Silently handle other exceptions
    
    return concerts

def filter_concerts_by_location(concerts, city=None, country=None):
    """Filter concerts by location."""
    if not city and not country:
        return concerts
    
    filtered_concerts = []
    for concert in concerts:
        if city and country:
            if city.lower() in concert["city"].lower() and country.lower() in concert["country"].lower():
                filtered_concerts.append(concert)
        elif city:
            if city.lower() in concert["city"].lower():
                filtered_concerts.append(concert)
        elif country:
            if country.lower() in concert["country"].lower():
                filtered_concerts.append(concert)
    
    return filtered_concerts

def main():
    # Set up API client
    print(f"{Fore.CYAN}Setting up Spotify client...")
    sp = setup_spotify_client()
    
    # Get artists the user follows
    followed_artists = get_followed_artists(sp)
    if not followed_artists:
        print(f"{Fore.YELLOW}You don't follow any artists on Spotify yet.")
        return
    
    # Ask for location filtering
    print(f"\n{Fore.CYAN}Location filtering (optional):")
    city = input("Enter city name to filter concerts (leave blank for all cities): ").strip()
    country = input("Enter country name to filter concerts (leave blank for all countries): ").strip()
    
    # Get concerts for each artist
    print(f"\n{Fore.CYAN}Searching for upcoming concerts...")
    print(f"{Fore.YELLOW}Note: This feature now uses web searches instead of the Songkick API.")
    print(f"{Fore.YELLOW}Results may be limited as the Songkick API is no longer freely available.")
    
    # Ask if user wants to limit the search to save time
    print(f"\n{Fore.CYAN}Search options:")
    print(f"{Fore.YELLOW}Searching for concerts for all {len(followed_artists)} artists may take a long time.")
    limit_search = input("Would you like to limit the search to your top artists? (y/n): ").strip().lower()
    
    if limit_search == 'y':
        limit = input("Enter the number of top artists to search (recommended: 20-50): ").strip()
        try:
            limit = int(limit)
            if limit <= 0:
                limit = 20
        except ValueError:
            limit = 20
        
        # Sort artists by popularity and take the top ones
        followed_artists.sort(key=lambda x: x.get('popularity', 0), reverse=True)
        followed_artists = followed_artists[:limit]
        print(f"{Fore.GREEN}Limiting search to your top {limit} artists by popularity.")
    
    all_concerts = []
    total_artists = len(followed_artists)
    
    # Import tqdm utilities
    sys.path.insert(0, script_dir)
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    # Create progress bar
    progress_bar = create_progress_bar(total=total_artists, desc="Checking concerts", unit="artist")
    
    # Create a session for connection pooling
    session = requests.Session()
    
    # Set a shorter timeout for the session
    session.request = lambda method, url, **kwargs: super(requests.Session, session).request(
        method=method, url=url, **{**kwargs, 'timeout': 3}
    )
    
    # Add delay between requests to avoid overwhelming servers
    delay_between_requests = 0.5  # seconds
    
    # Add error handling for the entire loop
    try:
        for i, artist in enumerate(followed_artists, 1):
            artist_name = artist['name']
            
            try:
                # Get concerts using web search
                concerts = get_concerts_from_web_search(artist_name)
                
                all_concerts.extend(concerts)
            except Exception as e:
                print_warning(f"Error processing {artist_name}: {str(e)[:50]}...")
                # Continue with the next artist
                continue
            
            # Update progress bar
            update_progress_bar(progress_bar, 1)
            
            # Add a delay to avoid hitting rate limits and overwhelming servers
            time.sleep(delay_between_requests)
    except KeyboardInterrupt:
        print_warning("\nSearch interrupted by user. Processing results so far...")
    except Exception as e:
        print_error(f"An error occurred during the search: {str(e)}")
        print_warning("Processing any results found so far...")
    
    # Close progress bar
    close_progress_bar(progress_bar)
    
    # Close the session
    session.close()
    
    # Filter concerts by location if specified
    if city or country:
        filtered_concerts = filter_concerts_by_location(all_concerts, city, country)
        print(f"\n{Fore.GREEN}Found {len(filtered_concerts)} concerts matching your location filters.")
    else:
        filtered_concerts = all_concerts
        print(f"\n{Fore.GREEN}Found {len(filtered_concerts)} upcoming concerts for your artists.")
    
    if not filtered_concerts:
        print(f"\n{Fore.YELLOW}No upcoming concerts found for your followed artists.")
        print("This could be because:")
        print("1. Your artists don't have any upcoming concerts")
        print("2. The web search didn't find any concerts")
        print("3. The Songkick API is no longer freely available")
        print("\nYou might want to check artist websites directly for tour information.")
        return
    
    # Sort concerts by date
    filtered_concerts.sort(key=lambda x: x["date"])
    
    # Group concerts by artist
    concerts_by_artist = defaultdict(list)
    for concert in filtered_concerts:
        concerts_by_artist[concert["artist"]].append(concert)
    
    # Display concerts
    print(f"\n{Fore.CYAN}Upcoming concerts:")
    for artist, concerts in concerts_by_artist.items():
        print(f"\n{Fore.GREEN}{artist}:")
        for i, concert in enumerate(concerts, 1):
            print(f"  {i}. {concert['venue']} - {concert['city']}, {concert['country']}")
            print(f"     Date: {concert['date']}")
            if concert['url']:
                print(f"     Tickets: {concert['url']}")
            else:
                print("     Tickets: No link available")
    
    # Generate a date-stamped filename
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    default_filename = f"{current_date}-upcoming_concerts.txt"
    
    # Ask if user wants to use a different filename
    print(f"\n{Fore.CYAN}Saving concerts to file...")
    filename = input(f"Enter filename (default: {default_filename}): ").strip()
    if not filename:
        filename = default_filename
    
    # Save to file
    with open(filename, "w") as f:
        f.write(f"UPCOMING CONCERTS - Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Location filters: City: {city or 'None'}, Country: {country or 'None'}\n\n")
        
        for artist, concerts in concerts_by_artist.items():
            f.write(f"{artist}:\n")
            for i, concert in enumerate(concerts, 1):
                f.write(f"  {i}. {concert['venue']} - {concert['city']}, {concert['country']}\n")
                f.write(f"     Date: {concert['date']}\n")
                if concert['url']:
                    f.write(f"     Tickets: {concert['url']}\n")
                else:
                    f.write("     Tickets: No link available\n")
            f.write("\n")
    
    print_success(f"Concerts saved to {filename}")
    
    # Also save as JSON for programmatic use
    json_filename = filename.replace(".txt", ".json")
    with open(json_filename, "w") as f:
        json.dump(filtered_concerts, f, indent=2)
    print(f"Concert data also saved to {json_filename}")

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

if __name__ == "__main__":
    main()
