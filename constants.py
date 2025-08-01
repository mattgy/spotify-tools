#!/usr/bin/env python3
"""
Centralized constants for the Spotify Tools project.
Contains shared values used across multiple scripts.
"""

import os
from pathlib import Path

# Application metadata
APP_NAME = "Spotify Tools"
APP_VERSION = "2.0.0"
APP_AUTHOR = "Matt Y"

# Directory paths
CONFIG_DIR = os.path.join(str(Path.home()), ".spotify-tools")
CACHE_DIR = os.path.join(CONFIG_DIR, "cache")
BACKUP_DIR = os.path.join(CONFIG_DIR, "backups")
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, "credentials.json")

# Cache expiration times (in seconds) - default to 30 days for consistency
DEFAULT_CACHE_EXPIRATION = 30 * 24 * 60 * 60  # 30 days

CACHE_EXPIRATION = {
    'short': 60 * 60,                    # 1 hour (for rapidly changing data)
    'medium': 24 * 60 * 60,              # 24 hours (for daily data)
    'long': 7 * 24 * 60 * 60,            # 7 days (for weekly data)
    'default': DEFAULT_CACHE_EXPIRATION, # 30 days (standard across app)
    'very_long': DEFAULT_CACHE_EXPIRATION, # 30 days (for consistency)
    'personal': DEFAULT_CACHE_EXPIRATION,  # 30 days (user data should persist)
    'external': DEFAULT_CACHE_EXPIRATION  # 30 days (external API data)
}

# Standardized cache keys for consistent reuse across the app
STANDARD_CACHE_KEYS = {
    'user_playlists': 'user_playlists',
    'liked_songs': 'all_liked_songs',
    'followed_artists': 'followed_artists',
    'top_artists': 'top_artists',
    'recently_played': 'recently_played',
    'playlist_tracks': 'playlist_tracks_{playlist_id}',
    'artist_details': 'artist_details_{artist_id}',
    'track_search': 'track_search_{artist}_{album}_{title}',
    'similar_artists': 'similar_artists_{artist_id}',
    'ai_match': 'ai_match_{service}_{artist}_{title}_{album}'
}

# Spotify API scopes organized by purpose
SPOTIFY_SCOPES = {
    'read_only': [
        "user-top-read",
        "user-library-read", 
        "playlist-read-private",
        "user-follow-read",
        "user-read-email",
        "user-read-private",
        "user-read-recently-played"
    ],
    'modify': [
        "user-top-read",
        "user-library-read",
        "user-library-modify", 
        "playlist-read-private",
        "playlist-modify-private",
        "playlist-modify-public",
        "user-follow-read",
        "user-follow-modify",
        "user-read-email",
        "user-read-private",
        "user-read-recently-played"
    ],
    'full': [
        "user-top-read",
        "user-library-read",
        "user-library-modify", 
        "playlist-read-private",
        "playlist-modify-private",
        "playlist-modify-public",
        "user-follow-read",
        "user-follow-modify",
        "user-read-email",
        "user-read-private",
        "user-read-recently-played",
        "user-read-playback-state",
        "user-modify-playback-state"
    ]
}

# API batch sizes and limits
BATCH_SIZES = {
    'spotify_tracks': 50,         # Max tracks per Spotify API call
    'spotify_artists': 50,        # Max artists per Spotify API call
    'spotify_audio_features': 100, # Max audio features per call
    'display_pagination': 20,     # Items per page in paginated displays
    'processing_batch': 100       # Default batch size for processing
}

# Rate limiting delays (in seconds)
RATE_LIMITS = {
    'api_call_delay': 0.1,        # Delay between API calls
    'batch_delay': 0.5,           # Delay between batches
    'retry_base_delay': 1,        # Base delay for retries
    'max_retries': 3              # Maximum retry attempts
}

# Default confidence thresholds
CONFIDENCE_THRESHOLDS = {
    'fuzzy_matching': 0.8,        # 80% similarity for fuzzy matching
    'external_validation': 0.7,   # 70% confidence for external APIs
    'personal_relevance': 0.6     # 60% for personal taste matching
}

# Export format configurations
EXPORT_FORMATS = {
    'apple_music': {
        'extension': '.txt',
        'format': 'artist - title',
        'encoding': 'utf-8'
    },
    'youtube_music': {
        'extension': '.csv', 
        'columns': ['Artist', 'Title', 'Album'],
        'encoding': 'utf-8'
    },
    'm3u': {
        'extension': '.m3u8',
        'format': '#EXTINF:-1,{artist} - {title}\n{path}',
        'encoding': 'utf-8'
    },
    'json': {
        'extension': '.json',
        'indent': 2,
        'encoding': 'utf-8'
    }
}

# Audio feature analysis ranges
AUDIO_FEATURES = {
    'energy': {'low': 0.3, 'high': 0.7},
    'valence': {'low': 0.3, 'high': 0.7}, 
    'danceability': {'low': 0.4, 'high': 0.8},
    'acousticness': {'low': 0.2, 'high': 0.8},
    'tempo': {'low': 80, 'high': 140}  # BPM
}

# Geographic regions for heat map analysis
GEOGRAPHIC_REGIONS = {
    'north_america': ['US', 'CA', 'MX'],
    'europe': ['GB', 'FR', 'DE', 'IT', 'ES', 'NL', 'SE', 'NO', 'DK'],
    'asia': ['JP', 'KR', 'CN', 'IN', 'TH', 'ID'],
    'oceania': ['AU', 'NZ'],
    'south_america': ['BR', 'AR', 'CL', 'CO'],
    'africa': ['ZA', 'NG', 'EG', 'MA']
}

# Error messages
ERROR_MESSAGES = {
    'auth_failed': "Failed to authenticate with Spotify. Please check your credentials.",
    'api_rate_limit': "API rate limit exceeded. Please wait and try again.",
    'network_error': "Network error occurred. Please check your connection.",
    'file_not_found': "The specified file could not be found.",
    'invalid_format': "The file format is not supported.",
    'insufficient_data': "Insufficient data to perform the requested operation."
}

# Success messages
SUCCESS_MESSAGES = {
    'auth_success': "✅ Successfully authenticated with Spotify!",
    'operation_complete': "✅ Operation completed successfully!",
    'file_saved': "✅ File saved successfully!",
    'cache_cleared': "✅ Cache cleared successfully!"
}

if __name__ == "__main__":
    print(f"{APP_NAME} v{APP_VERSION}")
    print(f"Configuration directory: {CONFIG_DIR}")
    print(f"Available cache expirations: {list(CACHE_EXPIRATION.keys())}")
    print(f"Available Spotify scope sets: {list(SPOTIFY_SCOPES.keys())}")