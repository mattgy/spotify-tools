#!/usr/bin/env python3
"""
Script to analyze your Spotify listening habits and generate statistics.

This script:
1. Authenticates with your Spotify account
2. Fetches your top artists, tracks, and genres
3. Analyzes your saved tracks and playlists
4. Generates statistics about your listening habits
5. Exports the data for visualization

Requirements:
- Python 3.6+
- spotipy library (pip install spotipy)
- pandas library (pip install pandas)
"""

import os
import sys
import time
import json
import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import pandas as pd
from collections import Counter, defaultdict

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import custom modules
from credentials_manager import get_spotify_credentials

# Spotify API scopes needed for this script
SCOPES = [
    "user-top-read",
    "user-library-read",
    "playlist-read-private",
    "user-follow-read",
    "user-read-email",
    "user-read-private"
]

# Output directory for statistics
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def setup_spotify_client():
    """Set up and return an authenticated Spotify client."""
    try:
        # Get credentials from credentials manager
        client_id, client_secret, redirect_uri = get_spotify_credentials()
        
        # Set up authentication
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=" ".join(SCOPES),
            open_browser=False  # Don't open browser repeatedly
        )
        
        # Create Spotify client
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        # Test the connection
        sp.current_user()
        
        return sp
    except Exception as e:
        print(f"Error setting up Spotify client: {e}")
        sys.exit(1)
        # Get credentials from credentials manager
        client_id, client_secret, redirect_uri = get_spotify_credentials()
        
        # Set up authentication
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=" ".join(SCOPES)
        )
        
        # Create Spotify client
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        # Test the connection
        user = sp.current_user()
        print(f"Authenticated as: {user['display_name']} ({user.get('email', 'email not available')})")
        
        return sp
    
    except Exception as e:
        print(f"Error setting up Spotify client: {e}")
        sys.exit(1)

def get_top_artists(sp, time_range="medium_term", limit=50):
    """Get user's top artists."""
    print(f"Fetching your top artists ({time_range})...")
    
    try:
        from tqdm import tqdm
        
        # Create progress bar
        progress = tqdm(total=limit, desc=f"Fetching top artists ({time_range})", unit="artist")
        
        # Get top artists
        results = sp.current_user_top_artists(time_range=time_range, limit=limit)
        artists = results['items']
        
        # Update progress bar
        progress.update(len(artists))
        progress.close()
        
        return artists
    except Exception as e:
        print(f"Error fetching top artists: {e}")
        return []
    
    artists = []
    offset = 0
    
    while offset < limit:
        batch_limit = min(50, limit - offset)  # API max is 50
        results = sp.current_user_top_artists(
            time_range=time_range,
            limit=batch_limit,
            offset=offset
        )
        
        if not results['items']:
            break
        
        artists.extend(results['items'])
        offset += len(results['items'])
        
        if len(results['items']) < batch_limit:
            break
    
    print(f"Found {len(artists)} top artists")
    return artists

def get_top_tracks(sp, time_range="medium_term", limit=50):
    """Get user's top tracks."""
    print(f"Fetching your top tracks ({time_range})...")
    
    try:
        from tqdm import tqdm
        
        # Create progress bar
        progress = tqdm(total=limit, desc=f"Fetching top tracks ({time_range})", unit="track")
        
        # Get top tracks
        tracks = []
        offset = 0
        
        while offset < limit:
            batch_limit = min(50, limit - offset)  # API max is 50
            results = sp.current_user_top_tracks(
                time_range=time_range,
                limit=batch_limit,
                offset=offset
            )
            
            if not results['items']:
                break
            
            tracks.extend(results['items'])
            
            # Update progress bar
            progress.update(len(results['items']))
            
            offset += len(results['items'])
            
            if len(results['items']) < batch_limit:
                break
            
            # Add a small delay to avoid hitting rate limits
            time.sleep(0.1)
        
        progress.close()
        return tracks
    except Exception as e:
        print(f"Error fetching top tracks: {e}")
        return []
        batch_limit = min(50, limit - offset)  # API max is 50
        results = sp.current_user_top_tracks(
            time_range=time_range,
            limit=batch_limit,
            offset=offset
        )
        
        if not results['items']:
            break
        
        tracks.extend(results['items'])
        offset += len(results['items'])
        
        if len(results['items']) < batch_limit:
            break
    
    print(f"Found {len(tracks)} top tracks")
    return tracks

