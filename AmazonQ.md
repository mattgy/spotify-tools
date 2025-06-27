# Spotify Playlist Converter

## Overview
I've created a script that recursively searches for playlist files (like M3U) in a specified directory and converts them to Spotify playlists. The script uses fuzzy matching to find songs on Spotify and confirms with you when matches aren't highly confident.

## Features
- Recursively scans directories for playlist files (.m3u, .m3u8, .pls)
- Uses fuzzy matching for song identification
- Confirms low-confidence matches with the user
- Updates existing Spotify playlists with missing songs
- Handles authentication with Spotify API

## Usage
```bash
# Convert playlists in the current directory
./spotify_playlist_converter.py

# Convert playlists in a specific directory
./spotify_playlist_converter.py /path/to/playlists

# Adjust the confidence threshold (default: 80)
./spotify_playlist_converter.py --threshold 70
```

## How It Works
1. The script recursively searches for playlist files in the specified directory
2. For each playlist file:
   - Parses the file to extract track information
   - Searches for each track on Spotify
   - Confirms with you if the match confidence is below the threshold
   - Creates a new Spotify playlist or updates an existing one with the same name
3. Provides a summary of the conversion process

## Requirements
- Spotify API credentials (uses the same credentials as other scripts in this repository)
- Python packages: spotipy, thefuzz, tqdm

## Integration with Existing Tools
This script integrates with your existing Spotify Tools setup and uses the same credential management system.
