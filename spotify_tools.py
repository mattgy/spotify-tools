#!/usr/bin/env python3
"""
Main script for Matt Y's Spotify Tools.
This script provides a menu to access all the Spotify utilities.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import subprocess
import time
import datetime
from pathlib import Path
import json
import shutil
import importlib.util

# Simple import check - let imports fail naturally if packages are missing
# This avoids the infinite loop issue

# Now import the required packages
import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform color support
colorama.init(autoreset=True)

# Get the directory of this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define paths to other scripts
FOLLOW_ARTISTS_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_follow_artists.py")
LIKE_SONGS_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_like_songs.py")
SIMILAR_ARTISTS_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_similar_artists.py")
ANALYTICS_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_analytics.py")
PLAYLIST_CONVERTER_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_playlist_converter.py")
CLEANUP_ARTISTS_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_cleanup_artists.py")
BACKUP_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_backup.py")
CHRISTMAS_CLEANUP_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_remove_christmas.py")
PLAYLIST_MANAGER_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_playlist_manager.py")
REMOVE_DUPLICATES_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_remove_duplicates.py")
IDENTIFY_SKIPPED_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_identify_skipped.py")
INSTALL_DEPENDENCIES_SCRIPT = os.path.join(SCRIPT_DIR, "install_dependencies.py")

# Define config directory
CONFIG_DIR = os.path.join(str(Path.home()), ".spotify-tools")
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, "credentials.json")
CACHE_DIR = os.path.join(CONFIG_DIR, "cache")

# Default cache age in days
DEFAULT_MAX_CACHE_AGE = 7

# Import print functions from spotify_utils
from spotify_utils import print_header, print_success, print_error, print_warning, print_info

def run_script(script_path, args=None):
    """Run a Python script with optional arguments."""
    if not os.path.exists(script_path):
        print_error(f"Error: Could not find script at {script_path}")
        return False
    
    cmd = [sys.executable, script_path]
    if args:
        cmd.extend(args)
    
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Error running script: {e}")
        return False
    except KeyboardInterrupt:
        print_warning("\nScript execution cancelled.")
        return False

def setup_virtual_environment():
    """Set up a virtual environment if it doesn't exist."""
    # Skip if we're being called from spotify_run.py which already set up the environment
    if os.environ.get("SPOTIFY_TOOLS_INITIALIZED"):
        return
        
    venv_dir = os.path.join(SCRIPT_DIR, "venv")
    
    # Check if virtual environment exists
    if not os.path.exists(venv_dir):
        print_info("Setting up virtual environment...")
        try:
            # Create virtual environment
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
            
            # Install dependencies
            check_and_update_dependencies()
            
            print_success("Virtual environment set up successfully.")
        except subprocess.CalledProcessError as e:
            print_error(f"Error setting up virtual environment: {e}")
            sys.exit(1)

def check_and_update_dependencies():
    """Check and update dependencies."""
    # Run the install dependencies script
    run_script(INSTALL_DEPENDENCIES_SCRIPT)

def setup_config_directory():
    """Set up the config directory."""
    # Create config directory if it doesn't exist
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # Create cache directory if it doesn't exist
    os.makedirs(CACHE_DIR, exist_ok=True)

def export_credentials_to_env():
    """Export credentials to environment variables."""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                credentials = json.load(f)
            
            # Export credentials to environment variables
            for key, value in credentials.items():
                os.environ[key] = value
        except Exception as e:
            print_warning(f"Warning: Could not load credentials: {e}")

