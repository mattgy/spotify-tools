#!/usr/bin/env python3
"""
Shared utilities for Spotify API operations across the project.
Includes rate limiting, error handling, and common patterns.
"""

import time
import functools
import logging
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from colorama import Fore

# Import centralized print functions (prevents circular imports)
from print_utils import print_success, print_error, print_warning, print_info, print_header

# Import centralized constants
from constants import CACHE_EXPIRATION, SPOTIFY_SCOPES, RATE_LIMITS

# Initialize logger
logger = logging.getLogger(__name__)

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
                        # Try to extract retry time from error message
                        retry_time = None
                        try:
                            # Look for "retry after X" pattern in error message
                            import re
                            retry_match = re.search(r'retry[^0-9]*(\d+)', error_str)
                            if retry_match:
                                retry_time = int(retry_match.group(1))
                            elif hasattr(e, 'headers') and 'retry-after' in e.headers:
                                retry_time = int(e.headers['retry-after'])
                        except (ValueError, AttributeError):
                            pass
                        
                        if retry_time:
                            print(f"{Fore.YELLOW}⚠️  Rate limit hit. Waiting {retry_time} seconds (from API)...")
                            time.sleep(retry_time)
                        else:
                            print(f"{Fore.YELLOW}⚠️  Rate limit hit. Waiting {retry_delay} seconds...")
                            time.sleep(retry_delay)
                        
                        retry_delay *= 2  # Exponential backoff for next attempt
                    else:
                        print(f"{Fore.RED}❌ Rate limiting persists after {max_retries} attempts.")
                        raise
                # Note: Audio Features API deprecated by Spotify in 2024
                # Removed special handling for audio-features errors
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
                # Add small delay between calls (0.05s = 20 req/s)
                time.sleep(0.05)
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
            # Add delay between pages (0.05s = 20 req/s)
            time.sleep(0.05)
            results = api_call._sp.next(results)
        elif 'artists' in results and results['artists'].get('next'):
            # Handle followed artists pagination (0.05s = 20 req/s)
            time.sleep(0.05)
            results = api_call._sp.next(results['artists'])
        else:
            break

def batch_process_items(items, batch_size, process_func, delay_between_batches=0.3):
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
            time.sleep(0.05)  # Rate limiting (20 req/s)
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
            time.sleep(0.05)  # Rate limiting (20 req/s)
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
            time.sleep(0.05)  # Rate limiting (20 req/s)
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
            time.sleep(0.05)  # Rate limiting (20 req/s)
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

# Alias for backward compatibility
def fetch_liked_songs(sp, show_progress=True, cache_key="liked_songs", cache_expiration=None):
    """Alias for fetch_user_saved_tracks with consistent naming."""
    return fetch_user_saved_tracks(sp, show_progress, cache_key, cache_expiration)

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
    
    # Filter playlists by owner (with cache corruption protection)
    user_playlists = []
    for p in playlists:
        # Handle cache corruption where playlist might be a string instead of dict
        if isinstance(p, str):
            print_warning(f"Skipping corrupted playlist data: {p}")
            continue
        if isinstance(p, dict) and p.get('owner', {}).get('id') == owner_filter:
            user_playlists.append(p)
    
    if show_progress:
        print_info(f"Extracting artists from {len(user_playlists)} playlists...")
        progress_bar = create_progress_bar(total=len(user_playlists), desc="Processing playlists", unit="playlist")
    
    all_artists = {}  # Use dict to automatically handle duplicates
    
    for playlist in user_playlists:
        try:
            # Handle cache corruption where playlist might be a string instead of dict
            if isinstance(playlist, str):
                print_warning(f"Detected corrupted playlist data: {playlist}")
                print_warning("Cache corruption detected. Please clear caches and try again.")
                if show_progress:
                    update_progress_bar(progress_bar, 1)
                continue
            
            if not isinstance(playlist, dict) or 'id' not in playlist:
                print_warning(f"Invalid playlist data: {playlist}")
                if show_progress:
                    update_progress_bar(progress_bar, 1)
                continue
            
            # Fetch tracks for this playlist
            tracks = fetch_playlist_tracks(sp, playlist['id'], show_progress=False)
            
            # Extract artists from tracks
            for item in tracks:
                if item and item.get('track') and item['track'].get('artists'):
                    for artist in item['track']['artists']:
                        # Handle cache corruption where artist might be a string instead of dict
                        if isinstance(artist, str):
                            print_warning(f"Detected corrupted artist data in playlist {playlist.get('name', 'Unknown')}: {artist}")
                            continue
                        
                        if not isinstance(artist, dict) or 'id' not in artist:
                            print_warning(f"Invalid artist data in playlist {playlist.get('name', 'Unknown')}: {artist}")
                            continue
                            
                        if artist['id'] not in all_artists:
                            all_artists[artist['id']] = artist
            
            if show_progress:
                update_progress_bar(progress_bar, 1)
                
        except Exception as e:
            playlist_name = playlist.get('name', 'Unknown') if isinstance(playlist, dict) else str(playlist)
            print_warning(f"Error processing playlist {playlist_name}: {e}")
            if show_progress:
                update_progress_bar(progress_bar, 1)
            continue
    
    if show_progress:
        close_progress_bar(progress_bar)
        print_success(f"Found {len(all_artists)} unique artists across all playlists")
    
    return list(all_artists.values())

