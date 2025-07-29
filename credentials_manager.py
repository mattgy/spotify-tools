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

# Define config directory
CONFIG_DIR = os.path.join(str(Path.home()), ".spotify-tools")
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, "credentials.json")

def get_spotify_credentials():
    """
    Get Spotify API credentials.
    
    Returns:
        tuple: (client_id, client_secret, redirect_uri)
    """
    # Create config directory if it doesn't exist
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # Check if credentials file exists
    if not os.path.exists(CREDENTIALS_FILE):
        # Check environment variables first
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
        
        if not client_id or not client_secret:
            # Prompt for credentials
            print("Spotify API credentials not found.")
            print("Please enter your Spotify API credentials:")
            
            try:
                if not client_id:
                    client_id = input("Client ID: ").strip()
                if not client_secret:
                    client_secret = input("Client Secret: ").strip()
                if not redirect_uri:
                    redirect_uri = input("Redirect URI [http://127.0.0.1:8888/callback]: ").strip()
                
                if not redirect_uri:
                    redirect_uri = "http://127.0.0.1:8888/callback"
            except EOFError:
                # Handle case where input is not available (like in tests)
                return None, None, None
        
        # Save credentials
        credentials = {
            "SPOTIFY_CLIENT_ID": client_id,
            "SPOTIFY_CLIENT_SECRET": client_secret,
            "SPOTIFY_REDIRECT_URI": redirect_uri
        }
        
        # Set secure file permissions before writing
        old_umask = os.umask(0o077)
        try:
            with open(CREDENTIALS_FILE, "w") as f:
                json.dump(credentials, f, indent=2)
            os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
        finally:
            os.umask(old_umask)
        
        return client_id, client_secret, redirect_uri
    
    # Load credentials from file
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            credentials = json.load(f)
        
        client_id = credentials.get("SPOTIFY_CLIENT_ID", "")
        client_secret = credentials.get("SPOTIFY_CLIENT_SECRET", "")
        redirect_uri = credentials.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
        
        # Check if credentials are valid
        if not client_id or not client_secret:
            raise ValueError("Invalid Spotify credentials")
        
        return client_id, client_secret, redirect_uri
    
    except Exception as e:
        print(f"Error loading Spotify credentials: {e}")
        
        # Prompt for credentials
        print("Please enter your Spotify API credentials:")
        
        client_id = input("Client ID: ").strip()
        client_secret = input("Client Secret: ").strip()
        redirect_uri = input("Redirect URI [http://127.0.0.1:8888/callback]: ").strip()
        
        if not redirect_uri:
            redirect_uri = "http://127.0.0.1:8888/callback"
        
        # Save credentials
        credentials = {
            "SPOTIFY_CLIENT_ID": client_id,
            "SPOTIFY_CLIENT_SECRET": client_secret,
            "SPOTIFY_REDIRECT_URI": redirect_uri
        }
        
        # Set secure file permissions before writing
        old_umask = os.umask(0o077)
        try:
            with open(CREDENTIALS_FILE, "w") as f:
                json.dump(credentials, f, indent=2)
            os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
        finally:
            os.umask(old_umask)
        
        return client_id, client_secret, redirect_uri

def get_lastfm_api_key():
    """
    Get Last.fm API key.
    
    Returns:
        str: Last.fm API key
    """
    # Create config directory if it doesn't exist
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # Check if credentials file exists
    if not os.path.exists(CREDENTIALS_FILE):
        # Check environment variable first
        api_key = os.environ.get("LASTFM_API_KEY", "")
        
        if not api_key:
            # Prompt for API key
            print("Last.fm API key not found.")
            print("Please enter your Last.fm API key:")
            
            try:
                api_key = input("API Key: ").strip()
            except EOFError:
                # Handle case where input is not available (like in tests)
                return None
        
        # Save credentials
        credentials = {
            "LASTFM_API_KEY": api_key
        }
        
        # Set secure file permissions before writing
        old_umask = os.umask(0o077)
        try:
            with open(CREDENTIALS_FILE, "w") as f:
                json.dump(credentials, f, indent=2)
            os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
        finally:
            os.umask(old_umask)
        
        return api_key
    
    # Load credentials from file
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            credentials = json.load(f)
        
        api_key = credentials.get("LASTFM_API_KEY", "")
        
        # If API key is not found or empty, check environment first
        if not api_key:
            api_key = os.environ.get("LASTFM_API_KEY", "")
            
            if not api_key:
                print("Last.fm API key not found.")
                print("Please enter your Last.fm API key:")
                
                try:
                    api_key = input("API Key: ").strip()
                    
                    # Update credentials
                    credentials["LASTFM_API_KEY"] = api_key
                    
                    # Set secure file permissions before writing
                    old_umask = os.umask(0o077)
                    try:
                        with open(CREDENTIALS_FILE, "w") as f:
                            json.dump(credentials, f, indent=2)
                        os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
                    finally:
                        os.umask(old_umask)
                except EOFError:
                    # Handle case where input is not available (like in tests)
                    return None
        
        return api_key
    
    except Exception as e:
        print(f"Error loading Last.fm API key: {e}")
        
        # Check environment variable first
        api_key = os.environ.get("LASTFM_API_KEY", "")
        
        if not api_key:
            # Prompt for API key
            print("Please enter your Last.fm API key:")
            
            try:
                api_key = input("API Key: ").strip()
            except EOFError:
                # Handle case where input is not available (like in tests)
                return None
        
        # Save credentials
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                credentials = json.load(f)
        except:
            credentials = {}
        
        credentials["LASTFM_API_KEY"] = api_key
        
        # Set secure file permissions before writing
        old_umask = os.umask(0o077)
        try:
            with open(CREDENTIALS_FILE, "w") as f:
                json.dump(credentials, f, indent=2)
            os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
        finally:
            os.umask(old_umask)
        
        return api_key

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
    except:
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
    """Get all credentials from file and environment."""
    credentials = {}
    
    # Load from file if exists
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                credentials = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load credentials file: {e}")
    
    # Override with environment variables if they exist
    env_vars = [
        'SPOTIFY_CLIENT_ID',
        'SPOTIFY_CLIENT_SECRET', 
        'SPOTIFY_REDIRECT_URI',
        'LASTFM_API_KEY',
        'SONGKICK_API_KEY',
        # AI service credentials
        'GEMINI_API_KEY',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'PERPLEXITY_API_KEY'
    ]
    
    for var in env_vars:
        if var in os.environ:
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
