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
            print(desc)
            
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
                        'name': artist['name'],
                        'popularity': artist.get('popularity', 0),
                        'genres': artist.get('genres', []),
                        'followers': artist['followers']['total']
                    }
                    for artist in top_artists['items']
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
        print("📈 Analyzing taste evolution...")
        
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
        print("🎭 Analyzing genres...")
        
        # Get all followed artists
        followed_artists = []
        results = self.sp.current_user_followed_artists(limit=50)
        
        while True:
            followed_artists.extend(results['artists']['items'])
            if results['artists']['next']:
                results = self.sp.next(results['artists'])
                time.sleep(0.1)
            else:
                break
        
        # Analyze genres
        all_genres = []
        genre_artist_map = defaultdict(list)
        
        for artist in followed_artists:
            for genre in artist.get('genres', []):
                all_genres.append(genre)
                genre_artist_map[genre].append(artist['name'])
        
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
        print("🌍 Analyzing artist diversity...")
        
        # Get followed artists with enhanced metadata
        followed_artists = []
        results = self.sp.current_user_followed_artists(limit=50)
        
        max_retries = 3
        retry_count = 0
        
        while True:
            try:
                followed_artists.extend(results['artists']['items'])
                if results['artists']['next']:
                    results = self.sp.next(results['artists'])
                    time.sleep(0.5)  # Increased delay to avoid timeouts
                    retry_count = 0  # Reset on success
                else:
                    break
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"⚠️  Warning: Failed to fetch all followed artists after {max_retries} retries. Using partial data.")
                    break
                print(f"⚠️  Retry {retry_count}/{max_retries} due to error: {str(e)[:100]}...")
                time.sleep(2 * retry_count)  # Exponential backoff
        
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
        print("📋 Analyzing playlists...")
        
        playlists = []
        results = self.sp.current_user_playlists(limit=50)
        
        while True:
            playlists.extend(results['items'])
            if results['next']:
                results = self.sp.next(results)
                time.sleep(0.1)
            else:
                break
        
        # Filter user's own playlists
        user_id = self.sp.current_user()['id']
        own_playlists = [p for p in playlists if p['owner']['id'] == user_id]
        
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
        print("🔍 Generating discovery insights...")
        
        # This would integrate with the music discovery engine
        # For now, return basic insights
        return {
            'recommendation_sources': ['spotify', 'musicbrainz', 'lastfm'],
            'discovery_potential': 'high',  # Could be calculated based on diversity scores
            'suggested_explorations': [
                'Explore artists from underrepresented countries',
                'Discover music from different time periods',
                'Try related artists from MusicBrainz'
            ]
        }
    
    def _analyze_music_timeline(self) -> dict:
        """Analyze the timeline of user's music preferences."""
        print("📅 Analyzing music timeline...")
        
        # Get liked songs with added dates
        liked_songs = []
        results = self.sp.current_user_saved_tracks(limit=50)
        
        # Limit to avoid long processing
        total_processed = 0
        max_songs = 500
        
        while results and total_processed < max_songs:
            for item in results['items']:
                if item['added_at']:
                    liked_songs.append({
                        'name': item['track']['name'],
                        'artists': [artist['name'] for artist in item['track']['artists']],
                        'added_at': item['added_at'],
                        'popularity': item['track'].get('popularity', 0)
                    })
                    total_processed += 1
                    
                if total_processed >= max_songs:
                    break
            
            if results['next'] and total_processed < max_songs:
                results = self.sp.next(results)
                time.sleep(0.1)
            else:
                break
        
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
        top_tracks = self.sp.current_user_top_tracks(limit=50, time_range='medium_term')
        track_ids = [track['id'] for track in top_tracks['items']]
        
        if not track_ids:
            return {}
        
        # Get audio features in batches with error handling
        all_features = []
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
            time.sleep(0.1)
        
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