def manage_api_credentials():
    """Manage API credentials."""
    print_header("API Credential Management")
    
    # Create config directory if it doesn't exist
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # Load existing credentials if available
    existing_credentials = {}
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                existing_credentials = json.load(f)
        except Exception as e:
            print_warning(f"Warning: Could not load existing credentials: {e}")
    
    # Spotify credentials
    print_info("\nSpotify API Credentials")
    print("To get your Spotify API credentials:")
    print("1. Go to https://developer.spotify.com/dashboard/")
    print("2. Log in and create a new application")
    print("3. Set the redirect URI to http://127.0.0.1:8888/callback")
    print("4. Copy the Client ID and Client Secret")
    
    spotify_client_id = input(f"Enter Spotify Client ID [{existing_credentials.get('SPOTIFY_CLIENT_ID', '')}]: ").strip()
    if not spotify_client_id and 'SPOTIFY_CLIENT_ID' in existing_credentials:
        spotify_client_id = existing_credentials['SPOTIFY_CLIENT_ID']
    
    spotify_client_secret = input(f"Enter Spotify Client Secret [{existing_credentials.get('SPOTIFY_CLIENT_SECRET', '')}]: ").strip()
    if not spotify_client_secret and 'SPOTIFY_CLIENT_SECRET' in existing_credentials:
        spotify_client_secret = existing_credentials['SPOTIFY_CLIENT_SECRET']
    
    spotify_redirect_uri = input(f"Enter Spotify Redirect URI [{existing_credentials.get('SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')}]: ").strip()
    if not spotify_redirect_uri:
        spotify_redirect_uri = existing_credentials.get('SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')
    
    # Last.fm credentials
    print_info("\nLast.fm API Credentials")
    print("To get your Last.fm API key:")
    print("1. Go to https://www.last.fm/api/account/create")
    print("2. Fill out the form and submit")
    print("3. Copy the API key")
    
    lastfm_api_key = input(f"Enter Last.fm API Key [{existing_credentials.get('LASTFM_API_KEY', '')}]: ").strip()
    if not lastfm_api_key and 'LASTFM_API_KEY' in existing_credentials:
        lastfm_api_key = existing_credentials['LASTFM_API_KEY']
    
    # Songkick credentials
    print_info("\nNote: Songkick API is no longer freely available.")
    print("The concert finder now uses web scraping instead of the Songkick API.")
    print("You can leave this field empty.")
    
    # Save credentials
    credentials = {
        "SPOTIFY_CLIENT_ID": spotify_client_id,
        "SPOTIFY_CLIENT_SECRET": spotify_client_secret,
        "SPOTIFY_REDIRECT_URI": spotify_redirect_uri,
        "LASTFM_API_KEY": lastfm_api_key
    }
    
    try:
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(credentials, f, indent=2)
        
        print_success("\nCredentials saved successfully.")
        
        # Export credentials to environment variables
        for key, value in credentials.items():
            os.environ[key] = value
    except Exception as e:
        print_error(f"Error saving credentials: {e}")