def batch_get_artist_details(sp, artist_ids, show_progress=True, cache_key_prefix="artist_details", cache_expiration=None):
    """
    Get detailed information for multiple artists efficiently using Spotify's bulk endpoint.
    
    Args:
        sp: Spotify client
        artist_ids: List of artist IDs (max 50 per API call)
        show_progress: Whether to show progress bar
        cache_key_prefix: Prefix for cache keys
        cache_expiration: Cache expiration in seconds
    
    Returns:
        Dictionary mapping artist IDs to artist detail objects
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('long', 7 * 24 * 60 * 60)  # 7 days for artist data
    
    # Check cache for each artist
    cached_artists = {}
    uncached_ids = []
    
    for artist_id in artist_ids:
        cache_key = f"{cache_key_prefix}_{artist_id}"
        cached_data = load_from_cache(cache_key, cache_expiration)
        if cached_data:
            cached_artists[artist_id] = cached_data
        else:
            uncached_ids.append(artist_id)
    
    if show_progress and uncached_ids:
        print_info(f"Fetching details for {len(uncached_ids)} artists ({len(cached_artists)} from cache)")
        progress_bar = create_progress_bar(total=len(uncached_ids), desc="Fetching artist details", unit="artist")
    
    # Fetch uncached artists in batches of 50 (Spotify API limit)
    batch_size = 50
    fetched_artists = {}
    
    for i in range(0, len(uncached_ids), batch_size):
        batch_ids = uncached_ids[i:i + batch_size]
        
        try:
            # Use Spotify's bulk artists endpoint
            artists_data = sp.artists(batch_ids)
            
            for artist in artists_data.get('artists', []):
                if artist:  # Skip None artists (deleted/unavailable)
                    artist_id = artist['id']
                    fetched_artists[artist_id] = artist
                    
                    # Cache individual artist
                    cache_key = f"{cache_key_prefix}_{artist_id}"
                    save_to_cache(artist, cache_key)
            
            if show_progress and uncached_ids:
                update_progress_bar(progress_bar, len(batch_ids))
            
            time.sleep(0.05)  # Rate limiting (20 req/s)
            
        except Exception as e:
            print_warning(f"Error fetching artist batch: {e}")
            if show_progress and uncached_ids:
                update_progress_bar(progress_bar, len(batch_ids))
    
    if show_progress and uncached_ids:
        close_progress_bar(progress_bar)
    
    # Combine cached and fetched results
    all_artists = {**cached_artists, **fetched_artists}
    
    if show_progress:
        print_success(f"Retrieved details for {len(all_artists)} artists")
    
    return all_artists

def batch_search_tracks(sp, search_queries, show_progress=True, cache_key_prefix="track_search", cache_expiration=None):
    """
    Perform multiple track searches efficiently with caching and rate limiting.
    
    Args:
        sp: Spotify client
        search_queries: List of search query strings
        show_progress: Whether to show progress bar
        cache_key_prefix: Prefix for cache keys
        cache_expiration: Cache expiration in seconds
    
    Returns:
        Dictionary mapping queries to search results
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('short', 60 * 60)  # 1 hour for search results
    
    # Check cache for each query
    cached_results = {}
    uncached_queries = []
    
    for query in search_queries:
        # Create safe cache key
        import hashlib
        safe_query = hashlib.md5(query.encode()).hexdigest()[:16]
        cache_key = f"{cache_key_prefix}_{safe_query}"
        
        cached_data = load_from_cache(cache_key, cache_expiration)
        if cached_data:
            cached_results[query] = cached_data
        else:
            uncached_queries.append(query)
    
    if show_progress and uncached_queries:
        print_info(f"Performing {len(uncached_queries)} track searches ({len(cached_results)} from cache)")
        progress_bar = create_progress_bar(total=len(uncached_queries), desc="Searching tracks", unit="search")
    
    # Perform uncached searches
    search_results = {}
    
    for query in uncached_queries:
        try:
            # Use higher limit for better results per call
            results = sp.search(q=query, type='track', limit=50)
            search_results[query] = results
            
            # Cache result
            import hashlib
            safe_query = hashlib.md5(query.encode()).hexdigest()[:16]
            cache_key = f"{cache_key_prefix}_{safe_query}"
            save_to_cache(results, cache_key)
            
            if show_progress:
                update_progress_bar(progress_bar, 1)
            
            time.sleep(0.05)  # Rate limiting (20 req/s)
            
        except Exception as e:
            print_warning(f"Error searching for '{query[:50]}...': {e}")
            search_results[query] = {'tracks': {'items': []}}
            if show_progress:
                update_progress_bar(progress_bar, 1)
    
    if show_progress and uncached_queries:
        close_progress_bar(progress_bar)
    
    # Combine cached and fresh results
    all_results = {**cached_results, **search_results}
    
    return all_results

