#!/usr/bin/env python3
"""
Create a Spotify playlist from a list of songs provided via file or direct input.
Reuses the matching logic from spotify_playlist_converter.py.

Author: Gemini CLI
"""

import os
import sys
import tempfile
from colorama import Fore, Style
import colorama

# Add the current directory to the Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Import centralized utilities
from print_utils import (
    print_header, print_success, print_error, print_warning, print_info,
    print_section_header, print_status
)
from spotify_utils import create_spotify_client
from preferences_manager import get_preference

# Import core logic from playlist converter
import spotify_playlist_converter as converter

def get_pasted_input():
    """Prompt user to paste song list text."""
    print_info("\nPaste your song list below (one song per line, e.g., 'Artist - Title').")
    print_info("When finished, press Enter on an empty line or press Ctrl+D (Unix) / Ctrl+Z (Windows).")
    print(f"{Fore.YELLOW}Paste here:")
    
    lines = []
    try:
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
    except EOFError:
        pass
        
    return "\n".join(lines)

def main():
    # Initialize colorama
    colorama.init(autoreset=True)
    
    print_header("CREATE PLAYLIST FROM SONG LIST")
    
    # 1. Authenticate with Spotify
    print_info("Authenticating with Spotify...")
    try:
        # Use common scopes for playlist modification
        scopes = [
            "playlist-read-private",
            "playlist-modify-private",
            "playlist-modify-public",
            "user-library-read"
        ]
        sp = create_spotify_client(scopes, "create_from_list")
        if not sp:
            print_error("Failed to authenticate with Spotify.")
            return
    except Exception as e:
        print_error(f"Authentication error: {e}")
        return

    user_info = sp.current_user()
    user_id = user_info['id']
    print_success(f"Authenticated as: {user_info.get('display_name', user_id)}")

    # 2. Input Selection
    print_section_header("INPUT SELECTION")
    print("1. Provide path to a text file")
    print("2. Paste song list text directly")
    
    choice = input(f"\n{Fore.CYAN}Choose input method (1-2, default: 1): ").strip()
    
    file_path = None
    temp_file = None
    playlist_name_default = "New List Playlist"
    
    if choice == "2":
        pasted_text = get_pasted_input()
        if not pasted_text:
            print_error("No text provided.")
            return
            
        # Create a temporary file to hold the pasted text
        temp_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False)
        temp_file.write(pasted_text)
        temp_file.close()
        file_path = temp_file.name
        playlist_name_default = "Pasted Songs"
    else:
        file_path = input(f"\n{Fore.CYAN}Enter path to text file: ").strip()
        
        # Remove quotes if the user dragged and dropped the file
        if (file_path.startswith('"') and file_path.endswith('"')) or (file_path.startswith("'") and file_path.endswith("'")):
            file_path = file_path[1:-1]
            
        if not os.path.exists(file_path):
            print_error(f"File not found: {file_path}")
            return
            
        if not os.path.isfile(file_path):
            print_error(f"Path is not a file: {file_path}")
            return
        
        playlist_name_default = os.path.splitext(os.path.basename(file_path))[0]

    # 3. Get playlist name
    playlist_name = input(f"{Fore.CYAN}Enter playlist name [{playlist_name_default}]: ").strip()
    if not playlist_name:
        playlist_name = playlist_name_default

    # 4. Configure matching settings
    print_section_header("MATCHING SETTINGS")
    
    # Use preferences or defaults
    auto_threshold = get_preference("playlist_converter.auto_threshold", 85)
    conf_threshold = get_preference("playlist_converter.confidence_threshold", 70)
    use_ai = get_preference("playlist_converter.use_ai_boost", False)
    
    print(f"  Current defaults:")
    print(f"  • Auto-accept threshold: {auto_threshold}")
    print(f"  • Manual review threshold: {conf_threshold}")
    print(f"  • AI Boost: {'Enabled' if use_ai else 'Disabled'}")
    
    change_settings = input(f"\n{Fore.CYAN}Use these settings? (y/n, default: y): ").strip().lower()
    if change_settings == 'n':
        try:
            auto_input = input(f"Enter auto-accept threshold (70-100, default {auto_threshold}): ").strip()
            if auto_input: auto_threshold = int(auto_input)
            
            conf_input = input(f"Enter manual review threshold (50-{auto_threshold-1}, default {conf_threshold}): ").strip()
            if conf_input: conf_threshold = int(conf_input)
            
            ai_input = input(f"Enable AI Boost? (y/n, default: {'y' if use_ai else 'n'}): ").strip().lower()
            if ai_input: use_ai = (ai_input == 'y')
        except ValueError:
            print_warning("Invalid input, using defaults.")

    # 5. Process the list
    print_section_header(f"PROCESSING: {playlist_name}")
    
    try:
        # Check if the file contains tracks
        tracks = converter.parse_text_playlist_file(file_path)
        
        if not tracks:
            print_error("No tracks found. Make sure each line follows 'Artist - Title' format.")
            if temp_file: os.unlink(temp_file.name)
            return
            
        print_info(f"Found {len(tracks)} entries to process.")
        
        # We'll use a specific path to ensure the playlist name is what the user wants
        # process_playlist_file uses the filename as the playlist name
        final_file_path = os.path.join(os.path.dirname(file_path), f"{playlist_name}.txt")
        
        # If it's a temp file or the user chose a different name, we need to handle it.
        # Let's temporarily copy/link to have the right name if needed
        cleanup_final = False
        if os.path.basename(file_path) != f"{playlist_name}.txt":
            import shutil
            try:
                shutil.copy(file_path, final_file_path)
                cleanup_final = True
                process_path = final_file_path
            except:
                process_path = file_path # Fallback
        else:
            process_path = file_path
            
        # Let's use the core processing logic
        matched_count, skipped_count = converter.process_playlist_file(
            sp=sp,
            file_path=process_path,
            user_id=user_id,
            confidence_threshold=conf_threshold,
            batch_mode=True, # Enable auto-accept above threshold
            auto_threshold=auto_threshold,
            use_previous_decisions=True,
            use_ai_boost=use_ai
        )
        
        if cleanup_final:
            try: os.unlink(final_file_path)
            except: pass
            
        print_section_header("SUMMARY")
        if matched_count > 0:
            print_success(f"Successfully processed playlist '{playlist_name}'")
            print(f"  • Tracks matched and added: {matched_count}")
            print(f"  • Tracks skipped: {skipped_count}")
        else:
            print_warning("No tracks were added to the playlist.")
            
    except Exception as e:
        print_error(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if temp_file and os.path.exists(temp_file.name):
            try: os.unlink(temp_file.name)
            except: pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
        sys.exit(0)
