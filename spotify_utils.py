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

if __name__ == "__main__":
    print("Spotify Utils Test")
    print("This module provides shared utilities for Spotify API operations.")