def get_playlist_artist_frequency(sp, playlist_ids, show_progress=True, cache_key="playlist_artist_frequency", cache_expiration=None):
    """
    Efficiently calculate artist frequency across multiple playlists with optimized caching.
    
    Args:
        sp: Spotify client
        playlist_ids: List of playlist IDs to analyze
        show_progress: Whether to show progress bar
        cache_key: Cache key for storing results
        cache_expiration: Cache expiration in seconds
    
    Returns:
        Dictionary mapping artist IDs to frequency counts and playlist appearances
    """
    from cache_utils import save_to_cache, load_from_cache
    from constants import CACHE_EXPIRATION
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
    from collections import defaultdict
    
    if cache_expiration is None:
        cache_expiration = CACHE_EXPIRATION.get('medium', 24 * 60 * 60)  # 24 hours
    
    # Try cache first
    cached_data = load_from_cache(cache_key, cache_expiration)
    if cached_data:
        if show_progress:
            print_info("Using cached artist frequency data")
        return cached_data
    
    if show_progress:
        print_info(f"Analyzing artist frequency across {len(playlist_ids)} playlists...")
        progress_bar = create_progress_bar(total=len(playlist_ids), desc="Analyzing playlists", unit="playlist")
    
    artist_frequency = defaultdict(lambda: {'count': 0, 'playlists': []})
    
    for playlist_id in playlist_ids:
        try:
            # Use centralized function for fetching tracks
            tracks = fetch_playlist_tracks(
                sp, 
                playlist_id, 
                show_progress=False,
                cache_key=f"playlist_tracks_{playlist_id}",
                cache_expiration=cache_expiration
            )
            
            # Track unique artists per playlist to avoid double-counting
            playlist_artists = set()
            
            for track_item in tracks:
                if track_item and track_item.get('track') and track_item['track'].get('artists'):
                    for artist in track_item['track']['artists']:
                        artist_id = artist.get('id')
                        if artist_id and artist_id not in playlist_artists:
                            playlist_artists.add(artist_id)
                            artist_frequency[artist_id]['count'] += 1
                            artist_frequency[artist_id]['playlists'].append(playlist_id)
            
            if show_progress:
                update_progress_bar(progress_bar, 1)
                
        except Exception as e:
            print_warning(f"Error processing playlist {playlist_id}: {e}")
            if show_progress:
                update_progress_bar(progress_bar, 1)
            continue
    
    if show_progress:
        close_progress_bar(progress_bar)
        print_success(f"Analyzed {len(artist_frequency)} unique artists across all playlists")
    
    # Convert to regular dict for caching
    result = dict(artist_frequency)
    
    # Cache results
    save_to_cache(result, cache_key)
    
    return result