def reset_environment():
    """Reset the environment by reinstalling dependencies."""
    print_header("Resetting Environment")
    
    # Confirm with user
    confirm = input("This will reinstall all dependencies. Continue? (y/n): ").strip().lower()
    if confirm != "y":
        print_warning("Reset cancelled.")
        return
    
    try:
        print_info("Resetting virtual environment...")
        
        # Run the reset script directly
        reset_script = os.path.join(SCRIPT_DIR, "reset.py")
        if os.path.exists(reset_script):
            # Find system Python
            import shutil
            system_python = shutil.which("python3")
            if not system_python:
                system_python = shutil.which("python")
            
            if system_python:
                print_info(f"Running reset using {system_python}...")
                result = subprocess.run([system_python, reset_script], 
                                      capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    print_success("Environment reset successfully!")
                    print_info("Please restart the application: ./spotify_run.py")
                    input("Press Enter to exit...")
                    sys.exit(0)
                else:
                    print_error(f"Reset failed: {result.stderr}")
                    print_info("You can manually run: python3 reset.py")
            else:
                print_error("Could not find system Python.")
                print_info("Please manually run: python3 reset.py")
        else:
            print_error("Reset script not found.")
            print_info("Please reinstall dependencies manually.")
            
    except subprocess.TimeoutExpired:
        print_error("Reset timed out. Please run manually: python3 reset.py")
    except Exception as e:
        print_error(f"Error during reset: {e}")
        print_info("Please manually run: python3 reset.py")

def manage_caches():
    """Manage cache files."""
    print_header("Cache Management")
    
    # Import cache utilities
    sys.path.insert(0, SCRIPT_DIR)
    from cache_utils import list_caches, clear_cache, get_cache_info
    
    # Get cache info
    info = get_cache_info()
    
    print(f"Total cache files: {info['count']}")
    print(f"Total size: {info['total_size'] / 1024:.1f} KB")
    
    if info['oldest']:
        print(f"Oldest cache: {info['oldest']['name']} ({time.ctime(info['oldest']['mtime'])})")
    
    if info['newest']:
        print(f"Newest cache: {info['newest']['name']} ({time.ctime(info['newest']['mtime'])})")
    
    # Group caches by type
    caches = list_caches()
    cache_types = {}
    
    for cache in caches:
        # Extract cache type from name (e.g., "artist_info_123" -> "artist_info")
        parts = cache['name'].split('_')
        if len(parts) > 1:
            cache_type = '_'.join(parts[:-1]) if parts[-1].isdigit() else parts[0]
        else:
            cache_type = "other"
        
        if cache_type not in cache_types:
            cache_types[cache_type] = []
        
        cache_types[cache_type].append(cache)
    
    # Print summary by type
    if cache_types:
        print("\nCache summary by type:")
        for cache_type, type_caches in sorted(cache_types.items()):
            total_size = sum(c['size'] for c in type_caches)
            oldest = min(type_caches, key=lambda c: c['mtime'])
            newest = max(type_caches, key=lambda c: c['mtime'])
            
            oldest_age = (time.time() - oldest['mtime']) / (24 * 60 * 60)
            newest_age = (time.time() - newest['mtime']) / (24 * 60 * 60)
            
            print(f"{cache_type}: {len(type_caches)} files, {total_size / 1024:.1f} KB")
            print(f"  Oldest: {oldest_age:.1f} days old, Newest: {newest_age:.1f} days old")
    
    # Options
    print("\nOptions:")
    print("1. Clear all caches")
    print("2. Clear caches by type")
    print("3. Back to main menu")
    
    choice = input("\nEnter your choice (1-3): ")
    
    if choice == "1":
        # Clear all caches
        confirm = input("Are you sure you want to clear all caches? (y/n): ").strip().lower()
        if confirm == "y":
            clear_cache()
            print_success("All caches cleared.")
    elif choice == "2":
        # Clear caches by type
        if cache_types:
            print("\nCache types:")
            types_list = sorted(cache_types.keys())
            for i, cache_type in enumerate(types_list, 1):
                type_caches = cache_types[cache_type]
                total_size = sum(c['size'] for c in type_caches)
                print(f"{i}. {cache_type}: {len(type_caches)} files, {total_size / 1024:.1f} KB")
            
            type_num = input(f"\nEnter type number to clear (1-{len(types_list)}): ")
            try:
                type_num = int(type_num)
                if 1 <= type_num <= len(types_list):
                    cache_type = types_list[type_num - 1]
                    confirm = input(f"Are you sure you want to clear all {cache_type} caches? (y/n): ").strip().lower()
                    if confirm == "y":
                        for cache in cache_types[cache_type]:
                            clear_cache(cache['name'])
                        print_success(f"All {cache_type} caches cleared.")
                else:
                    print_error("Invalid type number.")
            except ValueError:
                print_error("Invalid input. Please enter a number.")
        else:
            print_warning("No caches to clear.")

def check_cache_age():
    """Check cache age and ask to clear old caches."""
    # Import cache utilities
    sys.path.insert(0, SCRIPT_DIR)
    from cache_utils import list_caches, clear_cache
    
    # Get cache config
    cache_config_file = os.path.join(CONFIG_DIR, "cache_config.json")
    cache_config = {
        "max_age_days": DEFAULT_MAX_CACHE_AGE,
        "last_check": 0
    }
    
    if os.path.exists(cache_config_file):
        try:
            with open(cache_config_file, "r") as f:
                cache_config.update(json.load(f))
        except Exception:
            pass
    
    # Check if we need to check cache age (once per day)
    current_time = time.time()
    if current_time - cache_config["last_check"] < 24 * 60 * 60:
        return
    
    # Update last check time
    cache_config["last_check"] = current_time
    
    # Save config
    try:
        os.makedirs(os.path.dirname(cache_config_file), exist_ok=True)
        with open(cache_config_file, "w") as f:
            json.dump(cache_config, f)
    except Exception:
        pass
    
    # List all caches
    caches = list_caches()
    
    # Check for old caches
    old_caches = []
    for cache in caches:
        cache_age = current_time - cache["mtime"]
        cache_age_days = cache_age / (24 * 60 * 60)
        
        if cache_age_days > cache_config["max_age_days"]:
            old_caches.append((cache["name"], cache_age_days))
    
    if old_caches:
        print_warning(f"Found {len(old_caches)} cache files older than {cache_config['max_age_days']} days:")
        for name, age in old_caches:
            print(f"- {name} ({age:.1f} days old)")
        
        # Ask to clear old caches
        choice = input("\nWould you like to clear these old caches? (y/n/a): ").strip().lower()
        
        if choice == "y":
            # Clear old caches
            for name, _ in old_caches:
                clear_cache(name)
            print_success("Old caches cleared.")
        elif choice == "a":
            # Ask for new max age
            try:
                new_max_age = int(input(f"Enter new maximum cache age in days [{cache_config['max_age_days']}]: ").strip() or cache_config["max_age_days"])
                if new_max_age > 0:
                    cache_config["max_age_days"] = new_max_age
                    
                    # Save config
                    with open(cache_config_file, "w") as f:
                        json.dump(cache_config, f)
                    
                    print_success(f"Maximum cache age updated to {new_max_age} days.")
                    
                    # Check again with new max age
                    old_caches = []
                    for cache in caches:
                        cache_age = current_time - cache["mtime"]
                        cache_age_days = cache_age / (24 * 60 * 60)
                        
                        if cache_age_days > cache_config["max_age_days"]:
                            old_caches.append((cache["name"], cache_age_days))
                    
                    if old_caches:
                        print_warning(f"Found {len(old_caches)} cache files older than {cache_config['max_age_days']} days:")
                        for name, age in old_caches:
                            print(f"- {name} ({age:.1f} days old)")
                        
                        # Ask to clear old caches
                        if input("\nWould you like to clear these old caches? (y/n): ").strip().lower() == "y":
                            # Clear old caches
                            for name, _ in old_caches:
                                clear_cache(name)
                            print_success("Old caches cleared.")
                else:
                    print_error("Invalid maximum age. Must be greater than 0.")
            except ValueError:
                print_error("Invalid input. Please enter a number.")

def main():
    """Main function to run the master script."""
    # Check cache age on startup
    check_cache_age()
    
    # Set up virtual environment (skip if already initialized)
    if not os.environ.get("SPOTIFY_TOOLS_INITIALIZED"):
        setup_virtual_environment()
    
    # Set up config directory
    setup_config_directory()
    
    # Export credentials to environment variables
    export_credentials_to_env()
    
    # Display menu
    while True:
        print_header("Matt Y's Spotify Tools")
        
        # Playlist Management
        print(f"{Fore.YELLOW}{Style.BRIGHT}PLAYLIST MANAGEMENT:")
        print(f"{Fore.WHITE}1. Convert local playlists to Spotify playlists")
        print(f"{Fore.WHITE}2. Add all songs from your created playlists to Liked Songs")
        print(f"{Fore.WHITE}3. Remove Christmas songs from Liked Songs")
        print(f"{Fore.WHITE}4. Remove duplicate songs from Liked Songs")
        print(f"{Fore.WHITE}5. Identify frequently skipped songs in your library")
        
        # Artist Management
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}ARTIST MANAGEMENT:")
        print(f"{Fore.WHITE}6. Follow all artists in your created playlists")
        print(f"{Fore.WHITE}7. Find Artists to Follow That You Probably Like")
        print(f"{Fore.WHITE}8. Remove followed artists that you probably don't like")
        
        # Analytics & Insights
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}ANALYTICS & INSIGHTS:")
        print(f"{Fore.WHITE}9. Enhanced analytics & music insights")
        print(f"{Fore.WHITE}10. Backup & export your music library")
        
        # System Management
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}SYSTEM MANAGEMENT:")
        print(f"{Fore.WHITE}11. Manage caches")
        print(f"{Fore.WHITE}12. Manage API credentials")
        print(f"{Fore.WHITE}13. Reset environment (reinstall dependencies)")
        print(f"{Fore.WHITE}14. Exit")
        
        choice = input(f"\n{Fore.CYAN}Enter your choice (1-14): ")
        
        if choice == "1":
            # Run the playlist converter script
            print_info("\nConverting local playlists to Spotify playlists...")
            directory = input("Enter directory to search for playlists (press Enter for current directory): ")
            threshold = input("Enter confidence threshold (press Enter for default 80): ")
            
            args = []
            if directory:
                args.append(directory)
            if threshold:
                args.extend(["--threshold", threshold])
                
            run_script(PLAYLIST_CONVERTER_SCRIPT, args)
            
        elif choice == "2":
            # Run the like songs script
            print_info("\nRunning like songs functionality...")
            run_script(LIKE_SONGS_SCRIPT)
            
        elif choice == "3":
            # Run the Christmas cleanup script
            print_info("\nRemoving Christmas songs from Liked Songs...")
            run_script(CHRISTMAS_CLEANUP_SCRIPT)
            
        elif choice == "4":
            # Run the duplicate removal script
            print_info("\nRemoving duplicate songs from Liked Songs...")
            run_script(REMOVE_DUPLICATES_SCRIPT)
            
        elif choice == "5":
            # Run the skipped songs identifier script
            print_info("\nIdentifying frequently skipped songs...")
            run_script(IDENTIFY_SKIPPED_SCRIPT)
            
        elif choice == "6":
            # Run the follow artists script
            print_info("\nRunning follow artists functionality...")
            run_script(FOLLOW_ARTISTS_SCRIPT)
            
        elif choice == "7":
            # Run the similar artists script
            print_info("\nFinding artists to follow that you probably like...")
            run_script(SIMILAR_ARTISTS_SCRIPT)
            
        elif choice == "8":
            # Run the artist cleanup script
            print_info("\nRemoving followed artists that you probably don't like...")
            run_script(CLEANUP_ARTISTS_SCRIPT)
            
        elif choice == "9":
            # Run the enhanced analytics script
            print_info("\nLaunching enhanced analytics & insights...")
            run_script(ANALYTICS_SCRIPT)
            
        elif choice == "10":
            # Run the backup script
            print_info("\nRunning backup & export functionality...")
            run_script(BACKUP_SCRIPT)
            
        elif choice == "11":
            # Manage caches
            manage_caches()
            
        elif choice == "12":
            # Manage API credentials
            manage_api_credentials()
            
        elif choice == "13":
            # Reset environment
            reset_environment()
            
        elif choice == "14":
            print_success("Exiting...")
            break
        
        else:
            print_error("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