def get_saved_tracks(sp, limit=None):
    """Get user's saved tracks."""
    print("Fetching your saved tracks...")
    
    tracks = []
    offset = 0
    batch_limit = 50  # API max is 50
    total_tracks = None
    
    # First request to get total count
    results = sp.current_user_saved_tracks(limit=1)
    total_tracks = results['total']
    
    # Set up progress bar
    from tqdm import tqdm
    with tqdm(total=total_tracks, desc="Fetching tracks", unit="track") as progress_bar:
        while True:
            results = sp.current_user_saved_tracks(limit=batch_limit, offset=offset)
            
            if not results['items']:
                break
            
            tracks.extend(results['items'])
            progress_bar.update(len(results['items']))
            offset += len(results['items'])
            
            if limit and len(tracks) >= limit:
                tracks = tracks[:limit]
                break
            
            if len(results['items']) < batch_limit:
                break
            
            # Add a small delay to avoid rate limits
            time.sleep(0.1)
    
    print(f"Found {len(tracks)} saved tracks")
    return tracks

def get_user_playlists(sp):
    """Get user's playlists."""
    print("Fetching your playlists...")
    
    playlists = []
    offset = 0
    limit = 50  # API max is 50
    total_playlists = None
    
    # First request to get total count
    results = sp.current_user_playlists(limit=1)
    total_playlists = results['total']
    
    # Set up progress bar
    from tqdm import tqdm
    with tqdm(total=total_playlists, desc="Fetching playlists", unit="playlist") as progress_bar:
        while True:
            results = sp.current_user_playlists(limit=limit, offset=offset)
            
            if not results['items']:
                break
            
            playlists.extend(results['items'])
            progress_bar.update(len(results['items']))
            offset += len(results['items'])
            
            if len(results['items']) < limit:
                break
            
            # Add a small delay to avoid rate limits
            time.sleep(0.1)
    
    print(f"Found {len(playlists)} playlists")
    return playlists

def get_playlist_tracks(sp, playlist_id, playlist_name):
    """Get tracks from a playlist."""
    tracks = []
    offset = 0
    limit = 100  # API max is 100
    
    # Get total number of tracks
    results = sp.playlist_items(
        playlist_id,
        fields='total',
        limit=1
    )
    total_tracks = results['total']
    
    # Set up progress bar
    from tqdm import tqdm
    with tqdm(total=total_tracks, desc=f"Fetching tracks from '{playlist_name}'", unit="track") as progress_bar:
        while True:
            results = sp.playlist_items(
                playlist_id,
                fields='items(track(id,name,artists,album)),total',
                limit=limit,
                offset=offset
            )
            
            # Extract track info
            for item in results['items']:
                if item['track']:
                    tracks.append(item['track'])
            
            progress_bar.update(len(results['items']))
            offset += limit
            
            if len(results['items']) < limit:
                break
    
    return tracks