def strip_remix_tags(title):
    """
    Strip remix/version tags from a track title to get the original version name.

    Args:
        title: Track title potentially containing remix tags

    Returns:
        Cleaned title without remix tags
    """
    import re

    if not title:
        return title

    # Patterns to remove (in order of specificity)
    remix_patterns = [
        # Match parenthetical or bracketed remix info
        r'\s*[\[\(].*?(?:remix|rmx|mix|edit|rework|bootleg|mashup|version|vip|dub).*?[\]\)]',
        # Match trailing remix info
        r'\s+[–-]\s+.*?(?:remix|rmx|mix|edit|rework|bootleg|mashup|version|vip|dub).*?$',
        # Match leading remix info
        r'^.*?(?:remix|rmx|mix|edit|rework|bootleg|mashup|version|vip|dub)\s+[–-]\s+',
    ]

    cleaned = title
    for pattern in remix_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Clean up extra whitespace and punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\s+[–-]\s*$', '', cleaned)  # Remove trailing dash
    cleaned = re.sub(r'^\s*[–-]\s+', '', cleaned)  # Remove leading dash

    return cleaned if cleaned else title  # Return original if cleaning resulted in empty string

def is_karaoke_track(track_name, artist_name, album_name):
    """
    Detect if a track is likely a karaoke, backing track, or tribute version.

    Args:
        track_name: Track title
        artist_name: Artist name
        album_name: Album name

    Returns:
        True if track appears to be karaoke/backing track/tribute
    """
    # Normalize to lowercase for case-insensitive matching
    track_lower = track_name.lower() if track_name else ""
    artist_lower = artist_name.lower() if artist_name else ""
    album_lower = album_name.lower() if album_name else ""

    # Karaoke/backing track indicators in album names
    karaoke_album_indicators = [
        "karaoke", "backing track", "instrumental", "tribute",
        "in the style of", "sound-alike", "cover", "re-recorded",
        "originally performed by", "hits", "sing-along"
    ]

    # Karaoke/backing track indicators in track names
    karaoke_track_indicators = [
        "karaoke", "instrumental", "backing track", "sound-alike",
        "in the style of", "tribute", "cover version"
    ]

    # Karaoke/backing track artist indicators
    karaoke_artist_indicators = [
        "karaoke", "backing track", "tribute", "sound-alike",
        "originally performed", "cover"
    ]

    # Check album name for karaoke indicators
    for indicator in karaoke_album_indicators:
        if indicator in album_lower:
            logger.debug(f"Karaoke detected (album): '{track_name}' from '{album_name}' (indicator: '{indicator}')")
            return True

    # Check track name for karaoke indicators
    for indicator in karaoke_track_indicators:
        if indicator in track_lower:
            logger.debug(f"Karaoke detected (track): '{track_name}' (indicator: '{indicator}')")
            return True

    # Check artist name for karaoke indicators
    for indicator in karaoke_artist_indicators:
        if indicator in artist_lower:
            logger.debug(f"Karaoke detected (artist): '{track_name}' by '{artist_name}' (indicator: '{indicator}')")
            return True

    return False

