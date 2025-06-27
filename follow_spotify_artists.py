#!/usr/bin/env python3
"""
Script to follow all artists from your Spotify playlists and add all songs to Liked Songs.
This script uses the Spotify Web API to:
1. Authenticate with your Spotify account
2. Fetch all your playlists
3. Extract unique artists from those playlists
4. Follow all those artists
5. Add all songs from your playlists to your Liked Songs collection

Requirements:
- Python 3.6+
- spotipy library (pip install spotipy)
"""

import os
import sys
import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from collections import defaultdict

# Spotify API scopes needed for this script
SCOPES = [
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "user-follow-modify"
]

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        # Check for environment variables first
        client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
        redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
        
        # If environment variables aren't set, prompt the user
        if not client_id:
            client_id = input("Enter your Spotify Client ID: ")
        if not client_secret:
            client_secret = input("Enter your Spotify Client Secret: ")
        
        # Set up authentication
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=" ".join(SCOPES)
        )
        
        return spotipy.Spotify(auth_manager=auth_manager)
    
    except Exception as e:
        print(f"Error setting up Spotify client: {e}")
        print("\nTo set up a Spotify Developer account and create an app:")
        print("1. Go to https://developer.spotify.com/dashboard/")
        print("2. Log in and create a new app")
        print("3. Set the redirect URI to http://localhost:8888/callback")
        print("4. Copy the Client ID and Client Secret")
        sys.exit(1)

def get_all_playlists(sp):
    """Get all playlists for the authenticated user."""
    playlists = []
    offset = 0
    limit = 50
    
    while True:
        results = sp.current_user_playlists(limit=limit, offset=offset)
        if not results['items']:
            break
        
        playlists.extend(results['items'])
        offset += limit
        
        if len(results['items']) < limit:
            break
    
    return playlists

def get_playlist_tracks(sp, playlist_id):
    """Get all tracks from a playlist."""
    tracks = []
    offset = 0
    limit = 100
    
    while True:
        results = sp.playlist_items(
            playlist_id, 
            fields="items(track(id,name,artists(id,name))),next",
            limit=limit,
            offset=offset
        )
        
        if not results['items']:
            break
        
        tracks.extend([item['track'] for item in results['items'] if item['track'] and item['track'].get('id')])
        offset += limit
        
        if len(results['items']) < limit:
            break
    
    return tracks

def extract_artists(tracks):
    """Extract unique artists from a list of tracks."""
    artists = {}
    
    for track in tracks:
        if track and 'artists' in track:
            for artist in track['artists']:
                if artist and 'id' in artist and artist['id']:
                    artists[artist['id']] = artist['name']
    
    return artists

def add_tracks_to_liked_songs(sp, track_ids):
    """Add tracks to user's Liked Songs (Saved Tracks)."""
    # Spotify API allows saving up to 50 tracks at a time
    chunk_size = 50
    
    for i in range(0, len(track_ids), chunk_size):
        chunk = track_ids[i:i + chunk_size]
        try:
            sp.current_user_saved_tracks_add(chunk)
            print(f"Added tracks {i+1}-{i+len(chunk)} of {len(track_ids)} to Liked Songs")
            # Add a small delay to avoid hitting rate limits
            time.sleep(1)
        except Exception as e:
            print(f"Error adding tracks {i+1}-{i+len(chunk)} to Liked Songs: {e}")

def get_already_liked_tracks(sp):
    """Get a set of track IDs that are already in the user's Liked Songs."""
    liked_track_ids = set()
    offset = 0
    limit = 50
    
    print("Fetching your existing Liked Songs...")
    while True:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        if not results['items']:
            break
        
        for item in results['items']:
            if item['track'] and item['track'].get('id'):
                liked_track_ids.add(item['track']['id'])
        
        offset += limit
        if len(results['items']) < limit:
            break
        
        # Show progress for large libraries
        if offset % 500 == 0:
            print(f"Processed {offset} liked songs so far...")
    
    print(f"Found {len(liked_track_ids)} existing liked songs")
    return liked_track_ids

