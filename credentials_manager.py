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
        # Prompt for credentials
        print("Spotify API credentials not found.")
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
        
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(credentials, f, indent=2)
        
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
        
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(credentials, f, indent=2)
        
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
        # Prompt for API key
        print("Last.fm API key not found.")
        print("Please enter your Last.fm API key:")
        
        api_key = input("API Key: ").strip()
        
        # Save credentials
        credentials = {
            "LASTFM_API_KEY": api_key
        }
        
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(credentials, f, indent=2)
        
        return api_key
    
    # Load credentials from file
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            credentials = json.load(f)
        
        api_key = credentials.get("LASTFM_API_KEY", "")
        
        # If API key is not found or empty, prompt for it
        if not api_key:
            print("Last.fm API key not found.")
            print("Please enter your Last.fm API key:")
            
            api_key = input("API Key: ").strip()
            
            # Update credentials
            credentials["LASTFM_API_KEY"] = api_key
            
            with open(CREDENTIALS_FILE, "w") as f:
                json.dump(credentials, f, indent=2)
        
        return api_key
    
    except Exception as e:
        print(f"Error loading Last.fm API key: {e}")
        
        # Prompt for API key
        print("Please enter your Last.fm API key:")
        
        api_key = input("API Key: ").strip()
        
        # Save credentials
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                credentials = json.load(f)
        except:
            credentials = {}
        
        credentials["LASTFM_API_KEY"] = api_key
        
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(credentials, f, indent=2)
        
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
    
    # Save to file
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(existing_credentials, f, indent=2)
