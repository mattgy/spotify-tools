#!/usr/bin/env python3
"""
Shared utilities for Spotify API operations across the project.
Includes rate limiting, error handling, and common patterns.
"""

import time
import functools
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Common print functions for consistent messaging across the project
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

def print_header(text):
    """Print a formatted header."""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}" + "="*50)
    print(f"{Fore.CYAN}{Style.BRIGHT}{text}")
    print(f"{Fore.CYAN}{Style.BRIGHT}" + "="*50)

# Import centralized constants
from constants import CACHE_EXPIRATION, SPOTIFY_SCOPES, RATE_LIMITS

def show_spotify_setup_help():
    """Show standardized help for setting up Spotify API credentials."""
    print_info("\nTo set up a Spotify Developer account and create an app:")
    print("1. Go to https://developer.spotify.com/dashboard/")
    print("2. Log in and create a new app")
    print("3. Set the redirect URI to http://127.0.0.1:8888/callback")
    print("4. Copy the Client ID and Client Secret")
    print("5. Run this script again and provide the credentials when prompted")

def safe_spotify_call(func):
    """
    Decorator for safe Spotify API calls with automatic retry on rate limiting.
    
    Usage:
        @safe_spotify_call
        def my_api_call(sp, *args, **kwargs):
            return sp.some_api_method(*args, **kwargs)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['rate', 'limit', '429', 'too many requests']):
                    if attempt < max_retries - 1:
                        print(f"{Fore.YELLOW}⚠️  Rate limit hit. Waiting {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        print(f"{Fore.RED}❌ Rate limiting persists after {max_retries} attempts.")
                        raise
                elif '403' in error_str and ('audio-features' in error_str or 'audio_features' in error_str):
                    # Handle audio features permission issues gracefully
                    print(f"{Fore.YELLOW}Warning: Audio features not accessible (likely missing scope)")
                    return None
                else:
                    raise
        
        return None
    return wrapper

class SafeSpotifyClient:
    """
    Wrapper around spotipy.Spotify with built-in rate limiting and error handling.
    Can be used as a drop-in replacement for spotipy.Spotify.
    """
    
    def __init__(self, sp_client):
        """Initialize with an existing Spotify client."""
        self._sp = sp_client
        
    def __getattr__(self, name):
        """Wrap all Spotify API methods with rate limiting."""
        attr = getattr(self._sp, name)
        
        if callable(attr) and not name.startswith('_'):
            # Wrap API methods with rate limiting
            @safe_spotify_call
            def safe_method(*args, **kwargs):
                # Add small delay between calls
                time.sleep(0.1)
                return attr(*args, **kwargs)
            
            return safe_method
        else:
            return attr

def create_spotify_client(scopes, cache_path_suffix="", auto_open_browser=True):
    """
    Create a standardized Spotify client with proper authentication and rate limiting.
    
    Args:
        scopes: List of required Spotify scopes
        cache_path_suffix: Optional suffix for cache file (e.g., "analytics", "cleanup")
        auto_open_browser: Whether to automatically open browser for auth (default: True)
    
    Returns:
        SafeSpotifyClient instance
    """
    try:
        from credentials_manager import get_spotify_credentials
        import os
        
        client_id, client_secret, redirect_uri = get_spotify_credentials()
        
        # Create cache path
        cache_filename = "spotify_token_cache"
        if cache_path_suffix:
            cache_filename += f"_{cache_path_suffix}"
        
        cache_path = os.path.join(os.path.expanduser("~"), ".spotify-tools", cache_filename)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=" ".join(scopes),
            open_browser=auto_open_browser,
            cache_path=cache_path
        )
        
        # Create Spotify client with retries and timeout
        sp = spotipy.Spotify(
            auth_manager=auth_manager, 
            requests_timeout=30, 
            retries=3,
            backoff_factor=0.3
        )
        
        # Test the connection (this will trigger auth if needed)
        try:
            sp.current_user()
            print_success("✅ Successfully authenticated with Spotify!")
        except Exception as auth_error:
            if auto_open_browser:
                print_info("🔐 Opening browser for Spotify authentication...")
            else:
                print_info("🔐 Authentication required. Please follow the prompts.")
            # Re-raise to let spotipy handle the auth flow
            raise
        
        return SafeSpotifyClient(sp)
        
    except Exception as e:
        print_error(f"Error setting up Spotify client: {e}")
        raise

def paginate_spotify_results(api_call, *args, **kwargs):
    """
    Generic pagination helper for Spotify API calls that return paginated results.
    
    Args:
        api_call: The Spotify API method to call
        *args, **kwargs: Arguments to pass to the API call
    
    Yields:
        Individual items from all pages
    """
    results = api_call(*args, **kwargs)
    
    while True:
        if 'items' in results:
            for item in results['items']:
                yield item
        elif 'artists' in results and 'items' in results['artists']:
            # Handle followed artists format
            for item in results['artists']['items']:
                yield item
        else:
            break
        
        if results.get('next'):
            # Add delay between pages
            time.sleep(0.1)
            results = api_call._sp.next(results)
        elif 'artists' in results and results['artists'].get('next'):
            # Handle followed artists pagination
            time.sleep(0.1)
            results = api_call._sp.next(results['artists'])
        else:
            break

def batch_process_items(items, batch_size, process_func, delay_between_batches=0.1):
    """
    Process items in batches with rate limiting.
    
    Args:
        items: List of items to process
        batch_size: Number of items per batch
        process_func: Function to process each batch
        delay_between_batches: Delay in seconds between batches
    
    Returns:
        List of results from all batches
    """
    results = []
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        
        try:
            batch_result = process_func(batch)
            if batch_result is not None:
                if isinstance(batch_result, list):
                    results.extend(batch_result)
                else:
                    results.append(batch_result)
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Error processing batch {i//batch_size + 1}: {e}")
        
        # Add delay between batches
        if i + batch_size < len(items):
            time.sleep(delay_between_batches)
    
    return results

# Alias for backward compatibility
COMMON_SCOPES = SPOTIFY_SCOPES

# Reusable Spotify fetching functions with progress bars and caching
def fetch_user_playlists(sp, show_progress=True, cache_key="user_playlists", cache_expiration=None):
    """
    Fetch all user playlists with progress bar and caching.
    
    Args:
        sp: Spotify client
        show_progress: Whether to show progress bar
        cache_key: Cache key for storing results
        cache_expiration: Cache expiration in seconds (default from constants)
    
    Returns:
        List of playlist objects
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('medium', 24 * 60 * 60)
    
    # Try cache first
    cached_data = load_from_cache(cache_key, cache_expiration)
    if cached_data:
        if show_progress:
            print_info(f"Found {len(cached_data)} playlists (from cache)")
        return cached_data
    
    playlists = []
    limit = 50
    
    if show_progress:
        print_info("Fetching your playlists...")
        # Get total count first
        initial_results = sp.current_user_playlists(limit=1)
        total_playlists = initial_results['total']
        progress_bar = create_progress_bar(total=total_playlists, desc="Fetching playlists", unit="playlist")
    
    results = sp.current_user_playlists(limit=limit)
    
    while True:
        batch_playlists = results['items']
        playlists.extend(batch_playlists)
        
        if show_progress:
            update_progress_bar(progress_bar, len(batch_playlists))
        
        if results['next']:
            time.sleep(0.1)  # Rate limiting
            results = sp.next(results)
        else:
            break
    
    if show_progress:
        close_progress_bar(progress_bar)
        print_success(f"Found {len(playlists)} playlists")
    
    # Cache results
    save_to_cache(playlists, cache_key)
    return playlists

