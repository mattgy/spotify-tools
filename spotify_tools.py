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
IDENTIFY_SKIPPED_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_identify_skipped.py")
PLAYLIST_RECONCILE_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_playlist_reconcile.py")
PLAYLIST_SIZE_MANAGER_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_playlist_size_manager.py")
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
    
    # AI Service credentials (optional)
    print_info("\nAI Service Credentials (Optional)")
    print("AI services can help find difficult-to-match tracks.")
    print("Leave blank to skip AI-assisted matching.")
    print("\nSupported services:")
    print("1. Google Gemini Pro (free tier available)")
    print("   Get API key at: https://makersuite.google.com/app/apikey")
    print("2. OpenAI GPT-4 (paid)")
    print("   Get API key at: https://platform.openai.com/api-keys")
    print("3. Anthropic Claude (paid)")
    print("   Get API key at: https://console.anthropic.com/settings/keys")
    print("4. Perplexity (paid)")
    print("   Get API key at: https://www.perplexity.ai/settings/api")
    
    gemini_api_key = input(f"\nEnter Google Gemini API Key [{existing_credentials.get('GEMINI_API_KEY', '')}]: ").strip()
    if not gemini_api_key and 'GEMINI_API_KEY' in existing_credentials:
        gemini_api_key = existing_credentials['GEMINI_API_KEY']
    
    openai_api_key = input(f"Enter OpenAI API Key [{existing_credentials.get('OPENAI_API_KEY', '')}]: ").strip()
    if not openai_api_key and 'OPENAI_API_KEY' in existing_credentials:
        openai_api_key = existing_credentials['OPENAI_API_KEY']
    
    anthropic_api_key = input(f"Enter Anthropic API Key [{existing_credentials.get('ANTHROPIC_API_KEY', '')}]: ").strip()
    if not anthropic_api_key and 'ANTHROPIC_API_KEY' in existing_credentials:
        anthropic_api_key = existing_credentials['ANTHROPIC_API_KEY']
    
    perplexity_api_key = input(f"Enter Perplexity API Key [{existing_credentials.get('PERPLEXITY_API_KEY', '')}]: ").strip()
    if not perplexity_api_key and 'PERPLEXITY_API_KEY' in existing_credentials:
        perplexity_api_key = existing_credentials['PERPLEXITY_API_KEY']
    
    # Save credentials
    credentials = {
        "SPOTIFY_CLIENT_ID": spotify_client_id,
        "SPOTIFY_CLIENT_SECRET": spotify_client_secret,
        "SPOTIFY_REDIRECT_URI": spotify_redirect_uri,
        "LASTFM_API_KEY": lastfm_api_key,
        "GEMINI_API_KEY": gemini_api_key,
        "OPENAI_API_KEY": openai_api_key,
        "ANTHROPIC_API_KEY": anthropic_api_key,
        "PERPLEXITY_API_KEY": perplexity_api_key
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
    
    # Show current environment status
    venv_dir = os.path.join(SCRIPT_DIR, "venv")
    if os.path.exists(venv_dir):
        print_info(f"Current virtual environment: {venv_dir}")
        venv_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                       for dirpath, dirnames, filenames in os.walk(venv_dir)
                       for filename in filenames) / (1024 * 1024)  # MB
        print_info(f"Virtual environment size: {venv_size:.1f} MB")
    else:
        print_warning("No virtual environment found.")
    
    # Confirm with user
    confirm = input("This will remove and recreate the virtual environment. Continue? (y/n): ").strip().lower()
    if confirm != "y":
        print_warning("Reset cancelled.")
        return
    
    try:
        print_info("Starting environment reset...")
        
        # Find system Python
        import shutil
        system_python = shutil.which("python3")
        if not system_python:
            system_python = shutil.which("python")
        
        if not system_python:
            print_error("Could not find system Python.")
            print_info("Please ensure Python 3 is installed and in your PATH.")
            return
        
        print_info(f"Using system Python: {system_python}")
        
        # Check if reset script exists
        reset_script = os.path.join(SCRIPT_DIR, "reset.py")
        if not os.path.exists(reset_script):
            print_error("Reset script not found.")
            print_info("Please reinstall dependencies manually with: python3 install_dependencies.py")
            return
        
        print_info("Running reset script...")
        print_info("This may take a few minutes...")
        
        # Run reset with real-time output
        process = subprocess.Popen(
            [system_python, reset_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=SCRIPT_DIR
        )
        
        # Show output in real-time
        output_lines = []
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                print(f"  {line}")
                output_lines.append(line)
        
        return_code = process.poll()
        
        if return_code == 0:
            print_success("Environment reset successfully!")
            print_info("Virtual environment has been recreated with fresh dependencies.")
            print_info("Please restart the application: ./spotify_run.py")
            input("Press Enter to exit...")
            sys.exit(0)
        else:
            print_error("Reset failed.")
            print_error("Last few lines of output:")
            for line in output_lines[-5:]:
                print(f"  {line}")
            print_info("You can manually run: python3 reset.py")
            
    except subprocess.TimeoutExpired:
        print_error("Reset timed out after 5 minutes.")
        print_info("This might indicate a network issue. Please try again or run manually: python3 reset.py")
    except FileNotFoundError:
        print_error("Reset script not found or Python not accessible.")
        print_info("Please manually run: python3 reset.py")
    except Exception as e:
        print_error(f"Unexpected error during reset: {e}")
        print_info("Please manually run: python3 reset.py")

def _display_cache_summary():
    """Display cache summary information."""
    from cache_utils import get_cache_info, list_caches
    
    info = get_cache_info()
    print(f"Total cache files: {info['count']}")
    print(f"Total size: {info['total_size'] / 1024:.1f} KB")
    
    if info['oldest']:
        print(f"Oldest cache: {info['oldest']['name']} ({time.ctime(info['oldest']['mtime'])})")
    
    if info['newest']:
        print(f"Newest cache: {info['newest']['name']} ({time.ctime(info['newest']['mtime'])})")
    
    return _group_caches_by_type()

def _group_caches_by_type():
    """Group caches by type and return the grouped data."""
    from cache_utils import list_caches
    
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
    
    return cache_types

def _clear_caches_by_type(cache_types):
    """Handle clearing caches by type."""
    from cache_utils import clear_cache
    
    if not cache_types:
        print_warning("No caches to clear.")
        return
    
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

def manage_caches():
    """Manage cache files."""
    print_header("Cache Management")
    
    # Import cache utilities
    sys.path.insert(0, SCRIPT_DIR)
    from cache_utils import clear_cache, clean_deprecated_caches, optimize_cache_storage, easy_cache_cleanup
    
    # Display cache summary and get grouped cache types
    cache_types = _display_cache_summary()
    
    # Options
    print("\nOptions:")
    print("1. Clear all caches")
    print("2. Clear caches by type")
    print("3. Clean up deprecated cache files")
    print("4. Optimize cache storage (comprehensive cleanup)")
    print("5. Back to main menu")
    
    choice = input("\nEnter your choice (1-5): ")
    
    if choice == "1":
        # Clear all caches
        confirm = input("Are you sure you want to clear all caches? (y/n): ").strip().lower()
        if confirm == "y":
            clear_cache()
            print_success("All caches cleared.")
    elif choice == "2":
        # Clear caches by type
        _clear_caches_by_type(cache_types)
    elif choice == "3":
        # Clean up deprecated cache files
        print_info("Cleaning up deprecated cache files...")
        clean_deprecated_caches()
    elif choice == "4":
        # Optimize cache storage
        optimize_cache_storage()

def playlist_converter_menu():
    """Sub-menu for playlist converter options."""
    while True:
        print_header("Playlist Converter & Management")
        
        print(f"{Fore.YELLOW}{Style.BRIGHT}PLAYLIST SYNC OPTIONS:")
        print(f"{Fore.WHITE}1. Auto-sync only (add missing playlists & tracks automatically)")
        print(f"{Fore.WHITE}2. Auto-sync + manual review (review matches below threshold)")
        
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}CLEANUP OPTIONS:")
        print(f"{Fore.WHITE}3. Clean up Spotify playlists to match local ones exactly")
        print(f"{Fore.WHITE}4. Delete duplicate Spotify playlists (same name as local)")
        
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}MAINTENANCE:")
        print(f"{Fore.WHITE}5. Clear processed playlist cache")
        print(f"{Fore.WHITE}6. Remove .m3u suffixes from Spotify playlists")
        
        print(f"\n{Fore.WHITE}7. Back to main menu")
        
        choice = input(f"\n{Fore.CYAN}Enter your choice (1-7): ")
        
        if choice == "1":
            # Auto-sync mode - fully autonomous
            print_info("\nAuto-syncing playlists (autonomous mode)...")
            print_info("This will create missing playlists and add missing tracks automatically.")
            directory = input("Enter directory to search for playlists (press Enter for current directory): ")
            threshold = input("Enter confidence threshold for auto-adding (70-100, default 85): ").strip()
            
            args = ["--auto-mode"]
            if directory:
                args.append(directory)
            if threshold:
                args.extend(["--auto-threshold", threshold])
                
            run_script(PLAYLIST_CONVERTER_SCRIPT, args)
            
        elif choice == "2":
            # Auto-sync with manual review
            print_info("\nAuto-syncing playlists with manual review...")
            print_info("This will create missing playlists, auto-add high confidence tracks,")
            print_info("and let you manually review medium confidence matches.")
            directory = input("Enter directory to search for playlists (press Enter for current directory): ")
            
            args = []
            if directory:
                args.append(directory)
                
            run_script(PLAYLIST_CONVERTER_SCRIPT, args)
            
        elif choice == "3":
            # Clean up Spotify playlists to match local ones
            print_info("\nCleaning up Spotify playlists to match local ones exactly...")
            directory = input("Enter directory containing local playlists (press Enter for current directory): ")
            
            args = ["--cleanup-mode"]
            if directory:
                args.append(directory)
                
            run_script(PLAYLIST_RECONCILE_SCRIPT, args)
            
        elif choice == "4":
            # Delete duplicate playlists
            print_info("\nDeleting duplicate Spotify playlists with same names as local files...")
            directory = input("Enter directory containing local playlists (press Enter for current directory): ")
            
            args = ["--delete-duplicates-mode"]
            if directory:
                args.append(directory)
                
            run_script(PLAYLIST_RECONCILE_SCRIPT, args)
            
        elif choice == "5":
            # Clear processed playlist cache
            print_info("\nClearing processed playlist cache...")
            confirm = input("This will reset all playlist processing history. Continue? (y/n): ").lower().strip()
            
            if confirm == 'y':
                # Clear both converter and reconcile caches
                run_script(PLAYLIST_CONVERTER_SCRIPT, ["--clear-cache"])
                run_script(PLAYLIST_RECONCILE_SCRIPT, ["--clear-cache"])
                print_success("All playlist processing caches cleared.")
            else:
                print_warning("Cache clearing cancelled.")
            
        elif choice == "6":
            # Remove .m3u suffixes from Spotify playlists
            print_info("\nRemoving .m3u suffixes from Spotify playlists...")
            run_script(PLAYLIST_RECONCILE_SCRIPT, ["--remove-suffixes-mode"])
            
        elif choice == "7":
            break
        
        else:
            print_error("Invalid choice. Please try again.")

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
        print(f"{Fore.WHITE}4. Find and manage playlists by track count")
        
        # Artist Management
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}ARTIST MANAGEMENT:")
        print(f"{Fore.WHITE}5. Follow all artists in your created playlists")
        print(f"{Fore.WHITE}6. Find Artists to Follow That You Probably Like")
        print(f"{Fore.WHITE}7. Remove followed artists that you probably don't like")
        
        # System Management
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}SYSTEM MANAGEMENT:")
        print(f"{Fore.WHITE}8. Backup & export your music library")
        print(f"{Fore.WHITE}9. Manage caches")
        print(f"{Fore.WHITE}10. Manage API credentials")
        print(f"{Fore.WHITE}11. Reset environment (reinstall dependencies)")
        print(f"{Fore.WHITE}12. Exit")
        
        choice = input(f"\n{Fore.CYAN}Enter your choice (1-12): ")
        
        if choice == "1":
            # Playlist converter sub-menu
            playlist_converter_menu()
            
        elif choice == "2":
            # Run the like songs script
            print_info("\nRunning like songs functionality...")
            run_script(LIKE_SONGS_SCRIPT)
            
        elif choice == "3":
            # Run the Christmas cleanup script
            print_info("\nRemoving Christmas songs from Liked Songs...")
            run_script(CHRISTMAS_CLEANUP_SCRIPT)
            
        elif choice == "4":
            # Run the playlist size manager script
            print_info("\nManaging playlists by track count...")
            run_script(PLAYLIST_SIZE_MANAGER_SCRIPT)
            
        elif choice == "5":
            # Run the follow artists script
            print_info("\nRunning follow artists functionality...")
            run_script(FOLLOW_ARTISTS_SCRIPT)
            
        elif choice == "6":
            # Run the similar artists script
            print_info("\nFinding artists to follow that you probably like...")
            run_script(SIMILAR_ARTISTS_SCRIPT)
            
        elif choice == "7":
            # Run the artist cleanup script
            print_info("\nRemoving followed artists that you probably don't like...")
            run_script(CLEANUP_ARTISTS_SCRIPT)
            
        elif choice == "8":
            # Run the backup script
            print_info("\nRunning backup & export functionality...")
            run_script(BACKUP_SCRIPT)
            
        elif choice == "9":
            # Manage caches
            manage_caches()
            
        elif choice == "10":
            # Manage API credentials
            manage_api_credentials()
            
        elif choice == "11":
            # Reset environment
            reset_environment()
            
        elif choice == "12":
            print_success("Exiting...")
            break
        
        else:
            print_error("Invalid choice. Please try again.")

# Aliases for backward compatibility with tests
def setup_credentials():
    """Alias for manage_api_credentials."""
    return manage_api_credentials()

def clear_caches():
    """Alias for manage_caches."""
    return manage_caches()

if __name__ == "__main__":
    main()
