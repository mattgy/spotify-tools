#!/usr/bin/env python3
"""
Utility functions for managing API credentials.

This module provides functions to get and set API credentials for various services.
Credentials are stored in a JSON file in the user's home directory.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import json
import stat
from pathlib import Path

# Import constants
from constants import CONFIG_DIR, CREDENTIALS_FILE

def get_spotify_credentials():
    """
    Get Spotify API credentials.

    Checks environment variables first (populated from ~/.secrets), then falls
    back to the JSON credentials file, then prompts interactively.

    Returns:
        tuple: (client_id, client_secret, redirect_uri)
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)

    # Environment variables take precedence (primary source of truth: ~/.secrets)
    client_id    = os.environ.get("SPOTIFY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    redirect_uri  = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    if client_id and client_secret:
        return client_id, client_secret, redirect_uri

    # Fall back to credentials file
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                stored = json.load(f)
            client_id     = stored.get("SPOTIFY_CLIENT_ID", "")
            client_secret = stored.get("SPOTIFY_CLIENT_SECRET", "")
            redirect_uri  = stored.get("SPOTIFY_REDIRECT_URI", redirect_uri) or redirect_uri
            if client_id and client_secret:
                return client_id, client_secret, redirect_uri
        except Exception:
            pass

    # Test mode — skip prompts
    if os.environ.get("SPOTIFY_TOOLS_TEST_MODE"):
        return None, None, None

    # Interactive prompt as last resort
    print("Spotify API credentials not found.")
    print("Please enter your Spotify API credentials:")
    try:
        client_id     = input("Client ID: ").strip()
        client_secret = input("Client Secret: ").strip()
        redirect_uri  = input("Redirect URI [http://127.0.0.1:8888/callback]: ").strip()
        if not redirect_uri:
            redirect_uri = "http://127.0.0.1:8888/callback"
    except EOFError:
        return None, None, None

    # Persist for future runs
    old_umask = os.umask(0o077)
    try:
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump({
                "SPOTIFY_CLIENT_ID":     client_id,
                "SPOTIFY_CLIENT_SECRET": client_secret,
                "SPOTIFY_REDIRECT_URI":  redirect_uri,
            }, f, indent=2)
        os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        os.umask(old_umask)

    return client_id, client_secret, redirect_uri

def get_lastfm_api_key():
    """
    Get Last.fm API key.

    Checks environment variables first (populated from ~/.secrets), then the
    JSON credentials file, then prompts interactively.

    Returns:
        str: Last.fm API key, or None if unavailable
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)

    # Environment variable takes precedence
    api_key = os.environ.get("LASTFM_API_KEY", "")
    if api_key:
        return api_key

    # Fall back to credentials file
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                stored = json.load(f)
            api_key = stored.get("LASTFM_API_KEY", "")
            if api_key:
                return api_key
        except Exception:
            pass

    # Test mode — skip prompts
    if os.environ.get("SPOTIFY_TOOLS_TEST_MODE"):
        return None

    # Interactive prompt as last resort
    print("Last.fm API key not found. Please enter your Last.fm API key:")
    try:
        api_key = input("API Key: ").strip()
    except EOFError:
        return None

    return api_key or None

def save_credentials(credentials_dict):
    """
    Save credentials to file.
    
    Args:
        credentials_dict (dict): Dictionary of credentials to save
    """
    # Create config directory if it doesn't exist
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # Load existing credentials if available
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            existing_credentials = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_credentials = {}
    
    # Update with new credentials
    existing_credentials.update(credentials_dict)
    
    # Save to file with secure permissions
    old_umask = os.umask(0o077)
    try:
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(existing_credentials, f, indent=2)
        os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        os.umask(old_umask)

def get_credentials():
    """Get all credentials, with environment variables taking precedence over the JSON file.

    Primary source of truth is ~/.secrets (sourced in ~/.zshrc).  The JSON file
    at ~/.spotify-tools/credentials.json is kept as a fallback for values not
    present in the environment.
    """
    credentials = {}

    # Load file as baseline (lowest priority)
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                credentials = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load credentials file: {e}")

    # Environment variables win — covers everything in ~/.secrets
    env_vars = [
        'SPOTIFY_CLIENT_ID',
        'SPOTIFY_CLIENT_SECRET',
        'SPOTIFY_REDIRECT_URI',
        'LASTFM_API_KEY',
        'LASTFM_USERNAME',
        'TICKETMASTER_CONSUMER_KEY',
        'TICKETMASTER_CONSUMER_SECRET',
        'BANDSINTOWN_APP_ID',
        # AI service credentials
        'GEMINI_API_KEY',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'PERPLEXITY_API_KEY',
    ]

    for var in env_vars:
        if os.environ.get(var):
            credentials[var] = os.environ[var]

    return credentials

def get_ai_credentials(service=None):
    """Get AI service API credentials.
    
    Args:
        service: 'gemini', 'openai', 'anthropic', 'perplexity', or None for all available
    
    Returns:
        API key string, dict of all AI keys, or None if not found
    """
    credentials = get_credentials()
    
    service_map = {
        'gemini': 'GEMINI_API_KEY',
        'openai': 'OPENAI_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'perplexity': 'PERPLEXITY_API_KEY'
    }
    
    if service:
        key_name = service_map.get(service.lower())
        if not key_name:
            return None
        return credentials.get(key_name)
    else:
        # Return all available AI credentials
        ai_creds = {}
        for service_name, key_name in service_map.items():
            if key_name in credentials and credentials[key_name]:
                ai_creds[service_name] = credentials[key_name]
        return ai_creds if ai_creds else None

def remove_ai_credentials(service=None):
    """Remove AI service credentials.
    
    Args:
        service: specific service to remove, or None to remove all AI credentials
    
    Returns:
        bool: True if successful
    """
    credentials = get_credentials()
    
    ai_keys = ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY']
    
    if service:
        service_map = {
            'gemini': 'GEMINI_API_KEY',
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'perplexity': 'PERPLEXITY_API_KEY'
        }
        key_to_remove = service_map.get(service.lower())
        if key_to_remove:
            credentials[key_to_remove] = ''  # Set to empty to trigger removal
    else:
        # Remove all AI credentials
        for key in ai_keys:
            credentials[key] = ''  # Set to empty to trigger removal
    
    save_credentials(credentials)
    return True