def fetch_user_saved_tracks(sp, show_progress=True, cache_key="saved_tracks", cache_expiration=None):
    """
    Fetch all user saved tracks with progress bar and caching.
    
    Args:
        sp: Spotify client
        show_progress: Whether to show progress bar
        cache_key: Cache key for storing results
        cache_expiration: Cache expiration in seconds
    
    Returns:
        List of saved track objects
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('personal', 3 * 24 * 60 * 60)
    
    # Try cache first
    cached_data = load_from_cache(cache_key, cache_expiration)
    if cached_data:
        if show_progress:
            print_info(f"Found {len(cached_data)} saved tracks (from cache)")
        return cached_data
    
    tracks = []
    limit = 50
    
    if show_progress:
        print_info("Fetching your saved tracks...")
        # Get total count first
        initial_results = sp.current_user_saved_tracks(limit=1)
        total_tracks = initial_results['total']
        progress_bar = create_progress_bar(total=total_tracks, desc="Fetching saved tracks", unit="track")
    
    results = sp.current_user_saved_tracks(limit=limit)
    
    while True:
        batch_tracks = results['items']
        tracks.extend(batch_tracks)
        
        if show_progress:
            update_progress_bar(progress_bar, len(batch_tracks))
        
        if results['next']:
            time.sleep(0.1)  # Rate limiting
            results = sp.next(results)
        else:
            break
    
    if show_progress:
        close_progress_bar(progress_bar)
        print_success(f"Found {len(tracks)} saved tracks")
    
    # Cache results
    save_to_cache(tracks, cache_key)
    return tracks

def fetch_followed_artists(sp, show_progress=True, cache_key="followed_artists", cache_expiration=None):
    """
    Fetch all followed artists with progress bar and caching.
    
    Args:
        sp: Spotify client
        show_progress: Whether to show progress bar
        cache_key: Cache key for storing results
        cache_expiration: Cache expiration in seconds
    
    Returns:
        List of artist objects
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('medium', 24 * 60 * 60)
    
    # Try cache first
    cached_data = load_from_cache(cache_key, cache_expiration)
    if cached_data:
        if show_progress:
            print_info(f"Found {len(cached_data)} followed artists (from cache)")
        return cached_data
    
    artists = []
    limit = 50
    
    if show_progress:
        print_info("Fetching followed artists...")
        # Get total count first
        initial_results = sp.current_user_followed_artists(limit=1)
        total_artists = initial_results['artists']['total']
        progress_bar = create_progress_bar(total=total_artists, desc="Fetching followed artists", unit="artist")
    
    results = sp.current_user_followed_artists(limit=limit)
    
    while True:
        batch_artists = results['artists']['items']
        artists.extend(batch_artists)
        
        if show_progress:
            update_progress_bar(progress_bar, len(batch_artists))
        
        if results['artists']['next']:
            time.sleep(0.1)  # Rate limiting
            results = sp.next(results['artists'])
        else:
            break
    
    if show_progress:
        close_progress_bar(progress_bar)
        print_success(f"Found {len(artists)} followed artists")
    
    # Cache results
    save_to_cache(artists, cache_key)
    return artists