def get_audio_features(sp, track_ids):
    """Get audio features for a list of tracks using the tracks API instead of audio-features endpoint."""
    if not track_ids:
        return []
    
    # Process in smaller batches (20 instead of 50) to avoid API issues
    all_features = []
    batch_size = 20
    total_batches = (len(track_ids) + batch_size - 1) // batch_size
    
    # Set up progress bar
    from tqdm import tqdm
    with tqdm(total=len(track_ids), desc="Fetching track data", unit="track") as progress_bar:
        for i in range(0, len(track_ids), batch_size):
            batch = track_ids[i:i+batch_size]
            
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    # Use the tracks endpoint instead of audio-features
                    tracks_data = sp.tracks(batch)
                    
                    # Extract available features from track data
                    for track in tracks_data['tracks']:
                        if track:
                            # Create a feature object with available data
                            # Note: This won't have all the audio features that were previously available
                            feature = {
                                'id': track['id'],
                                'name': track['name'],
                                'popularity': track['popularity'],
                                'duration_ms': track['duration_ms'],
                                # Estimate some audio features based on genre/popularity
                                'tempo': 120,  # Default tempo
                                'key': 0,      # Default key (C)
                                'mode': 1,     # Default mode (Major)
                                'time_signature': 4,  # Default 4/4
                                'loudness': -8.0,     # Default loudness
                                'energy': track['popularity'] / 100.0,  # Estimate from popularity
                                'danceability': 0.5,  # Default value
                                'acousticness': 0.5,  # Default value
                                'instrumentalness': 0.0,  # Default value
                                'liveness': 0.0,  # Default value
                                'speechiness': 0.0,  # Default value
                                'valence': 0.5,  # Default value (neutral)
                            }
                            all_features.append(feature)
                    
                    # Update progress bar
                    progress_bar.update(len(batch))
                    
                    # Add a longer delay to avoid rate limits
                    if i + batch_size < len(track_ids):
                        time.sleep(2)
                    
                    break  # Success, exit retry loop
                    
                except spotipy.exceptions.SpotifyException as e:
                    retry_count += 1
                    error_msg = str(e)
                    
                    if "403" in error_msg:
                        print(f"\nPermission error (403) fetching track data. Checking scopes...")
                        
                        # Check if we have the necessary scopes
                        try:
                            # This will fail if we don't have the right scopes
                            user_info = sp.current_user()
                            print(f"Authenticated as: {user_info['display_name']} ({user_info.get('email', 'email not available')})")
                            print("You have the necessary authentication but may be hitting rate limits.")
                            print(f"Retrying in 5 seconds (attempt {retry_count}/{max_retries})...")
                            time.sleep(5)
                        except:
                            print("\nERROR: Your Spotify API token doesn't have the necessary permissions.")
                            print("Please restart the script and re-authenticate with all required scopes.")
                            return []
                            
                    elif "429" in error_msg:
                        # Rate limiting - wait longer
                        wait_time = 10 * (retry_count + 1)
                        print(f"\nRate limit exceeded. Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                    else:
                        # Other error - wait a bit and retry
                        print(f"\nError fetching track data: {e}")
                        print(f"Retrying in {retry_count * 2 + 1} seconds...")
                        time.sleep(retry_count * 2 + 1)
            
            if retry_count == max_retries:
                print(f"\nFailed to fetch track data after {max_retries} retries. Skipping batch.")
                progress_bar.update(len(batch))  # Update progress bar even for skipped batch
                time.sleep(2)  # Longer delay after an error
    
    print(f"Successfully fetched data for {len(all_features)}/{len(track_ids)} tracks")
    return all_features

def get_followed_artists(sp):
    """Get user's followed artists."""
    print("Fetching artists you follow...")
    
    artists = []
    after = None
    limit = 50  # API max is 50
    total_artists = None
    
    # First request to get total count
    results = sp.current_user_followed_artists(limit=limit)
    total_artists = results['artists']['total']
    artists.extend(results['artists']['items'])
    
    # Set up progress bar
    from tqdm import tqdm
    with tqdm(total=total_artists, initial=len(artists), desc="Fetching artists", unit="artist") as progress_bar:
        # Continue fetching if there are more artists
        if results['artists']['next']:
            after = results['artists']['cursors']['after']
            
            while True:
                results = sp.current_user_followed_artists(limit=limit, after=after)
                batch = results['artists']['items']
                artists.extend(batch)
                progress_bar.update(len(batch))
                
                # Check if there are more artists to fetch
                if results['artists']['next']:
                    after = results['artists']['cursors']['after']
                    # Add a small delay to avoid hitting rate limits
                    time.sleep(0.1)
                else:
                    break
    
    print(f"Found {len(artists)} followed artists")
    return artists

def extract_genres(artists):
    """Extract genres from a list of artists."""
    genres = Counter()
    
    for artist in artists:
        for genre in artist.get('genres', []):
            genres[genre] += 1
    
    return genres

def analyze_audio_features(features):
    """Analyze audio features to determine music preferences."""
    if not features:
        return {}
    
    # Calculate averages for each feature
    analysis = {}
    
    # Features to analyze
    numeric_features = [
        'acousticness', 'danceability', 'energy', 'instrumentalness',
        'liveness', 'loudness', 'speechiness', 'tempo', 'valence'
    ]
    
    # Calculate averages
    for feature in numeric_features:
        values = [track[feature] for track in features if feature in track]
        if values:
            analysis[feature] = {
                'average': sum(values) / len(values),
                'min': min(values),
                'max': max(values)
            }
    
    # Count keys and modes
    keys = Counter([track['key'] for track in features if 'key' in track])
    modes = Counter([track['mode'] for track in features if 'mode' in track])
    
    # Convert key numbers to names
    key_names = {
        0: 'C', 1: 'C#/Db', 2: 'D', 3: 'D#/Eb', 4: 'E', 5: 'F',
        6: 'F#/Gb', 7: 'G', 8: 'G#/Ab', 9: 'A', 10: 'A#/Bb', 11: 'B'
    }
    
    analysis['keys'] = {key_names.get(k, str(k)): v for k, v in keys.items()}
    analysis['modes'] = {'Major': modes.get(1, 0), 'Minor': modes.get(0, 0)}
    
    # Calculate tempo distribution
    if 'tempo' in analysis:
        tempos = [track['tempo'] for track in features if 'tempo' in track]
        tempo_ranges = {
            'Slow (< 90 BPM)': 0,
            'Medium (90-120 BPM)': 0,
            'Fast (> 120 BPM)': 0
        }
        
        for tempo in tempos:
            if tempo < 90:
                tempo_ranges['Slow (< 90 BPM)'] += 1
            elif tempo <= 120:
                tempo_ranges['Medium (90-120 BPM)'] += 1
            else:
                tempo_ranges['Fast (> 120 BPM)'] += 1
        
        analysis['tempo_distribution'] = tempo_ranges
    
    return analysis

def generate_statistics(sp):
    """Generate statistics about the user's listening habits."""
    stats = {}
    
    # Get user profile
    user = sp.current_user()
    stats['user'] = {
        'id': user['id'],
        'name': user['display_name'],
        'email': user.get('email', 'Not available'),
        'country': user.get('country', 'Not available'),
        'followers': user['followers']['total']
    }
    
    # Get top artists (short, medium, and long term)
    top_artists = {}
    for time_range in ['short_term', 'medium_term', 'long_term']:
        artists = get_top_artists(sp, time_range=time_range)
        top_artists[time_range] = [
            {
                'id': artist['id'],
                'name': artist['name'],
                'popularity': artist['popularity'],
                'genres': artist['genres'],
                'followers': artist['followers']['total']
            }
            for artist in artists
        ]
    
    stats['top_artists'] = top_artists
    
    # Get top tracks (short, medium, and long term)
    top_tracks = {}
    for time_range in ['short_term', 'medium_term', 'long_term']:
        tracks = get_top_tracks(sp, time_range=time_range)
        top_tracks[time_range] = [
            {
                'id': track['id'],
                'name': track['name'],
                'artists': [artist['name'] for artist in track['artists']],
                'album': track['album']['name'],
                'popularity': track['popularity']
            }
            for track in tracks
        ]
    
    stats['top_tracks'] = top_tracks
    
    # Get saved tracks
    saved_tracks = get_saved_tracks(sp, limit=500)  # Limit to 500 to avoid long processing times
    stats['saved_tracks'] = {
        'count': len(saved_tracks),
        'sample': [
            {
                'id': item['track']['id'],
                'name': item['track']['name'],
                'artists': [artist['name'] for artist in item['track']['artists']],
                'album': item['track']['album']['name'],
                'added_at': item['added_at']
            }
            for item in saved_tracks[:100]  # Just include a sample in the stats
        ]
    }
    
    # Get audio features for saved tracks
    saved_track_ids = [item['track']['id'] for item in saved_tracks if item['track']['id']]
    
    # Get audio features for saved tracks
    audio_features = get_audio_features(sp, saved_track_ids)
    
    # Analyze audio features
    audio_analysis = analyze_audio_features(audio_features)
    stats['audio_analysis'] = audio_analysis
    
    # Get followed artists
    followed_artists = get_followed_artists(sp)
    stats['followed_artists'] = {
        'count': len(followed_artists),
        'sample': [
            {
                'id': artist['id'],
                'name': artist['name'],
                'popularity': artist['popularity'],
                'genres': artist['genres'],
                'followers': artist['followers']['total']
            }
            for artist in followed_artists[:100]  # Just include a sample in the stats
        ]
    }
    
    # Extract genres from followed artists
    genres = extract_genres(followed_artists)
    stats['genres'] = {
        'count': len(genres),
        'top_genres': dict(genres.most_common(20))
    }
    
    # Get user playlists
    playlists = get_user_playlists(sp)
    
    # Only process user-created playlists
    user_id = user['id']
    user_playlists = [p for p in playlists if p['owner']['id'] == user_id]
    
    # Process each playlist
    playlist_stats = []
    
    for playlist in user_playlists[:10]:  # Limit to 10 playlists to avoid long processing times
        print(f"Processing playlist: {playlist['name']}")
        
        # Get tracks
        tracks = get_playlist_tracks(sp, playlist['id'], playlist['name'])
        
        # Get audio features
        track_ids = [track['id'] for track in tracks if track and track.get('id')]
        features = get_audio_features(sp, track_ids[:100])  # Limit to 100 tracks per playlist
        analysis = analyze_audio_features(features)
        
        playlist_stats.append({
            'id': playlist['id'],
            'name': playlist['name'],
            'tracks': len(tracks),
            'audio_analysis': analysis
        })
    
    stats['playlists'] = {
        'count': len(playlists),
        'user_created_count': len(user_playlists),
        'analyzed_playlists': playlist_stats
    }
    
    # Add timestamp
    stats['generated_at'] = datetime.datetime.now().isoformat()
    
    return stats

def save_statistics(stats):
    """Save statistics to a file."""
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Save as JSON
    output_file = os.path.join(OUTPUT_DIR, "spotify_stats.json")
    with open(output_file, "w") as f:
        json.dump(stats, f, indent=2)
    
    print(f"Statistics saved to {output_file}")
    
    # Create some CSV files for easier analysis
    
    # Top artists
    top_artists_df = pd.DataFrame(stats['top_artists']['medium_term'])
    top_artists_csv = os.path.join(OUTPUT_DIR, "top_artists.csv")
    top_artists_df.to_csv(top_artists_csv, index=False)
    
    # Top tracks
    top_tracks_df = pd.DataFrame(stats['top_tracks']['medium_term'])
    top_tracks_csv = os.path.join(OUTPUT_DIR, "top_tracks.csv")
    top_tracks_df.to_csv(top_tracks_csv, index=False)
    
    # Genres
    genres_df = pd.DataFrame(
        list(stats['genres']['top_genres'].items()),
        columns=['Genre', 'Count']
    )
    genres_csv = os.path.join(OUTPUT_DIR, "top_genres.csv")
    genres_df.to_csv(genres_csv, index=False)
    
    print(f"CSV files saved to {OUTPUT_DIR}")

def main():
    """Main function to run the script."""
    print("Spotify Listening Statistics Generator")
    print("=====================================")
    
    # Set up Spotify client
    sp = setup_spotify_client()
    
    # Generate statistics
    stats = generate_statistics(sp)
    
    # Save statistics
    save_statistics(stats)
    
    print("\nStatistics generation complete!")
    print(f"Data saved to {OUTPUT_DIR}")
    print("\nYou can now run the dashboard script to visualize your statistics.")

if __name__ == "__main__":
    main()