def _get_strategy_name(query, idx):
    """Convert search query to human-readable strategy name."""
    # Parse the query to identify strategy type
    if 'artist:' in query and 'album:' in query and 'track:' in query:
        return "artist+album+track"
    elif 'album:' in query and 'track:' in query:
        return "album+track"
    elif 'artist:' in query and 'track:' in query:
        # Check if this is a swap strategy
        if query.count('artist:"') > 0 and query.count('track:"') > 0:
            # Extract values to detect swap
            parts = query.split('"')
            if len(parts) >= 4:
                artist_val = parts[1]
                track_val = parts[3]
                # This is a heuristic - swap strategies have unusual artist/track combos
                return "swap-search"
        return "artist+track"
    elif query.count('"') == 2 and ' ' in query.replace('"', ''):
        # Two quoted parts like "artist" "title"
        return "quoted-pair"
    elif query.count('"') == 1:
        # Single search term
        if 'track:' in query:
            return "track-only"
        elif 'artist:' in query:
            return "artist-only"
        else:
            # Combined "artist title" or title-only
            return "combined" if ' ' in query.replace('"', '') else "title-only"
    else:
        return f"strategy-{idx+1}"

def optimized_track_search_strategies(sp, artist, title, album=None, max_strategies=7):
    """
    Optimized track search using fewer, more effective strategies with higher limits.
    
    Args:
        sp: Spotify client
        artist: Artist name
        title: Track title
        album: Album name (optional)
        max_strategies: Maximum number of search strategies to try
    
    Returns:
        Best matching track or None
    """
    from cache_utils import save_to_cache, load_from_cache
    import hashlib
    
    # Create cache key
    cache_key = f"optimized_track_search_{hashlib.md5(f'{artist}_{title}_{album}'.encode()).hexdigest()[:16]}"
    cached_result = load_from_cache(cache_key, 7 * 24 * 60 * 60)  # 7 days

    # Handle corrupted cache entries gracefully
    if cached_result and isinstance(cached_result, dict):
        return cached_result
    
    # Optimized search strategies (fewer, more effective)
    # Ordered by specificity: most specific first
    strategies = []

    # Special handling for Various Artists compilations
    various_artists = artist and artist.lower() in ['various', 'various artists', 'va']

    if various_artists:
        # For compilations, prioritize album+track over artist
        if album and title:
            strategies.append(f'album:"{album}" track:"{title}"')
        if title:
            strategies.append(f'"{title}"')  # Title-only for unique tracks
    else:
        # Normal artist-based search
        if artist and album and title:
            strategies.append(f'artist:"{artist}" album:"{album}" track:"{title}"')

        # Album+track should come early when album is known
        if album and title:
            strategies.append(f'album:"{album}" track:"{title}"')

        if artist and title:
            strategies.append(f'artist:"{artist}" track:"{title}"')
            strategies.append(f'"{artist}" "{title}"')

    # Simple fallback
    if artist and title:
        strategies.append(f'"{artist} {title}"')

    # Title-only search for unique titles
    if title:
        strategies.append(f'"{title}"')

    # Artist name spacing variation - for cases like "Soap Kills" vs "Soapkills"
    if artist and title and ' ' in artist and not various_artists:
        artist_no_space = artist.replace(' ', '')
        strategies.append(f'artist:"{artist_no_space}" track:"{title}"')

    # Swap strategy - for cases where artist and title are reversed in metadata
    # Only try if artist doesn't contain ' - ' (prevents double-swapping issues)
    if artist and title and ' - ' not in artist and not various_artists:
        strategies.append(f'artist:"{title}" track:"{artist}"')

    # Limit to max_strategies
    strategies = strategies[:max_strategies]
    
    # Use batch search for all strategies
    search_results = batch_search_tracks(sp, strategies, show_progress=False, cache_expiration=60*60)

    # Find best match across all strategies using fuzzy matching
    from rapidfuzz import fuzz
    best_match = None
    best_score = 0
    best_strategy = None

    for idx, (strategy, results) in enumerate(search_results.items()):
        tracks = results.get('tracks', {}).get('items', [])

        for track in tracks:
            # Use consolidated scoring function for consistent results
            track_artists_str = ', '.join([a['name'] for a in track.get('artists', [])])
            track_name = track.get('name', '')
            track_album = track.get('album', {}).get('name', '') if track.get('album') else ''

            # Calculate match score using the consolidated function
            score = consolidated_track_score(
                search_artist=artist or "",
                search_title=title or "",
                result_artist=track_artists_str,
                result_title=track_name,
                result_album=track_album,
                search_album=album or ""
            )

            # Special handling for swap strategy results
            # If this came from swap strategy, verify the swap is actually correct
            swap_strategy = f'artist:"{title}" track:"{artist}"'
            if swap_strategy in strategy:
                # Check if artist/title are actually swapped in the result
                # The search had title as artist and artist as title
                # So we expect: result artist matches our title, result title matches our artist
                title_to_artist_score = fuzz.ratio(title.lower(), track_artists_str.lower())
                artist_to_title_score = fuzz.ratio(artist.lower(), track_name.lower())

                # Only accept if swap makes sense (high scores in both directions)
                if title_to_artist_score > 60 and artist_to_title_score > 60:
                    # Apply penalty for swapped metadata (significant data quality issue)
                    score = score * 0.85  # 15% penalty for swapped metadata
                    logger.debug(f"Detected swapped metadata: '{artist} - {title}' -> '{track_name}' by {track_artists_str} (swap validated)")
                else:
                    # Not actually a swap, skip this result
                    logger.debug(f"Swap strategy false positive, skipping: {track_name} by {track_artists_str}")
                    continue

            if score > best_score:
                best_score = score
                # Create human-readable strategy name for lineage tracking
                strategy_name = _get_strategy_name(strategy, idx)
                best_strategy = strategy_name
                best_match = {
                    'id': track['id'],
                    'name': track['name'],
                    'artists': [artist['name'] for artist in track['artists']],
                    'album': track['album']['name'] if track.get('album') else '',
                    'uri': track['uri'],
                    'score': score,
                    'strategy': strategy_name  # Track which strategy found this match
                }
    
    # Log which strategy found the match for debugging
    if best_match and best_strategy:
        logger.debug(f"Found match via strategy '{best_strategy}': {best_match['name']} by {', '.join(best_match['artists'])} (score: {best_score:.1f})")

    # Cache result
    save_to_cache(best_match, cache_key)

    return best_match

