#!/usr/bin/env python3
"""
Configuration management for Spotify Tools.
Handles loading settings from files and environment variables.
"""

import os
import json
from pathlib import Path

# Default configuration values
DEFAULT_CONFIG = {
    # Cache settings
    "cache_expiration_days": 7,
    "cache_max_size_mb": 100,
    
    # API rate limiting
    "api_delay_seconds": 0.1,
    "api_retry_count": 3,
    "api_timeout_seconds": 30,
    
    # Batch processing
    "batch_size_artists": 50,
    "batch_size_tracks": 50,
    "batch_size_playlists": 20,
    
    # UI settings
    "progress_bar_enabled": True,
    "colored_output": True,
    
    # Analytics settings
    "analytics_time_ranges": ["short_term", "medium_term", "long_term"],
    "analytics_max_items": 50,
    
    # Discovery settings
    "similar_artist_limit": 20,
    "confidence_threshold": 0.8,
    
    # Backup settings
    "backup_format": "json",
    "backup_compression": True
}

class Config:
    """Configuration manager for Spotify Tools."""
    
    def __init__(self):
        self.config_dir = os.path.join(str(Path.home()), ".spotify-tools")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self._config = DEFAULT_CONFIG.copy()
        self.load_config()
    
    def load_config(self):
        """Load configuration from file and environment variables."""
        # Create config directory if it doesn't exist
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Load from file if it exists
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    file_config = json.load(f)
                    self._config.update(file_config)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load config file: {e}")
        
        # Override with environment variables
        self._load_from_env()
    
    def _load_from_env(self):
        """Load configuration from environment variables."""
        env_mappings = {
            "SPOTIFY_TOOLS_CACHE_DAYS": ("cache_expiration_days", int),
            "SPOTIFY_TOOLS_API_DELAY": ("api_delay_seconds", float),
            "SPOTIFY_TOOLS_BATCH_SIZE": ("batch_size_artists", int),
            "SPOTIFY_TOOLS_PROGRESS_BAR": ("progress_bar_enabled", bool),
            "SPOTIFY_TOOLS_COLORED_OUTPUT": ("colored_output", bool),
        }
        
        for env_var, (config_key, type_func) in env_mappings.items():
            if env_var in os.environ:
                try:
                    if type_func == bool:
                        value = os.environ[env_var].lower() in ('true', '1', 'yes', 'on')
                    else:
                        value = type_func(os.environ[env_var])
                    self._config[config_key] = value
                except (ValueError, TypeError) as e:
                    print(f"Warning: Invalid value for {env_var}: {e}")
    
    def get(self, key, default=None):
        """Get a configuration value."""
        return self._config.get(key, default)
    
    def set(self, key, value):
        """Set a configuration value."""
        self._config[key] = value
    
    def save_config(self):
        """Save current configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self._config, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save config file: {e}")
    
    def reset_to_defaults(self):
        """Reset configuration to default values."""
        self._config = DEFAULT_CONFIG.copy()
        self.save_config()
    
    def update_config(self, updates):
        """Update multiple configuration values."""
        self._config.update(updates)
        self.save_config()
    
    @property
    def all_settings(self):
        """Get all configuration settings."""
        return self._config.copy()

# Global configuration instance
config = Config()

# Convenience functions for common settings
def get_cache_expiration():
    """Get cache expiration in seconds."""
    return config.get("cache_expiration_days", 7) * 24 * 60 * 60

def get_api_delay():
    """Get API delay in seconds."""
    return config.get("api_delay_seconds", 0.1)

def get_batch_size(item_type="artists"):
    """Get batch size for different item types."""
    return config.get(f"batch_size_{item_type}", 50)

def get_retry_count():
    """Get API retry count."""
    return config.get("api_retry_count", 3)

def is_progress_bar_enabled():
    """Check if progress bars are enabled."""
    return config.get("progress_bar_enabled", True)

def is_colored_output_enabled():
    """Check if colored output is enabled."""
    return config.get("colored_output", True)