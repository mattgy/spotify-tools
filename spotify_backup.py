#!/usr/bin/env python3
"""
Backup and Migration Tools for Spotify library data.
Creates portable backups of playlists, followed artists, and liked songs.
"""

import os
import sys
import json
import csv
import datetime
import time
from pathlib import Path
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from credentials_manager import get_spotify_credentials
from cache_utils import save_to_cache, load_from_cache
from config import config, get_cache_expiration, get_batch_size
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

# Spotify API scopes needed
SPOTIFY_SCOPES = [
    "user-library-read",
    "playlist-read-private",
    "user-follow-read",
    "user-read-email",
    "user-read-private"
]

class SpotifyBackup:
    """Comprehensive Spotify library backup system."""
    
    def __init__(self):
        self.sp = self._setup_spotify_client()
        self.backup_dir = os.path.join(str(Path.home()), ".spotify-tools", "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        
    def _setup_spotify_client(self):
        """Set up authenticated Spotify client."""
        from spotify_utils import create_spotify_client
        
        try:
            return create_spotify_client(SPOTIFY_SCOPES, "backup")
        except Exception as e:
            print(f"{Fore.RED}Authentication error: {e}")
            return None
    
    def create_full_backup(self) -> str:
        """Create a complete backup of user's Spotify library."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"spotify_backup_{timestamp}"
        backup_path = os.path.join(self.backup_dir, backup_name)
        os.makedirs(backup_path, exist_ok=True)
        
        print(f"{Fore.CYAN}🔄 Creating full Spotify library backup...")
        print(f"{Fore.BLUE}Backup location: {backup_path}")
        
        # Get user profile
        user_profile = self.sp.current_user()
        
        backup_data = {
            'backup_info': {
                'created_at': timestamp,
                'user_id': user_profile.get('id'),
                'user_name': user_profile.get('display_name'),
                'user_email': user_profile.get('email'),
                'backup_version': '1.0'
            },
            'playlists': [],
            'followed_artists': [],
            'liked_songs': [],
            'top_artists': {},
            'top_tracks': {}
        }
        
        # Backup playlists
        print(f"{Fore.YELLOW}📋 Backing up playlists...")
        backup_data['playlists'] = self._backup_playlists()
        
        # Backup followed artists
        print(f"{Fore.YELLOW}👥 Backing up followed artists...")
        backup_data['followed_artists'] = self._backup_followed_artists()
        
        # Backup liked songs
        print(f"{Fore.YELLOW}❤️ Backing up liked songs...")
        backup_data['liked_songs'] = self._backup_liked_songs()
        
        # Backup top artists and tracks
        print(f"{Fore.YELLOW}🏆 Backing up top artists and tracks...")
        backup_data['top_artists'] = self._backup_top_artists()
        backup_data['top_tracks'] = self._backup_top_tracks()
        
        # Save main backup file
        backup_file = os.path.join(backup_path, "spotify_backup.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        # Create CSV exports for portability
        self._create_csv_exports(backup_data, backup_path)
        
        # Create cross-platform export formats
        print(f"{Fore.BLUE}Creating Apple Music export format...")
        self._create_apple_music_export(backup_data, backup_path)
        
        print(f"{Fore.BLUE}Creating YouTube Music export format...")
        self._create_youtube_music_export(backup_data, backup_path)
        
        print(f"{Fore.BLUE}Creating M3U playlist files...")
        self._create_universal_m3u_export(backup_data, backup_path)
        
        # Create human-readable report
        self._create_backup_report(backup_data, backup_path)
        
        print(f"{Fore.GREEN}✅ Backup completed successfully!")
        print(f"{Fore.BLUE}Backup saved to: {backup_path}")
        
        return backup_path
    
    def _backup_playlists(self) -> list:
        """Backup all user playlists."""
        playlists = []
        
        # Get all user playlists
        results = self.sp.current_user_playlists(limit=50)
        
        while True:
            for playlist in results['items']:
                if playlist is None:
                    continue
                
                print(f"  📋 {playlist['name']}")
                
                playlist_data = {
                    'id': playlist['id'],
                    'name': playlist['name'],
                    'description': playlist.get('description', ''),
                    'public': playlist.get('public', False),
                    'collaborative': playlist.get('collaborative', False),
                    'owner': playlist['owner']['id'],
                    'follower_count': playlist.get('followers', {}).get('total', 0),
                    'track_count': playlist['tracks']['total'],
                    'created_at': datetime.datetime.now().isoformat(),
                    'tracks': []
                }
                
                # Get all tracks in playlist
                track_results = self.sp.playlist_items(playlist['id'], limit=100)
                
                while True:
                    for item in track_results['items']:
                        if item is None or item['track'] is None:
                            continue
                        
                        track = item['track']
                        if track['type'] != 'track':
                            continue
                        
                        track_data = {
                            'name': track['name'],
                            'artists': [artist['name'] for artist in track['artists']],
                            'artist_ids': [artist['id'] for artist in track['artists']],
                            'album': track['album']['name'],
                            'album_id': track['album']['id'],
                            'track_id': track['id'],
                            'duration_ms': track['duration_ms'],
                            'popularity': track.get('popularity', 0),
                            'explicit': track.get('explicit', False),
                            'added_at': item.get('added_at'),
                            'isrc': track.get('external_ids', {}).get('isrc'),
                            'spotify_url': track['external_urls'].get('spotify')
                        }
                        
                        playlist_data['tracks'].append(track_data)
                    
                    if track_results['next']:
                        track_results = self.sp.next(track_results)
                        time.sleep(0.1)  # Rate limiting
                    else:
                        break
                
                playlists.append(playlist_data)
            
            if results['next']:
                results = self.sp.next(results)
                time.sleep(0.1)
            else:
                break
        
        return playlists
    
    def _backup_followed_artists(self) -> list:
        """Backup all followed artists."""
        artists = []
        
        # Get followed artists
        results = self.sp.current_user_followed_artists(limit=50)
        
        while True:
            for artist in results['artists']['items']:
                artist_data = {
                    'id': artist['id'],
                    'name': artist['name'],
                    'genres': artist.get('genres', []),
                    'popularity': artist.get('popularity', 0),
                    'follower_count': artist['followers']['total'],
                    'spotify_url': artist['external_urls'].get('spotify'),
                    'images': [img['url'] for img in artist.get('images', [])],
                    'backed_up_at': datetime.datetime.now().isoformat()
                }
                artists.append(artist_data)
                
                print(f"  👥 {artist['name']}")
            
            if results['artists']['next']:
                results = self.sp.next(results['artists'])
                time.sleep(0.1)
            else:
                break
        
        return artists
    
    def _backup_liked_songs(self) -> list:
        """Backup all liked songs."""
        tracks = []
        
        # Get liked songs
        results = self.sp.current_user_saved_tracks(limit=50)
        
        while True:
            for item in results['items']:
                track = item['track']
                
                track_data = {
                    'name': track['name'],
                    'artists': [artist['name'] for artist in track['artists']],
                    'artist_ids': [artist['id'] for artist in track['artists']],
                    'album': track['album']['name'],
                    'album_id': track['album']['id'],
                    'track_id': track['id'],
                    'duration_ms': track['duration_ms'],
                    'popularity': track.get('popularity', 0),
                    'explicit': track.get('explicit', False),
                    'added_at': item.get('added_at'),
                    'isrc': track.get('external_ids', {}).get('isrc'),
                    'spotify_url': track['external_urls'].get('spotify')
                }
                
                tracks.append(track_data)
                
                if len(tracks) % 100 == 0:
                    print(f"  ❤️ {len(tracks)} liked songs backed up...")
            
            if results['next']:
                results = self.sp.next(results)
                time.sleep(0.1)
            else:
                break
        
        return tracks
    
    def _backup_top_artists(self) -> dict:
        """Backup top artists for different time ranges."""
        top_artists = {}
        time_ranges = ['short_term', 'medium_term', 'long_term']
        
        for time_range in time_ranges:
            print(f"  🏆 Top artists ({time_range})")
            
            results = self.sp.current_user_top_artists(limit=50, time_range=time_range)
            
            artists = []
            for artist in results['items']:
                artist_data = {
                    'id': artist['id'],
                    'name': artist['name'],
                    'genres': artist.get('genres', []),
                    'popularity': artist.get('popularity', 0),
                    'follower_count': artist['followers']['total'],
                    'spotify_url': artist['external_urls'].get('spotify')
                }
                artists.append(artist_data)
            
            top_artists[time_range] = artists
        
        return top_artists
    
    def _backup_top_tracks(self) -> dict:
        """Backup top tracks for different time ranges."""
        top_tracks = {}
        time_ranges = ['short_term', 'medium_term', 'long_term']
        
        for time_range in time_ranges:
            print(f"  🏆 Top tracks ({time_range})")
            
            results = self.sp.current_user_top_tracks(limit=50, time_range=time_range)
            
            tracks = []
            for track in results['items']:
                track_data = {
                    'name': track['name'],
                    'artists': [artist['name'] for artist in track['artists']],
                    'album': track['album']['name'],
                    'track_id': track['id'],
                    'popularity': track.get('popularity', 0),
                    'duration_ms': track['duration_ms'],
                    'spotify_url': track['external_urls'].get('spotify')
                }
                tracks.append(track_data)
            
            top_tracks[time_range] = tracks
        
        return top_tracks
    
    def _create_csv_exports(self, backup_data: dict, backup_path: str):
        """Create CSV exports for maximum portability."""
        
        # Export playlists summary
        playlists_csv = os.path.join(backup_path, "playlists_summary.csv")
        with open(playlists_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Name', 'Description', 'Owner', 'Track Count', 'Public', 'Collaborative'])
            
            for playlist in backup_data['playlists']:
                writer.writerow([
                    playlist['name'],
                    playlist['description'],
                    playlist['owner'],
                    playlist['track_count'],
                    playlist['public'],
                    playlist['collaborative']
                ])
        
        # Export all tracks from all playlists
        all_tracks_csv = os.path.join(backup_path, "all_playlist_tracks.csv")
        with open(all_tracks_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Playlist', 'Track', 'Artists', 'Album', 'Duration', 'Added Date', 'ISRC'])
            
            for playlist in backup_data['playlists']:
                for track in playlist['tracks']:
                    writer.writerow([
                        playlist['name'],
                        track['name'],
                        ', '.join(track['artists']),
                        track['album'],
                        track['duration_ms'],
                        track['added_at'],
                        track.get('isrc', '')
                    ])
        
        # Export followed artists
        artists_csv = os.path.join(backup_path, "followed_artists.csv")
        with open(artists_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Name', 'Genres', 'Popularity', 'Followers', 'Spotify URL'])
            
            for artist in backup_data['followed_artists']:
                writer.writerow([
                    artist['name'],
                    ', '.join(artist['genres']),
                    artist['popularity'],
                    artist['follower_count'],
                    artist['spotify_url']
                ])
        
        # Export liked songs
        liked_csv = os.path.join(backup_path, "liked_songs.csv")
        with open(liked_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Track', 'Artists', 'Album', 'Duration', 'Added Date', 'ISRC'])
            
            for track in backup_data['liked_songs']:
                writer.writerow([
                    track['name'],
                    ', '.join(track['artists']),
                    track['album'],
                    track['duration_ms'],
                    track['added_at'],
                    track.get('isrc', '')
                ])
    
    def _create_apple_music_export(self, backup_data: dict, backup_path: str):
        """Create Apple Music compatible export format."""
        apple_dir = os.path.join(backup_path, "apple_music_format")
        os.makedirs(apple_dir, exist_ok=True)
        
        # Create Apple Music Library XML-style structure (simplified)
        for playlist in backup_data['playlists']:
            playlist_file = os.path.join(apple_dir, f"{playlist['name']}.txt")
            
            with open(playlist_file, 'w', encoding='utf-8') as f:
                f.write(f"# {playlist['name']}\n")
                f.write(f"# Description: {playlist['description']}\n")
                f.write(f"# Tracks: {len(playlist['tracks'])}\n\n")
                
                for track in playlist['tracks']:
                    # Apple Music format: Artist - Song
                    artists = ', '.join(track['artists'])
                    f.write(f"{artists} - {track['name']}\n")
        
        # Create a consolidated library file
        library_file = os.path.join(apple_dir, "spotify_library_for_apple_music.txt")
        with open(library_file, 'w', encoding='utf-8') as f:
            f.write("# Spotify Library Export for Apple Music\n")
            f.write("# Format: Artist - Song (Album)\n\n")
            
            # Add liked songs first
            if backup_data.get('liked_songs'):
                f.write("# === LIKED SONGS ===\n")
                for track in backup_data['liked_songs']:
                    artists = ', '.join(track['artists'])
                    f.write(f"{artists} - {track['name']} ({track['album']})\n")
                f.write("\n")
            
            # Add playlists
            for playlist in backup_data['playlists']:
                f.write(f"# === {playlist['name'].upper()} ===\n")
                for track in playlist['tracks']:
                    artists = ', '.join(track['artists'])
                    f.write(f"{artists} - {track['name']} ({track['album']})\n")
                f.write("\n")
    
    def _create_youtube_music_export(self, backup_data: dict, backup_path: str):
        """Create YouTube Music compatible export format."""
        youtube_dir = os.path.join(backup_path, "youtube_music_format")
        os.makedirs(youtube_dir, exist_ok=True)
        
        # Create YouTube Music CSV format
        youtube_csv = os.path.join(youtube_dir, "youtube_music_import.csv")
        
        with open(youtube_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # YouTube Music CSV headers
            writer.writerow(['Title', 'Artist', 'Album', 'Playlist'])
            
            # Add liked songs to "Liked" playlist
            if backup_data.get('liked_songs'):
                for track in backup_data['liked_songs']:
                    writer.writerow([
                        track['name'],
                        ', '.join(track['artists']),
                        track['album'],
                        'Liked Songs'
                    ])
            
            # Add playlist tracks
            for playlist in backup_data['playlists']:
                for track in playlist['tracks']:
                    writer.writerow([
                        track['name'],
                        ', '.join(track['artists']),
                        track['album'],
                        playlist['name']
                    ])
        
        # Create individual playlist files
        for playlist in backup_data['playlists']:
            playlist_file = os.path.join(youtube_dir, f"{playlist['name']}_youtube.csv")
            
            with open(playlist_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Title', 'Artist', 'Album'])
                
                for track in playlist['tracks']:
                    writer.writerow([
                        track['name'],
                        ', '.join(track['artists']),
                        track['album']
                    ])
    
    def _create_universal_m3u_export(self, backup_data: dict, backup_path: str):
        """Create M3U playlist files for maximum compatibility."""
        m3u_dir = os.path.join(backup_path, "m3u_playlists")
        os.makedirs(m3u_dir, exist_ok=True)
        
        # Create M3U files for each playlist
        for playlist in backup_data['playlists']:
            playlist_file = os.path.join(m3u_dir, f"{playlist['name']}.m3u")
            
            with open(playlist_file, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                f.write(f"#PLAYLIST:{playlist['name']}\n")
                
                for track in playlist['tracks']:
                    duration_sec = track['duration_ms'] // 1000
                    artists = ', '.join(track['artists'])
                    f.write(f"#EXTINF:{duration_sec},{artists} - {track['name']}\n")
                    # Note: No actual file paths since these are Spotify tracks
                    f.write(f"# Spotify URI: {track.get('uri', 'N/A')}\n")
        
        # Create a master M3U with all liked songs
        if backup_data.get('liked_songs'):
            liked_file = os.path.join(m3u_dir, "Liked_Songs.m3u")
            
            with open(liked_file, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                f.write("#PLAYLIST:Liked Songs\n")
                
                for track in backup_data['liked_songs']:
                    duration_sec = track['duration_ms'] // 1000
                    artists = ', '.join(track['artists'])
                    f.write(f"#EXTINF:{duration_sec},{artists} - {track['name']}\n")
                    f.write(f"# Spotify URI: {track.get('uri', 'N/A')}\n")
    
    def _create_backup_report(self, backup_data: dict, backup_path: str):
        """Create a human-readable backup report."""
        report_file = os.path.join(backup_path, "backup_report.txt")
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("SPOTIFY LIBRARY BACKUP REPORT\n")
            f.write("=" * 50 + "\n\n")
            
            info = backup_data['backup_info']
            f.write(f"Backup Date: {info['created_at']}\n")
            f.write(f"User: {info['user_name']} ({info['user_id']})\n")
            f.write(f"Email: {info.get('user_email', 'N/A')}\n\n")
            
            f.write("BACKUP SUMMARY\n")
            f.write("-" * 30 + "\n")
            f.write(f"Playlists: {len(backup_data['playlists'])}\n")
            f.write(f"Followed Artists: {len(backup_data['followed_artists'])}\n")
            f.write(f"Liked Songs: {len(backup_data['liked_songs'])}\n\n")
            
            total_tracks = sum(len(p['tracks']) for p in backup_data['playlists'])
            f.write(f"Total Playlist Tracks: {total_tracks}\n")
            
            f.write("\nPLAYLIST DETAILS\n")
            f.write("-" * 30 + "\n")
            for playlist in backup_data['playlists']:
                f.write(f"• {playlist['name']}: {len(playlist['tracks'])} tracks\n")
            
            f.write(f"\nTOP GENRES (from followed artists)\n")
            f.write("-" * 30 + "\n")
            all_genres = []
            for artist in backup_data['followed_artists']:
                all_genres.extend(artist['genres'])
            
            from collections import Counter
            genre_counts = Counter(all_genres)
            for genre, count in genre_counts.most_common(10):
                f.write(f"• {genre}: {count} artists\n")
    
    def list_backups(self) -> list:
        """List all available backups."""
        backups = []
        
        if not os.path.exists(self.backup_dir):
            return backups
        
        for item in os.listdir(self.backup_dir):
            backup_path = os.path.join(self.backup_dir, item)
            if os.path.isdir(backup_path):
                backup_file = os.path.join(backup_path, "spotify_backup.json")
                if os.path.exists(backup_file):
                    try:
                        with open(backup_file, 'r') as f:
                            backup_info = json.load(f)['backup_info']
                            backups.append({
                                'name': item,
                                'path': backup_path,
                                'created_at': backup_info['created_at'],
                                'user_name': backup_info.get('user_name', 'Unknown')
                            })
                    except Exception:
                        continue
        
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        return backups

def main():
    """Main function for backup functionality."""
    print(f"{Fore.CYAN}{Style.BRIGHT}Spotify Library Backup Tool")
    print("=" * 50)
    
    backup_tool = SpotifyBackup()
    
    while True:
        print(f"\n{Fore.WHITE}Options:")
        print("1. Create full backup")
        print("2. List existing backups")
        print("3. Exit")
        
        choice = input(f"\n{Fore.CYAN}Enter your choice (1-3): ")
        
        if choice == "1":
            backup_path = backup_tool.create_full_backup()
            print(f"\n{Fore.GREEN}Backup completed successfully!")
            print(f"{Fore.BLUE}Location: {backup_path}")
            
        elif choice == "2":
            backups = backup_tool.list_backups()
            if backups:
                print(f"\n{Fore.YELLOW}Available Backups:")
                for i, backup in enumerate(backups, 1):
                    print(f"{i}. {backup['name']} - {backup['created_at']} - {backup['user_name']}")
            else:
                print(f"\n{Fore.YELLOW}No backups found.")
                
        elif choice == "3":
            print(f"{Fore.GREEN}Goodbye!")
            break
        
        else:
            print(f"{Fore.RED}Invalid choice. Please try again.")

if __name__ == "__main__":
    main()