def consolidated_track_score(search_artist, search_title, result_artist, result_title, result_album="", search_album=""):
    """
    Consolidated track matching score with advanced fuzzy matching and comprehensive penalties.

    This function combines the best aspects of both previous scoring approaches:
    - Advanced distance metrics (token_set_ratio, Jaro-Winkler, partial_ratio)
    - Featuring artist extraction and matching
    - Remix/version mismatch penalties
    - Exact match bonuses
    - Phonetic fallback matching

    Weights: Artist 45%, Title 40%, Album 15%
    Score range: 0-100

    Args:
        search_artist: Artist name from search query
        search_title: Track title from search query
        result_artist: Artist name from Spotify result
        result_title: Track title from Spotify result
        result_album: Album name from Spotify result (optional)
        search_album: Album name from search query (optional)

    Returns:
        Float score 0-100 indicating match quality
    """
    from rapidfuzz import fuzz
    from rapidfuzz.distance import JaroWinkler
    import re

    # Helper function to extract featuring info
    def extract_featuring_info(text):
        feat_patterns = [
            r'\s+[\[\(](?:feat\.?|featuring|ft\.?)\s+([^\]\)]+)[\]\)]',
            r'\s+(?:feat\.?|featuring|ft\.?)\s+(.+?)(?:\s*[\[\(]|$)',
            r'\s+[\[\(](?:with|w\/)\s+([^\]\)]+)[\]\)]',
        ]
        main_text = text
        featuring = ""
        for pattern in feat_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                featuring = match.group(1).strip()
                main_text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
                break
        return main_text, featuring

    # Helper function to strip remaster tags
    def strip_remaster_tags(text):
        patterns = [
            r'\s*[\(\[].*?(?:remaster|anniversary|deluxe|expanded|edition).*?[\)\]]',
            r'\s*-\s*(?:remaster|anniversary|deluxe|expanded|edition).*$',
        ]
        clean = text
        for pattern in patterns:
            clean = re.sub(pattern, '', clean, flags=re.IGNORECASE)
        return clean.strip()

    # Extract featuring info
    search_artist_main, search_artist_feat = extract_featuring_info(search_artist)
    search_title_main, search_title_feat = extract_featuring_info(search_title)
    result_artist_main, result_artist_feat = extract_featuring_info(result_artist)
    result_title_main, result_title_feat = extract_featuring_info(result_title)

    # Strip remaster tags
    search_title_clean = strip_remaster_tags(search_title_main)
    result_title_clean = strip_remaster_tags(result_title_main)

    # Normalize for comparison (lowercase, remove extra spaces)
    norm_search_artist = search_artist_main.lower().strip()
    norm_search_title = search_title_clean.lower().strip()
    norm_result_artist = result_artist_main.lower().strip()
    norm_result_title = result_title_clean.lower().strip()
    norm_search_album = search_album.lower().strip() if search_album else ""
    norm_result_album = result_album.lower().strip() if result_album else ""

    # === ARTIST MATCHING (45% weight) ===
    # Use multiple distance metrics and take the best
    artist_scores = []

    if norm_search_artist and norm_result_artist:
        # Exact ratio (good for similar strings)
        artist_scores.append(fuzz.ratio(norm_search_artist, norm_result_artist))

        # Token set ratio (handles word order, extra words)
        artist_scores.append(fuzz.token_set_ratio(norm_search_artist, norm_result_artist))

        # Partial ratio (handles substrings)
        artist_scores.append(fuzz.partial_ratio(norm_search_artist, norm_result_artist))

        # Jaro-Winkler (better for names with typos, favors matching prefixes)
        jw_score = JaroWinkler.normalized_similarity(norm_search_artist, norm_result_artist) * 100
        artist_scores.append(jw_score)

    artist_score = max(artist_scores) if artist_scores else 0

    # === TITLE MATCHING (40% weight) ===
    title_scores = []

    if norm_search_title and norm_result_title:
        # Exact ratio
        title_scores.append(fuzz.ratio(norm_search_title, norm_result_title))

        # Token set ratio (very important for titles with extra info)
        title_scores.append(fuzz.token_set_ratio(norm_search_title, norm_result_title))

        # Partial ratio
        title_scores.append(fuzz.partial_ratio(norm_search_title, norm_result_title))

    title_score = max(title_scores) if title_scores else 0

    # === ALBUM MATCHING (15% weight) ===
    album_score = 0
    if norm_search_album and norm_result_album:
        album_scores = [
            fuzz.ratio(norm_search_album, norm_result_album),
            fuzz.token_set_ratio(norm_search_album, norm_result_album),
            fuzz.partial_ratio(norm_search_album, norm_result_album)
        ]
        album_score = max(album_scores)
    elif norm_search_album or norm_result_album:
        # Partial credit when only one side has album info
        # This helps when metadata is incomplete on one side
        if norm_search_album:
            album_score = 40  # Partial credit for search having album
        else:
            album_score = 30  # Partial credit for result having album

    # === BONUSES ===
    bonus = 0

    # Exact match bonus (+20 points)
    if (norm_search_artist == norm_result_artist and
        norm_search_title == norm_result_title):
        bonus += 20

    # Featuring artist match bonus
    if search_artist_feat and result_artist_feat:
        feat_score = fuzz.ratio(search_artist_feat.lower(), result_artist_feat.lower())
        if feat_score > 70:
            bonus += 10

    # Stronger substring match bonuses (length-weighted)
    # Title substring matching
    if norm_search_title in norm_result_title:
        # Our search title is contained in result
        length_ratio = len(norm_search_title) / len(norm_result_title) if norm_result_title else 0
        bonus += 15 if length_ratio > 0.7 else 10
    elif norm_result_title in norm_search_title:
        bonus += 10

    # Artist substring matching
    if norm_search_artist in norm_result_artist:
        length_ratio = len(norm_search_artist) / len(norm_result_artist) if norm_result_artist else 0
        bonus += 12 if length_ratio > 0.7 else 8
    elif norm_result_artist in norm_search_artist:
        bonus += 8

    # === PENALTIES ===
    penalty = 0

    # Smarter remix mismatch penalty
    remix_keywords = ['remix', 'rmx', 'mix', 'dub', 'vip', 'bootleg', 'mashup']
    version_keywords_soft = ['radio edit', 'extended mix', 'version']

    search_is_remix = any(kw in search_title.lower() for kw in remix_keywords)
    result_is_remix = any(kw in result_title.lower() for kw in remix_keywords)

    if search_is_remix != result_is_remix:
        # Check if both are just version variants (less severe)
        search_has_version = any(kw in search_title.lower() for kw in version_keywords_soft)
        result_has_version = any(kw in result_title.lower() for kw in version_keywords_soft)

        if search_has_version or result_has_version:
            penalty += 20  # Lighter penalty for version mismatches
        else:
            penalty += 40  # Heavier penalty for remix mismatches

    # Version-aware mismatch penalty
    version_categories = {
        'major': ['live', 'acoustic'],           # Major version changes
        'minor': ['demo', 'alternate'],          # Minor variations
        'edit': ['radio edit', 'unplugged']      # Edit variants
    }

    def get_version_type(title):
        for vtype, keywords in version_categories.items():
            if any(kw in title.lower() for kw in keywords):
                return vtype
        return None

    search_version = get_version_type(search_title)
    result_version = get_version_type(result_title)

    if search_version != result_version and (search_version or result_version):
        if search_version in ['major', None] or result_version in ['major', None]:
            penalty += 30  # Major mismatch (live vs studio)
        else:
            penalty += 15  # Minor mismatch (demo vs alternate)

    # Karaoke/backing track penalty (-80, very heavy to filter out karaoke versions)
    if is_karaoke_track(result_title, result_artist, result_album):
        penalty += 80
        logger.debug(f"Applied karaoke penalty to: '{result_title}' by {result_artist} from '{result_album}'")

    # Different primary artist penalty (-30, major issue)
    if artist_score < 50:  # Very different artists
        penalty += 30

    # Calculate weighted composite score with dynamic normalization
    # Don't waste weight on missing components - redistribute to available data
    weights = {'artist': 0.45, 'title': 0.40, 'album': 0.15}
    available_weight = 0

    # Calculate total available weight
    if artist_score > 0:
        available_weight += weights['artist']
    if title_score > 0:
        available_weight += weights['title']
    if album_score > 0:
        available_weight += weights['album']

    # Normalize weights based on available components
    if available_weight > 0:
        artist_weight = (weights['artist'] / available_weight) if artist_score > 0 else 0
        title_weight = (weights['title'] / available_weight) if title_score > 0 else 0
        album_weight = (weights['album'] / available_weight) if album_score > 0 else 0
    else:
        # No valid components
        artist_weight = title_weight = album_weight = 0

    base_score = (artist_score * artist_weight) + (title_score * title_weight) + (album_score * album_weight)
    final_score = base_score + bonus - penalty

    # Clamp to 0-100 range
    return max(0, min(100, final_score))

if __name__ == "__main__":
    print("Spotify Utils Test")
    print("This module provides shared utilities for Spotify API operations.")