def fetch_playlist_tracks(sp, playlist_id, show_progress=True, cache_key=None, cache_expiration=None):
    """
    Fetch all tracks from a playlist with progress bar and caching.
    
    Args:
        sp: Spotify client
        playlist_id: Playlist ID
        show_progress: Whether to show progress bar
        cache_key: Cache key for storing results (auto-generated if None)
        cache_expiration: Cache expiration in seconds
    
    Returns:
        List of track objects
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('medium', 24 * 60 * 60)
    
    if cache_key is None:
        cache_key = f"playlist_tracks_{playlist_id}"
    
    # Try cache first
    cached_data = load_from_cache(cache_key, cache_expiration)
    if cached_data:
        return cached_data
    
    tracks = []
    limit = 100
    
    # Get total count first
    playlist_info = sp.playlist(playlist_id, fields="tracks.total,name")
    total_tracks = playlist_info['tracks']['total']
    
    if show_progress and total_tracks > 50:
        playlist_name = playlist_info.get('name', 'Unknown')
        progress_bar = create_progress_bar(total=total_tracks, desc=f"Fetching tracks from {playlist_name}", unit="track")
    
    results = sp.playlist_items(playlist_id, limit=limit)
    
    while True:
        batch_tracks = results['items']
        tracks.extend(batch_tracks)
        
        if show_progress and total_tracks > 50:
            update_progress_bar(progress_bar, len(batch_tracks))
        
        if results['next']:
            time.sleep(0.1)  # Rate limiting
            results = sp.next(results)
        else:
            break
    
    if show_progress and total_tracks > 50:
        close_progress_bar(progress_bar)
    
    # Cache results
    save_to_cache(tracks, cache_key)
    return tracks

def fetch_recently_played(sp, limit=50, show_progress=True, cache_key="recently_played", cache_expiration=None):
    """
    Fetch recently played tracks with caching.
    
    Args:
        sp: Spotify client
        limit: Maximum number of tracks to fetch (max 50 per API call)
        show_progress: Whether to show progress info
        cache_key: Cache key for storing results
        cache_expiration: Cache expiration in seconds
    
    Returns:
        List of recently played track objects
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('short', 60 * 60)  # 1 hour for recent data
    
    # Try cache first
    cached_data = load_from_cache(cache_key, cache_expiration)
    if cached_data:
        if show_progress:
            print_info(f"Found {len(cached_data)} recently played tracks (from cache)")
        return cached_data
    
    if show_progress:
        print_info("Fetching recently played tracks...")
    
    # Note: Spotify API only returns max 50 items for recently played
    # To get more, we need multiple calls with different time windows
    all_tracks = []
    
    # Fetch in chunks to get more data
    limit_per_call = min(50, limit)
    calls_needed = max(1, limit // 50)
    
    for i in range(calls_needed):
        try:
            results = sp.current_user_recently_played(limit=limit_per_call, before=None)
            tracks = results.get('items', [])
            
            if not tracks:
                break
                
            all_tracks.extend(tracks)
            
            if len(tracks) < limit_per_call:
                break  # No more tracks available
                
            time.sleep(0.2)  # Rate limiting between calls
            
        except Exception as e:
            print_warning(f"Error fetching recently played tracks: {e}")
            break
    
    # Remove duplicates by track ID and timestamp
    seen = set()
    unique_tracks = []
    for track in all_tracks:
        key = (track['track']['id'], track['played_at'])
        if key not in seen:
            seen.add(key)
            unique_tracks.append(track)
    
    if show_progress:
        print_success(f"Found {len(unique_tracks)} recently played tracks")
    
    # Cache results
    save_to_cache(unique_tracks, cache_key)
    return unique_tracks

def fetch_user_top_items(sp, item_type='artists', time_range='medium_term', limit=50, show_progress=True, cache_key=None, cache_expiration=None):
    """
    Fetch user's top artists or tracks with caching.
    
    Args:
        sp: Spotify client
        item_type: 'artists' or 'tracks'
        time_range: 'short_term', 'medium_term', or 'long_term'
        limit: Number of items to fetch (max 50)
        show_progress: Whether to show progress info
        cache_key: Cache key for storing results
        cache_expiration: Cache expiration in seconds
    
    Returns:
        List of top artist or track objects
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('personal', 3 * 24 * 60 * 60)
    
    if cache_key is None:
        cache_key = f"top_{item_type}_{time_range}"
    
    # Try cache first
    cached_data = load_from_cache(cache_key, cache_expiration)
    if cached_data:
        if show_progress:
            print_info(f"Found {len(cached_data)} top {item_type} ({time_range}) from cache")
        return cached_data
    
    if show_progress:
        print_info(f"Fetching top {item_type} ({time_range})...")
    
    try:
        if item_type == 'artists':
            results = sp.current_user_top_artists(limit=limit, time_range=time_range)
        elif item_type == 'tracks':
            results = sp.current_user_top_tracks(limit=limit, time_range=time_range)
        else:
            raise ValueError(f"Invalid item_type: {item_type}. Must be 'artists' or 'tracks'")
        
        items = results.get('items', [])
        
        if show_progress:
            print_success(f"Found {len(items)} top {item_type}")
        
        # Cache results
        save_to_cache(items, cache_key)
        return items
        
    except Exception as e:
        print_warning(f"Error fetching top {item_type}: {e}")
        return []

def extract_artists_from_playlists(playlists, sp, show_progress=True, owner_filter=None):
    """
    Extract unique artists from a list of playlists with progress tracking.
    
    Args:
        playlists: List of playlist objects
        sp: Spotify client
        show_progress: Whether to show progress bar
        owner_filter: Only process playlists owned by this user (None = current user)
    
    Returns:
        List of unique artist objects with metadata
    """
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    if owner_filter is None:
        user_profile = sp.current_user()
        owner_filter = user_profile['id']
    
    # Filter playlists by owner
    user_playlists = [p for p in playlists if p['owner']['id'] == owner_filter]
    
    if show_progress:
        print_info(f"Extracting artists from {len(user_playlists)} playlists...")
        progress_bar = create_progress_bar(total=len(user_playlists), desc="Processing playlists", unit="playlist")
    
    all_artists = {}  # Use dict to automatically handle duplicates
    
    for playlist in user_playlists:
        try:
            # Fetch tracks for this playlist
            tracks = fetch_playlist_tracks(sp, playlist['id'], show_progress=False)
            
            # Extract artists from tracks
            for item in tracks:
                if item and item.get('track') and item['track'].get('artists'):
                    for artist in item['track']['artists']:
                        if artist['id'] not in all_artists:
                            all_artists[artist['id']] = artist
            
            if show_progress:
                update_progress_bar(progress_bar, 1)
                
        except Exception as e:
            print_warning(f"Error processing playlist {playlist.get('name', 'Unknown')}: {e}")
            if show_progress:
                update_progress_bar(progress_bar, 1)
            continue
    
    if show_progress:
        close_progress_bar(progress_bar)
        print_success(f"Found {len(all_artists)} unique artists across all playlists")
    
    return list(all_artists.values())

if __name__ == "__main__":
    print("Spotify Utils Test")
    print("This module provides shared utilities for Spotify API operations.")