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
PREFERENCES_FILE = os.path.join(CONFIG_DIR, "preferences.json")
EXCLUSIONS_FILE = os.path.join(CONFIG_DIR, "exclusions.json")

# Cache expiration times (in seconds)
# Updated to more reasonable defaults - user data changes frequently
DEFAULT_CACHE_EXPIRATION = 24 * 60 * 60  # 24 hours (more reasonable default)

CACHE_EXPIRATION = {
    'short': 1 * 60 * 60,                # 1 hour (user playlists, liked songs - changes frequently)
    'medium': 6 * 60 * 60,               # 6 hours (playlist tracks)
    'long': 7 * 24 * 60 * 60,            # 7 days (artist info, relatively static)
    'default': DEFAULT_CACHE_EXPIRATION, # 24 hours (reasonable default)
    'very_long': 30 * 24 * 60 * 60,      # 30 days (static data only)
    'personal': 1 * 60 * 60,             # 1 hour (user data changes frequently)
    'external': 7 * 24 * 60 * 60         # 7 days (external API data)
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
    # 'spotify_audio_features': 100, # DEPRECATED: Audio Features API removed by Spotify
    'display_pagination': 20,     # Items per page in paginated displays
    'processing_batch': 100       # Default batch size for processing
}

# Rate limiting delays (in seconds)
# Spotify's actual limit is ~10-20 requests/second
RATE_LIMITS = {
    'api_call_delay': 0.05,       # Delay between API calls (20 req/s)
    'batch_delay': 0.3,           # Delay between batches
    'retry_base_delay': 1,        # Base delay for retries
    'max_retries': 3,             # Maximum retry attempts
    'respect_retry_after': True   # Always respect Retry-After headers
}

# Default confidence thresholds
CONFIDENCE_THRESHOLDS = {
    'fuzzy_matching': 0.8,        # 80% similarity for fuzzy matching
    'external_validation': 0.7,   # 70% confidence for external APIs
    'personal_relevance': 0.6     # 60% for personal taste matching
}

# Library cleanup and analysis thresholds
CLEANUP_THRESHOLDS = {
    'low_follower_count': 10,     # Artists with <= 10 followers considered low-follower
    'min_play_count': 1,          # Minimum play count to consider a song "played"
    'stale_cache_days': 30        # Days before cache is considered stale
}

# AI service settings for track matching
AI_SETTINGS = {
    'default_service': None,      # None = use first available (gemini, openai, anthropic, perplexity)
    'cache_expiration': 7 * 24 * 60 * 60,  # 7 days for AI responses
    'max_retries': 2,             # Maximum retry attempts for AI queries
    'timeout': 30                 # Request timeout in seconds
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
# DEPRECATED: Spotify deprecated the Audio Features API endpoint in 2024
# Kept for reference but functionality removed
# AUDIO_FEATURES = {
#     'energy': {'low': 0.3, 'high': 0.7},
#     'valence': {'low': 0.3, 'high': 0.7},
#     'danceability': {'low': 0.4, 'high': 0.8},
#     'acousticness': {'low': 0.2, 'high': 0.8},
#     'tempo': {'low': 80, 'high': 140}  # BPM
# }

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
    'quota_exceeded': "API quota exceeded. Your app is in Development Mode (25 user limit).",
    'extended_access_needed': "This operation requires Extended Access. See: https://developer.spotify.com/documentation/web-api/concepts/quota-modes",
    'network_error': "Network error occurred. Please check your connection.",
    'file_not_found': "The specified file could not be found.",
    'invalid_format': "The file format is not supported.",
    'insufficient_data': "Insufficient data to perform the requested operation.",
    'audio_features_deprecated': "Audio Features API has been deprecated by Spotify and is no longer available."
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