def follow_artists(sp, artist_ids):
    """Follow a list of artists."""
    # Spotify API allows following up to 50 artists at a time
    chunk_size = 50
    
    for i in range(0, len(artist_ids), chunk_size):
        chunk = artist_ids[i:i + chunk_size]
        try:
            sp.user_follow_artists(chunk)
            print(f"Followed artists {i+1}-{i+len(chunk)} of {len(artist_ids)}")
            # Add a small delay to avoid hitting rate limits
            time.sleep(1)
        except Exception as e:
            print(f"Error following artists {i+1}-{i+len(chunk)}: {e}")

def main():
    print("Setting up Spotify client...")
    sp = setup_spotify_client()
    
    print("Fetching your playlists...")
    playlists = get_all_playlists(sp)
    print(f"Found {len(playlists)} playlists")
    
    # Ask user what they want to do
    print("\nWhat would you like to do?")
    print("1. Follow all artists in your playlists")
    print("2. Add all songs from playlists to Liked Songs")
    print("3. Both")
    
    choice = input("Enter your choice (1-3): ")
    
    follow_artists_option = choice in ['1', '3']
    add_songs_option = choice in ['2', '3']
    
    all_artists = {}
    all_tracks = []
    playlist_artist_counts = defaultdict(int)
    playlist_track_counts = defaultdict(int)
    
    for i, playlist in enumerate(playlists, 1):
        print(f"Processing playlist {i}/{len(playlists)}: {playlist['name']}")
        tracks = get_playlist_tracks(sp, playlist['id'])
        artists = extract_artists(tracks)
        
        playlist_artist_counts[playlist['name']] = len(artists)
        playlist_track_counts[playlist['name']] = len(tracks)
        
        all_artists.update(artists)
        all_tracks.extend(tracks)
    
    # Get unique tracks by ID
    unique_tracks = {}
    for track in all_tracks:
        if track and 'id' in track and track['id']:
            unique_tracks[track['id']] = track
    
    print("\nArtist count by playlist:")
    for playlist_name, count in playlist_artist_counts.items():
        print(f"- {playlist_name}: {count} artists, {playlist_track_counts[playlist_name]} tracks")
    
    print(f"\nFound {len(all_artists)} unique artists across all playlists")
    print(f"Found {len(unique_tracks)} unique tracks across all playlists")
    
    # Follow artists if requested
    if follow_artists_option and all_artists:
        confirm = input(f"\nDo you want to follow all {len(all_artists)} artists? (y/n): ")
        if confirm.lower() == 'y':
            print("Following artists...")
            follow_artists(sp, list(all_artists.keys()))
            print("Done following artists!")
        else:
            print("Skipping artist following.")
    
    # Add tracks to liked songs if requested
    if add_songs_option and unique_tracks:
        # Get already liked tracks to avoid duplicates
        already_liked = get_already_liked_tracks(sp)
        
        # Filter out tracks that are already liked
        new_tracks_to_like = [track_id for track_id in unique_tracks.keys() if track_id not in already_liked]
        
        print(f"\nFound {len(new_tracks_to_like)} tracks that aren't in your Liked Songs yet")
        
        if new_tracks_to_like:
            confirm = input(f"Do you want to add these {len(new_tracks_to_like)} tracks to your Liked Songs? (y/n): ")
            if confirm.lower() == 'y':
                print("Adding tracks to Liked Songs...")
                add_tracks_to_liked_songs(sp, new_tracks_to_like)
                print("Done adding tracks to Liked Songs!")
            else:
                print("Skipping adding tracks to Liked Songs.")
        else:
            print("No new tracks to add to Liked Songs.")
    
    print("All operations completed successfully!")

if __name__ == "__main__":
    main()
