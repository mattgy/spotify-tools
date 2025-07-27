#!/usr/bin/env python3
"""
Enhanced Analytics for Spotify listening patterns and music taste analysis.
Replaces the broken dashboard with comprehensive analytics.
"""

import os
import sys
import json
import datetime
import time
from collections import Counter, defaultdict
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from credentials_manager import get_spotify_credentials
from cache_utils import save_to_cache, load_from_cache
from config import config, get_cache_expiration
from musicbrainz_integration import mb_client
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
from spotify_utils import create_spotify_client

# Spotify API scopes needed
SPOTIFY_SCOPES = [
    "user-top-read",
    "user-library-read",
    "playlist-read-private",
    "user-follow-read",
    "user-read-email",
    "user-read-private"
]

class SpotifyAnalytics:
    """Enhanced Spotify analytics and insights."""
    
    def __init__(self):
        self.sp = self._setup_spotify_client()
        self.output_dir = os.path.join(script_dir, "analytics_output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.cache_expiration = get_cache_expiration()
    
    def _setup_spotify_client(self):
        """Set up authenticated Spotify client."""
        try:
            from spotify_utils import create_spotify_client
            return create_spotify_client(SPOTIFY_SCOPES, "analytics")
        except Exception as e:
            print(f"{Fore.RED}Error setting up Spotify client: {e}")
            sys.exit(1)
    
    
    def generate_comprehensive_report(self) -> str:
        """Generate a comprehensive analytics report."""
        print(f"{Fore.CYAN}🔍 Generating comprehensive music analytics...")
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(self.output_dir, f"spotify_analytics_{timestamp}.json")
        
        # Collect all data with rate limiting
        analytics_data = {
            'generated_at': timestamp,
            'user_profile': self._get_user_profile(),
        }
        
        # Add rate limiting delay
        time.sleep(0.5)
        
        # Get listening patterns once and reuse
        print("🎵 Analyzing listening patterns...")
        listening_patterns = self._analyze_listening_patterns()
        analytics_data['listening_patterns'] = listening_patterns
        
        # Analysis steps with progress tracking
        analysis_steps = [
            ("📈 Analyzing taste evolution...", "_analyze_taste_evolution", [listening_patterns]),
            ("🎭 Analyzing genres...", "_analyze_genres", []),
            ("🎨 Analyzing artist diversity...", "_analyze_artist_diversity", []),
            ("📋 Analyzing playlists...", "_analyze_playlists", []),
            ("🔍 Getting discovery insights...", "_get_discovery_insights", [])
        ]
        
        progress_bar = create_progress_bar(len(analysis_steps), "Running analytics", "analysis")
        
        for i, (desc, method_name, args) in enumerate(analysis_steps):
            # Only print the description once, not in both the loop and the method
            
            method = getattr(self, method_name)
            if args:
                result = method(*args)
            else:
                result = method()
            
            # Store result using appropriate key
            if method_name == "_analyze_taste_evolution":
                analytics_data['music_taste_evolution'] = result
            elif method_name == "_analyze_genres":
                analytics_data['genre_analysis'] = result
            elif method_name == "_analyze_artist_diversity":
                analytics_data['artist_diversity'] = result
            elif method_name == "_analyze_playlists":
                analytics_data['playlist_insights'] = result
            elif method_name == "_get_discovery_insights":
                analytics_data['discovery_recommendations'] = result
            
            update_progress_bar(progress_bar, 1)
            time.sleep(0.5)  # Rate limiting delay
        
        close_progress_bar(progress_bar)
        
        time.sleep(0.5)
        analytics_data['music_timeline'] = self._analyze_music_timeline()
        
        time.sleep(0.5)
        analytics_data['audio_features_analysis'] = self._analyze_audio_features()
        
        # Save comprehensive data
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(analytics_data, f, indent=2, ensure_ascii=False)
        
        # Create human-readable report
        text_report = self._create_text_report(analytics_data)
        text_file = os.path.join(self.output_dir, f"spotify_report_{timestamp}.txt")
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        # Create visualizations
        self._create_visualizations(analytics_data, timestamp)
        
        print(f"{Fore.GREEN}✅ Analytics report generated!")
        print(f"{Fore.BLUE}📊 Report saved to: {report_file}")
        print(f"{Fore.BLUE}📄 Text report: {text_file}")
        
        return report_file
    
    def _get_user_profile(self) -> dict:
        """Get user profile information."""
        user = self.sp.current_user()
        return {
            'id': user.get('id'),
            'display_name': user.get('display_name'),
            'email': user.get('email'),
            'country': user.get('country'),
            'followers': user.get('followers', {}).get('total', 0),
            'product': user.get('product')
        }
    
    def _analyze_listening_patterns(self) -> dict:
        """Analyze user's listening patterns across time ranges."""
        
        patterns = {}
        time_ranges = ['short_term', 'medium_term', 'long_term']
        
        progress_bar = create_progress_bar(len(time_ranges), "Analyzing time periods", "period")
        
        for i, time_range in enumerate(time_ranges):
            print(f"  • Analyzing {time_range} listening patterns...")
            
            # Get top artists and tracks for this time range with error handling
            try:
                top_artists = self.sp.current_user_top_artists(limit=50, time_range=time_range)
            except Exception as e:
                if "rate" in str(e).lower():
                    print(f"  ⚠️ Rate limited for artists. Waiting 3 seconds...")
                    time.sleep(3.0)
                    top_artists = self.sp.current_user_top_artists(limit=50, time_range=time_range)
                else:
                    raise e
            
            # Add delay between API calls to avoid rate limiting
            time.sleep(1.0)
            
            try:
                top_tracks = self.sp.current_user_top_tracks(limit=50, time_range=time_range)
            except Exception as e:
                if "rate" in str(e).lower():
                    print(f"  ⚠️ Rate limited for tracks. Waiting 3 seconds...")
                    time.sleep(3.0)
                    top_tracks = self.sp.current_user_top_tracks(limit=50, time_range=time_range)
                else:
                    raise e
            
            patterns[time_range] = {
                'top_artists': [
                    {
                        'name': artist['name'] if isinstance(artist, dict) else str(artist),
                        'popularity': artist.get('popularity', 0) if isinstance(artist, dict) else 0,
                        'genres': artist.get('genres', []) if isinstance(artist, dict) else [],
                        'followers': artist['followers']['total'] if isinstance(artist, dict) and 'followers' in artist else 0
                    }
                    for artist in top_artists['items']
                    if artist  # Skip None/empty artists
                ],
                'top_tracks': [
                    {
                        'name': track['name'],
                        'artists': [artist['name'] for artist in track['artists']],
                        'album': track['album']['name'],
                        'popularity': track.get('popularity', 0),
                        'duration_ms': track['duration_ms']
                    }
                    for track in top_tracks['items']
                ]
            }
            
            update_progress_bar(progress_bar, 1)
            
            # Add delay between time ranges to avoid rate limiting
            if i < len(time_ranges) - 1:
                time.sleep(1.0)
        
        close_progress_bar(progress_bar)
        return patterns
    
    def _analyze_taste_evolution(self, patterns=None) -> dict:
        """Analyze how user's taste has evolved over time."""
        # Use provided patterns or get them (avoid duplicate API calls)
        if patterns is None:
            patterns = self._analyze_listening_patterns()
        
        evolution = {
            'genre_evolution': self._track_genre_changes(patterns),
            'artist_consistency': self._analyze_artist_consistency(patterns),
            'popularity_trends': self._analyze_popularity_trends(patterns)
        }
        
        return evolution
    
    def _track_genre_changes(self, patterns: dict) -> dict:
        """Track how genres have changed over time."""
        genre_evolution = {}
        
        for time_range, data in patterns.items():
            genres = []
            for artist in data['top_artists']:
                genres.extend(artist['genres'])
            
            genre_counts = Counter(genres)
            genre_evolution[time_range] = dict(genre_counts.most_common(10))
        
        return genre_evolution
    
    def _analyze_artist_consistency(self, patterns: dict) -> dict:
        """Analyze which artists remain consistent across time ranges."""
        all_artists = {}
        
        for time_range, data in patterns.items():
            artists = {artist['name'] for artist in data['top_artists']}
            all_artists[time_range] = artists
        
        # Find intersections
        short_term = all_artists.get('short_term', set())
        medium_term = all_artists.get('medium_term', set())
        long_term = all_artists.get('long_term', set())
        
        return {
            'consistent_across_all': list(short_term & medium_term & long_term),
            'short_medium_overlap': list(short_term & medium_term),
            'medium_long_overlap': list(medium_term & long_term),
            'only_recent': list(short_term - medium_term - long_term),
            'only_long_term': list(long_term - medium_term - short_term)
        }
    
    def _analyze_popularity_trends(self, patterns: dict) -> dict:
        """Analyze trends in music popularity."""
        trends = {}
        
        for time_range, data in patterns.items():
            artist_popularity = [artist['popularity'] for artist in data['top_artists']]
            track_popularity = [track['popularity'] for track in data['top_tracks']]
            
            trends[time_range] = {
                'avg_artist_popularity': sum(artist_popularity) / len(artist_popularity) if artist_popularity else 0,
                'avg_track_popularity': sum(track_popularity) / len(track_popularity) if track_popularity else 0,
                'mainstream_vs_niche': self._classify_mainstream_vs_niche(artist_popularity + track_popularity)
            }
        
        return trends
    
    def _classify_mainstream_vs_niche(self, popularity_scores: list) -> dict:
        """Classify music as mainstream vs niche based on popularity."""
        if not popularity_scores:
            return {'mainstream': 0, 'niche': 0, 'classification': 'unknown'}
        
        avg_popularity = sum(popularity_scores) / len(popularity_scores)
        mainstream_count = sum(1 for score in popularity_scores if score > 70)
        niche_count = sum(1 for score in popularity_scores if score < 30)
        
        classification = 'mainstream' if avg_popularity > 65 else 'niche' if avg_popularity < 35 else 'balanced'
        
        return {
            'avg_popularity': avg_popularity,
            'mainstream_count': mainstream_count,
            'niche_count': niche_count,
            'classification': classification
        }
    
    def _analyze_genres(self) -> dict:
        """Comprehensive genre analysis."""
        from spotify_utils import fetch_followed_artists
        from constants import CACHE_EXPIRATION
        
        # Get all followed artists using cached data - use consistent cache key
        followed_artists = fetch_followed_artists(
            self.sp,
            show_progress=True,  # Show progress for transparency
            cache_key="followed_artists",
            cache_expiration=CACHE_EXPIRATION['long']
        )
        
        if not followed_artists:
            return {
                'total_unique_genres': 0,
                'top_genres': {},
                'genre_diversity_score': 0,
                'genre_artist_mapping': {},
                'rare_genres': []
            }
        
        # Analyze genres with progress indication
        print("  Processing genre data...")
        all_genres = []
        genre_artist_map = defaultdict(list)
        
        progress_bar = create_progress_bar(len(followed_artists), "Analyzing artist genres", "artist")
        
        for artist in followed_artists:
            # Handle case where artist might be a string instead of dict
            if isinstance(artist, dict):
                for genre in artist.get('genres', []):
                    all_genres.append(genre)
                    genre_artist_map[genre].append(artist.get('name', 'Unknown'))
            elif isinstance(artist, str):
                # Skip strings as they don't have genre data
                print_warning(f"Found artist data as string: {artist}")
            update_progress_bar(progress_bar, 1)
        
        close_progress_bar(progress_bar)
        
        genre_counts = Counter(all_genres)
        
        return {
            'total_unique_genres': len(genre_counts),
            'top_genres': dict(genre_counts.most_common(20)),
            'genre_diversity_score': len(genre_counts) / len(followed_artists) if followed_artists else 0,
            'genre_artist_mapping': dict(genre_artist_map),
            'rare_genres': [genre for genre, count in genre_counts.items() if count == 1]
        }
    
    def _analyze_artist_diversity(self) -> dict:
        """Analyze diversity in artist selection."""
        from spotify_utils import fetch_followed_artists
        from constants import CACHE_EXPIRATION
        
        # Get followed artists using cached data - use consistent cache key
        followed_artists = fetch_followed_artists(
            self.sp,
            show_progress=True,  # Show progress for transparency
            cache_key="followed_artists",
            cache_expiration=CACHE_EXPIRATION['long']
        )
        
        # Enrich with MusicBrainz data for geographic analysis
        countries = []
        time_periods = []
        artist_types = []
        
        sample_size = min(20, len(followed_artists))  # Limit to avoid API overload
        sample_artists = followed_artists[:sample_size]
        
        for artist in sample_artists:
            enriched = mb_client.enrich_artist_data(artist)
            mb_data = enriched.get('musicbrainz', {})
            
            if mb_data.get('country'):
                countries.append(mb_data['country'])
            
            if mb_data.get('type'):
                artist_types.append(mb_data['type'])
            
            # Analyze time periods
            begin_date = mb_data.get('begin_date', '')
            if begin_date and len(begin_date) >= 4:
                try:
                    year = int(begin_date[:4])
                    if year < 1960:
                        time_periods.append("Pre-1960")
                    elif year < 1980:
                        time_periods.append("1960s-1970s")
                    elif year < 2000:
                        time_periods.append("1980s-1990s")
                    elif year < 2010:
                        time_periods.append("2000s")
                    else:
                        time_periods.append("2010s+")
                except ValueError:
                    pass
        
        return {
            'total_artists': len(followed_artists),
            'geographic_diversity': {
                'countries': dict(Counter(countries).most_common(10)),
                'unique_countries': len(set(countries))
            },
            'temporal_diversity': dict(Counter(time_periods)),
            'artist_type_diversity': dict(Counter(artist_types)),
            'diversity_scores': {
                'geographic': len(set(countries)) / len(countries) if countries else 0,
                'temporal': len(set(time_periods)) / len(time_periods) if time_periods else 0,
                'type': len(set(artist_types)) / len(artist_types) if artist_types else 0
            }
        }
    
    def _analyze_playlists(self) -> dict:
        """Analyze user's playlist creation and management patterns."""
        from spotify_utils import fetch_user_playlists
        from constants import CACHE_EXPIRATION
        
        # Get user playlists using cached data - use consistent cache key
        all_playlists = fetch_user_playlists(
            self.sp,
            show_progress=True,  # Show progress for transparency
            cache_key="user_playlists",
            cache_expiration=CACHE_EXPIRATION['long']
        )
        
        # Filter user's own playlists
        user_id = self.sp.current_user()['id']
        own_playlists = [p for p in all_playlists if p['owner']['id'] == user_id]
        
        # Analyze playlist characteristics
        playlist_analysis = {
            'total_playlists': len(own_playlists),
            'total_tracks': sum(p['tracks']['total'] for p in own_playlists),
            'avg_tracks_per_playlist': sum(p['tracks']['total'] for p in own_playlists) / len(own_playlists) if own_playlists else 0,
            'public_vs_private': {
                'public': sum(1 for p in own_playlists if p.get('public', False)),
                'private': sum(1 for p in own_playlists if not p.get('public', False))
            },
            'collaborative_playlists': sum(1 for p in own_playlists if p.get('collaborative', False)),
            'playlist_sizes': {
                'small': sum(1 for p in own_playlists if p['tracks']['total'] < 20),
                'medium': sum(1 for p in own_playlists if 20 <= p['tracks']['total'] < 100),
                'large': sum(1 for p in own_playlists if p['tracks']['total'] >= 100)
            }
        }
        
        return playlist_analysis
    
    def _get_discovery_insights(self) -> dict:
        """Get music discovery insights and recommendations."""
        from music_discovery_engine import MusicDiscoveryEngine
        from lastfm_integration import lastfm_client
        
        try:
            # Quick profile analysis for discovery insights
            discovery_engine = MusicDiscoveryEngine()
            discovery_engine.sp = self.sp  # Reuse our Spotify client
            
            # Get a lightweight profile analysis
            followed_artists = fetch_followed_artists(
                self.sp,
                show_progress=False,
                cache_key="followed_artists",
                cache_expiration=CACHE_EXPIRATION['long']
            )
            
            if not followed_artists:
                return {
                    'error': 'No followed artists found for analysis',
                    'recommendation_sources': ['spotify', 'musicbrainz', 'lastfm'],
                    'discovery_potential': 'unknown'
                }
            
            # Analyze top genres for discovery potential
            all_genres = []
            for artist in followed_artists[:20]:  # Sample to avoid long processing
                # Handle case where artist might be a string instead of dict
                if isinstance(artist, dict):
                    all_genres.extend(artist.get('genres', []))
                # Skip strings as they don't have genre data
            
            from collections import Counter
            genre_counts = Counter(all_genres)
            unique_genres = len(genre_counts)
            
            # Get some Last.fm based insights if available
            lastfm_insights = {}
            if lastfm_client.api_key and followed_artists:
                sample_artist = followed_artists[0]['name']
                artist_info = lastfm_client.get_artist_info(sample_artist)
                if not artist_info.get('error'):
                    lastfm_insights = {
                        'sample_artist_listeners': artist_info.get('listeners', 0),
                        'sample_artist_tags': artist_info.get('tags', [])[:5]
                    }
            
            # Calculate discovery potential
            discovery_score = min(unique_genres / 10, 1.0)  # Normalize to 0-1
            if discovery_score > 0.7:
                discovery_potential = 'high'
            elif discovery_score > 0.4:
                discovery_potential = 'medium' 
            else:
                discovery_potential = 'low'
            
            return {
                'recommendation_sources': ['spotify', 'musicbrainz', 'lastfm'],
                'discovery_potential': discovery_potential,
                'diversity_score': discovery_score,
                'unique_genres_analyzed': unique_genres,
                'total_artists_analyzed': len(followed_artists),
                'suggested_explorations': [
                    f'Explore artists from underrepresented countries (current diversity: {unique_genres} genres)',
                    'Discover music from different time periods using MusicBrainz data',
                    'Try Last.fm similarity recommendations for genre expansion',
                    'Use geographic heat maps to find new regional music styles'
                ],
                'lastfm_sample': lastfm_insights,
                'top_genres_discovered': dict(genre_counts.most_common(10))
            }
            
        except Exception as e:
            print(f"Warning: Could not generate discovery insights: {e}")
            return {
                'error': str(e),
                'recommendation_sources': ['spotify', 'musicbrainz', 'lastfm'],
                'discovery_potential': 'unknown',
                'suggested_explorations': [
                    'Explore artists from underrepresented countries',
                    'Discover music from different time periods',
                    'Try related artists from MusicBrainz'
                ]
            }
    
    def _analyze_music_timeline(self) -> dict:
        """Analyze the timeline of user's music preferences."""
        from spotify_utils import fetch_liked_songs
        from constants import CACHE_EXPIRATION
        
        print("📅 Analyzing music timeline...")
        
        # Get liked songs using cached data - use consistent cache key
        all_liked_songs = fetch_liked_songs(
            self.sp,
            show_progress=True,  # Show progress for transparency
            cache_key="liked_songs",
            cache_expiration=CACHE_EXPIRATION['long']
        )
        
        # Limit to avoid long processing and convert to simplified format
        max_songs = 500
        liked_songs = []
        
        progress_bar = create_progress_bar(min(len(all_liked_songs), max_songs), "Processing timeline data", "song")
        
        for i, item in enumerate(all_liked_songs[:max_songs]):
            if item['added_at']:
                liked_songs.append({
                    'name': item['track']['name'],
                    'artists': [artist['name'] for artist in item['track']['artists']],
                    'added_at': item['added_at'],
                    'popularity': item['track'].get('popularity', 0)
                })
            update_progress_bar(progress_bar, 1)
        
        close_progress_bar(progress_bar)
        
        # Analyze by month/year
        timeline_analysis = {
            'total_songs_analyzed': len(liked_songs),
            'date_range': {
                'earliest': min(song['added_at'] for song in liked_songs) if liked_songs else None,
                'latest': max(song['added_at'] for song in liked_songs) if liked_songs else None
            },
            'monthly_activity': self._group_by_month(liked_songs),
            'listening_intensity_periods': self._identify_intensity_periods(liked_songs)
        }
        
        return timeline_analysis
    
    def _group_by_month(self, songs: list) -> dict:
        """Group songs by month for timeline analysis."""
        monthly_counts = defaultdict(int)
        
        for song in songs:
            try:
                date = datetime.datetime.fromisoformat(song['added_at'].replace('Z', '+00:00'))
                month_key = date.strftime('%Y-%m')
                monthly_counts[month_key] += 1
            except Exception:
                continue
        
        return dict(monthly_counts)
    
    def _identify_intensity_periods(self, songs: list) -> dict:
        """Identify periods of high/low music discovery activity."""
        monthly_counts = self._group_by_month(songs)
        
        if not monthly_counts:
            return {}
        
        counts = list(monthly_counts.values())
        avg_monthly = sum(counts) / len(counts)
        
        high_activity = {k: v for k, v in monthly_counts.items() if v > avg_monthly * 1.5}
        low_activity = {k: v for k, v in monthly_counts.items() if v < avg_monthly * 0.5}
        
        return {
            'average_monthly': avg_monthly,
            'high_activity_periods': high_activity,
            'low_activity_periods': low_activity,
            'most_active_month': max(monthly_counts.items(), key=lambda x: x[1]) if monthly_counts else None
        }
    
    def _analyze_audio_features(self) -> dict:
        """Analyze audio features of user's music."""
        print("🎵 Analyzing audio features...")
        
        # Get top tracks and analyze their audio features
        try:
            top_tracks = self.sp.current_user_top_tracks(limit=50, time_range='medium_term')
            track_ids = [track['id'] for track in top_tracks['items']]
        except Exception as e:
            print(f"⚠️ Could not fetch top tracks: {e}")
            return {}
        
        if not track_ids:
            return {}
        
        print("  Fetching audio features...")
        
        # Get audio features in batches with error handling
        all_features = []
        num_batches = (len(track_ids) + 99) // 100
        progress_bar = create_progress_bar(num_batches, "Analyzing audio features", "batch")
        
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i:i+100]
            try:
                features = self.sp.audio_features(batch)
                if features is not None:
                    # Filter out None values in the features list
                    valid_features = [f for f in features if f is not None]
                    all_features.extend(valid_features)
                else:
                    print("⚠️ Audio features unavailable (may require additional permissions)")
            except Exception as e:
                error_str = str(e).lower()
                if '403' in error_str or 'forbidden' in error_str:
                    print("⚠️ Audio features not accessible - missing scope or permissions")
                else:
                    print(f"⚠️ Error fetching audio features: {e}")
                # Continue with other batches
                continue
            
            update_progress_bar(progress_bar, 1)
            time.sleep(0.1)
        
        close_progress_bar(progress_bar)
        
        if not all_features:
            return {}
        
        # Calculate averages
        feature_keys = ['danceability', 'energy', 'speechiness', 'acousticness', 
                       'instrumentalness', 'liveness', 'valence', 'tempo']
        
        averages = {}
        for key in feature_keys:
            values = [f[key] for f in all_features if f[key] is not None]
            averages[key] = sum(values) / len(values) if values else 0
        
        return {
            'tracks_analyzed': len(all_features),
            'audio_feature_averages': averages,
            'music_personality': self._classify_music_personality(averages)
        }
    
    def _classify_music_personality(self, features: dict) -> dict:
        """Classify user's music personality based on audio features."""
        if not features:
            return {}
        
        personality = {}
        
        # Energy level
        energy = features.get('energy', 0.5)
        if energy > 0.7:
            personality['energy_level'] = 'High-energy listener'
        elif energy < 0.3:
            personality['energy_level'] = 'Calm/relaxed listener'
        else:
            personality['energy_level'] = 'Balanced energy listener'
        
        # Danceability
        dance = features.get('danceability', 0.5)
        if dance > 0.7:
            personality['danceability'] = 'Loves danceable music'
        elif dance < 0.3:
            personality['danceability'] = 'Prefers non-dance music'
        else:
            personality['danceability'] = 'Mixed dance preferences'
        
        # Valence (positivity)
        valence = features.get('valence', 0.5)
        if valence > 0.7:
            personality['mood'] = 'Upbeat/positive music lover'
        elif valence < 0.3:
            personality['mood'] = 'Melancholic/introspective listener'
        else:
            personality['mood'] = 'Emotionally diverse listener'
        
        # Acousticness
        acoustic = features.get('acousticness', 0.5)
        if acoustic > 0.7:
            personality['style'] = 'Acoustic/organic music lover'
        elif acoustic < 0.3:
            personality['style'] = 'Electronic/produced music fan'
        else:
            personality['style'] = 'Diverse production preferences'
        
        return personality
    
    def _create_text_report(self, analytics_data: dict) -> str:
        """Create a human-readable text report."""
        report = []
        report.append("SPOTIFY MUSIC ANALYTICS REPORT")
        report.append("=" * 50)
        report.append(f"Generated: {analytics_data['generated_at']}")
        report.append(f"User: {analytics_data['user_profile']['display_name']}")
        report.append("")
        
        # Listening patterns summary
        patterns = analytics_data['listening_patterns']
        report.append("LISTENING PATTERNS")
        report.append("-" * 30)
        
        for time_range, data in patterns.items():
            report.append(f"\n{time_range.replace('_', ' ').title()}:")
            report.append(f"  Top Artists: {', '.join([a['name'] for a in data['top_artists'][:5]])}")
            report.append(f"  Top Tracks: {', '.join([t['name'] for t in data['top_tracks'][:3]])}")
        
        # Genre analysis
        genre_analysis = analytics_data['genre_analysis']
        report.append(f"\nGENRE ANALYSIS")
        report.append("-" * 30)
        report.append(f"Total Genres: {genre_analysis['total_unique_genres']}")
        report.append(f"Genre Diversity Score: {genre_analysis['genre_diversity_score']:.2f}")
        report.append("Top Genres:")
        for genre, count in list(genre_analysis['top_genres'].items())[:10]:
            report.append(f"  • {genre}: {count} artists")
        
        # Music personality
        audio_features = analytics_data.get('audio_features_analysis', {})
        if 'music_personality' in audio_features:
            report.append(f"\nMUSIC PERSONALITY")
            report.append("-" * 30)
            for trait, description in audio_features['music_personality'].items():
                report.append(f"  • {trait.replace('_', ' ').title()}: {description}")
        
        # Artist diversity
        diversity = analytics_data['artist_diversity']
        report.append(f"\nARTIST DIVERSITY")
        report.append("-" * 30)
        report.append(f"Total Artists Followed: {diversity['total_artists']}")
        
        geo_div = diversity['geographic_diversity']
        report.append(f"Countries Represented: {geo_div['unique_countries']}")
        if geo_div['countries']:
            report.append("Top Countries:")
            for country, count in list(geo_div['countries'].items())[:5]:
                report.append(f"  • {country}: {count} artists")
        
        return "\n".join(report)
    
    def _create_visualizations(self, analytics_data: dict, timestamp: str):
        """Create visualization charts."""
        try:
            import matplotlib.pyplot as plt
            
            # Set style
            plt.style.use('default')
            
            # Create genre distribution chart
            genre_analysis = analytics_data['genre_analysis']
            if genre_analysis['top_genres']:
                fig, ax = plt.subplots(figsize=(12, 8))
                
                genres = list(genre_analysis['top_genres'].keys())[:15]
                counts = [genre_analysis['top_genres'][g] for g in genres]
                
                bars = ax.barh(genres, counts)
                ax.set_xlabel('Number of Artists')
                ax.set_title('Top Genres in Your Music Library')
                ax.set_facecolor('#f8f9fa')
                
                # Color bars
                for i, bar in enumerate(bars):
                    bar.set_color(plt.cm.viridis(i / len(bars)))
                
                plt.tight_layout()
                plt.savefig(os.path.join(self.output_dir, f'genre_distribution_{timestamp}.png'), 
                           dpi=300, bbox_inches='tight', facecolor='white')
                plt.close()
            
            # Create geographic heat map
            artist_diversity = analytics_data.get('artist_diversity', {})
            if artist_diversity and 'geographic_diversity' in artist_diversity:
                self._create_geographic_heatmap(artist_diversity['geographic_diversity'], timestamp)
            
            # Create audio features radar chart
            audio_features = analytics_data.get('audio_features_analysis', {})
            if 'audio_feature_averages' in audio_features:
                self._create_audio_features_radar(audio_features['audio_feature_averages'], timestamp)
            
            print(f"{Fore.BLUE}📊 Visualizations saved to {self.output_dir}")
            
        except ImportError:
            print(f"{Fore.YELLOW}Warning: matplotlib not available for visualizations")
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not create visualizations: {e}")
    
    def _create_audio_features_radar(self, features: dict, timestamp: str):
        """Create radar chart for audio features."""
        try:
            import numpy as np
            
            # Features to include (exclude tempo as it's on different scale)
            feature_names = ['danceability', 'energy', 'speechiness', 'acousticness', 
                           'instrumentalness', 'liveness', 'valence']
            values = [features.get(name, 0) for name in feature_names]
            
            # Create radar chart
            angles = np.linspace(0, 2 * np.pi, len(feature_names), endpoint=False).tolist()
            values += values[:1]  # Complete the circle
            angles += angles[:1]
            
            fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
            ax.plot(angles, values, 'o-', linewidth=2, color='#1db954')
            ax.fill(angles, values, alpha=0.25, color='#1db954')
            
            ax.set_xticks(angles[:-1])
            ax.set_xticklabels([name.replace('_', ' ').title() for name in feature_names])
            ax.set_ylim(0, 1)
            ax.set_title('Your Music Audio Features Profile', size=16, pad=20)
            ax.grid(True)
            
            plt.tight_layout()
            plt.savefig(os.path.join(self.output_dir, f'audio_features_radar_{timestamp}.png'), 
                       dpi=300, bbox_inches='tight', facecolor='white')
            plt.close()
            
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not create radar chart: {e}")
    
    def _create_geographic_heatmap(self, geographic_data: dict, timestamp: str):
        """Create geographic heat map of artist origins."""
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            
            countries = geographic_data.get('countries', {})
            if not countries:
                print(f"{Fore.YELLOW}No geographic data available for heat map")
                return
                
            # Create country codes mapping for common countries
            country_codes = {
                'United States': 'US', 'United Kingdom': 'GB', 'Canada': 'CA',
                'Germany': 'DE', 'France': 'FR', 'Australia': 'AU', 'Japan': 'JP',
                'South Korea': 'KR', 'Sweden': 'SE', 'Norway': 'NO', 'Denmark': 'DK',
                'Netherlands': 'NL', 'Belgium': 'BE', 'Italy': 'IT', 'Spain': 'ES',
                'Brazil': 'BR', 'Mexico': 'MX', 'Argentina': 'AR', 'India': 'IN',
                'China': 'CN', 'Russia': 'RU', 'Poland': 'PL', 'Finland': 'FI',
                'Iceland': 'IS', 'Ireland': 'IE', 'Switzerland': 'CH', 'Austria': 'AT',
                'Portugal': 'PT', 'Greece': 'GR', 'Turkey': 'TR', 'Israel': 'IL',
                'South Africa': 'ZA', 'New Zealand': 'NZ', 'Chile': 'CL',
                'Colombia': 'CO', 'Venezuela': 'VE', 'Peru': 'PE', 'Ecuador': 'EC',
                'Uruguay': 'UY', 'Paraguay': 'PY', 'Bolivia': 'BO', 'Thailand': 'TH',
                'Vietnam': 'VN', 'Philippines': 'PH', 'Indonesia': 'ID', 'Malaysia': 'MY',
                'Singapore': 'SG', 'Taiwan': 'TW', 'Hong Kong': 'HK'
            }
            
            # Create a simple world map visualization using matplotlib
            fig, ax = plt.subplots(figsize=(16, 10))
            
            # Sort countries by artist count
            sorted_countries = sorted(countries.items(), key=lambda x: x[1], reverse=True)
            top_countries = sorted_countries[:20]  # Show top 20 countries
            
            # Create bar chart for geographic distribution
            country_names = [country for country, count in top_countries]
            artist_counts = [count for country, count in top_countries]
            
            # Create horizontal bar chart with color mapping
            colors = plt.cm.plasma(np.linspace(0, 1, len(top_countries)))
            bars = ax.barh(range(len(country_names)), artist_counts, color=colors)
            
            ax.set_yticks(range(len(country_names)))
            ax.set_yticklabels(country_names)
            ax.set_xlabel('Number of Artists')
            ax.set_title('Geographic Distribution of Artists in Your Library\n(Artist Origins Heat Map)', 
                        size=14, pad=20)
            ax.grid(axis='x', alpha=0.3)
            
            # Add value labels on bars
            for i, (bar, count) in enumerate(zip(bars, artist_counts)):
                ax.text(count + 0.1, bar.get_y() + bar.get_height()/2, 
                       str(count), va='center', fontsize=9)
            
            # Color bar to show intensity
            sm = plt.cm.ScalarMappable(cmap=plt.cm.plasma, 
                                     norm=plt.Normalize(vmin=min(artist_counts), 
                                                       vmax=max(artist_counts)))
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, shrink=0.6)
            cbar.set_label('Artist Count', rotation=270, labelpad=20)
            
            plt.tight_layout()
            plt.savefig(os.path.join(self.output_dir, f'geographic_heatmap_{timestamp}.png'), 
                       dpi=300, bbox_inches='tight', facecolor='white')
            plt.close()
            
            # Also create a summary pie chart for continents
            self._create_continent_distribution(countries, timestamp)
            
        except ImportError:
            print(f"{Fore.YELLOW}Warning: Required packages not available for geographic heat map")
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not create geographic heat map: {e}")
    
    def _create_continent_distribution(self, countries: dict, timestamp: str):
        """Create pie chart showing distribution by continent."""
        try:
            import matplotlib.pyplot as plt
            
            # Map countries to continents (simplified mapping)
            continent_mapping = {
                'United States': 'North America', 'Canada': 'North America', 'Mexico': 'North America',
                'Brazil': 'South America', 'Argentina': 'South America', 'Chile': 'South America',
                'Colombia': 'South America', 'Peru': 'South America', 'Venezuela': 'South America',
                'United Kingdom': 'Europe', 'Germany': 'Europe', 'France': 'Europe', 'Italy': 'Europe',
                'Spain': 'Europe', 'Sweden': 'Europe', 'Norway': 'Europe', 'Denmark': 'Europe',
                'Netherlands': 'Europe', 'Belgium': 'Europe', 'Finland': 'Europe', 'Iceland': 'Europe',
                'Ireland': 'Europe', 'Switzerland': 'Europe', 'Austria': 'Europe', 'Portugal': 'Europe',
                'Greece': 'Europe', 'Poland': 'Europe', 'Russia': 'Europe',
                'China': 'Asia', 'Japan': 'Asia', 'South Korea': 'Asia', 'India': 'Asia',
                'Thailand': 'Asia', 'Vietnam': 'Asia', 'Philippines': 'Asia', 'Indonesia': 'Asia',
                'Malaysia': 'Asia', 'Singapore': 'Asia', 'Taiwan': 'Asia', 'Hong Kong': 'Asia',
                'Turkey': 'Asia', 'Israel': 'Asia',
                'Australia': 'Oceania', 'New Zealand': 'Oceania',
                'South Africa': 'Africa'
            }
            
            continent_counts = {}
            for country, count in countries.items():
                continent = continent_mapping.get(country, 'Other')
                continent_counts[continent] = continent_counts.get(continent, 0) + count
            
            if continent_counts:
                fig, ax = plt.subplots(figsize=(10, 8))
                
                continents = list(continent_counts.keys())
                counts = list(continent_counts.values())
                colors = plt.cm.Set3(range(len(continents)))
                
                wedges, texts, autotexts = ax.pie(counts, labels=continents, autopct='%1.1f%%',
                                                 colors=colors, startangle=90)
                
                ax.set_title('Geographic Distribution by Continent\n(Artist Origins)', size=14, pad=20)
                
                # Enhance text
                for autotext in autotexts:
                    autotext.set_color('white')
                    autotext.set_fontweight('bold')
                
                plt.tight_layout()
                plt.savefig(os.path.join(self.output_dir, f'continent_distribution_{timestamp}.png'), 
                           dpi=300, bbox_inches='tight', facecolor='white')
                plt.close()
                
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not create continent distribution: {e}")

def main():
    """Main function for analytics."""
    print(f"{Fore.CYAN}{Style.BRIGHT}Spotify Enhanced Analytics")
    print("=" * 50)
    
    analytics = SpotifyAnalytics()
    
    while True:
        print(f"\n{Fore.WHITE}Analytics Options:")
        print("1. Generate comprehensive analytics report")
        print("2. Quick genre analysis")
        print("3. Audio features analysis")
        print("4. Exit")
        
        choice = input(f"\n{Fore.CYAN}Enter your choice (1-4): ")
        
        if choice == "1":
            report_file = analytics.generate_comprehensive_report()
            print(f"\n{Fore.GREEN}✅ Comprehensive report generated!")
            
        elif choice == "2":
            genre_data = analytics._analyze_genres()
            print(f"\n{Fore.YELLOW}📊 Genre Analysis:")
            print(f"Total Genres: {genre_data['total_unique_genres']}")
            print(f"Diversity Score: {genre_data['genre_diversity_score']:.2f}")
            print("\nTop 10 Genres:")
            for genre, count in list(genre_data['top_genres'].items())[:10]:
                print(f"  • {genre}: {count} artists")
                
        elif choice == "3":
            audio_data = analytics._analyze_audio_features()
            if audio_data:
                print(f"\n{Fore.YELLOW}🎵 Audio Features Analysis:")
                print(f"Tracks Analyzed: {audio_data['tracks_analyzed']}")
                print("\nYour Music Profile:")
                for trait, desc in audio_data.get('music_personality', {}).items():
                    print(f"  • {trait.replace('_', ' ').title()}: {desc}")
            else:
                print(f"{Fore.RED}No audio features data available")
                
        elif choice == "4":
            print(f"{Fore.GREEN}Goodbye!")
            break
        
        else:
            print(f"{Fore.RED}Invalid choice. Please try again.")

if __name__ == "__main__":
    main()