#!/usr/bin/env python3
"""
Personal listening pattern analysis for artist relevance scoring.

This module analyzes the user's listening habits, taste patterns, and music preferences
to create personalized relevance scores that balance popularity with personal taste alignment.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import time
import json
import math
import spotipy
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from cache_utils import save_to_cache, load_from_cache
from spotify_utils import safe_spotify_call, batch_process_items

# Cache expiration for personal analysis (shorter since listening habits change)
PERSONAL_CACHE_EXPIRATION = 60 * 60 * 24 * 3  # 3 days

class PersonalTasteAnalyzer:
    """Analyze user's personal listening patterns and taste preferences."""
    
    def __init__(self, sp: spotipy.Spotify):
        self.sp = sp
        self.user_profile = None
        self.listening_patterns = None
        
    def get_comprehensive_listening_profile(self) -> Dict:
        """
        Build a comprehensive profile of user's listening habits and preferences.
        
        Returns:
            Dict with user's taste patterns, preferred genres, artist styles, etc.
        """
        cache_key = "comprehensive_listening_profile"
        cached_data = load_from_cache(cache_key, PERSONAL_CACHE_EXPIRATION)
        
        if cached_data:
            print(f"{Fore.BLUE}Using cached listening profile...")
            return cached_data
        
        print(f"{Fore.BLUE}Analyzing your personal listening patterns...")
        
        profile = {
            'user_info': self._get_user_info(),
            'top_artists': self._analyze_top_artists(),
            'top_tracks': self._analyze_top_tracks(), 
            'recently_played': self._analyze_recent_activity(),
            'genre_preferences': {},
            'audio_features_preferences': {},
            'discovery_patterns': {},
            'taste_markers': {},
            'listening_diversity': {}
        }
        
        # Analyze genre preferences
        profile['genre_preferences'] = self._analyze_genre_preferences(
            profile['top_artists'], profile['top_tracks']
        )
        
        # Analyze audio feature preferences (tempo, energy, etc.)
        profile['audio_features_preferences'] = self._analyze_audio_preferences(
            profile['top_tracks']
        )
        
        # Analyze discovery patterns (mainstream vs niche)
        profile['discovery_patterns'] = self._analyze_discovery_patterns(
            profile['top_artists']
        )
        
        # Create taste markers for similarity matching
        profile['taste_markers'] = self._create_taste_markers(profile)
        
        # Analyze listening diversity
        profile['listening_diversity'] = self._analyze_listening_diversity(profile)
        
        # Cache the profile
        save_to_cache(profile, cache_key)
        
        return profile
    
    def _get_user_info(self) -> Dict:
        """Get basic user information."""
        if not self.user_profile:
            self.user_profile = self.sp.current_user()
        
        return {
            'id': self.user_profile.get('id'),
            'display_name': self.user_profile.get('display_name'),
            'followers': self.user_profile.get('followers', {}).get('total', 0),
            'country': self.user_profile.get('country')
        }
    
    def _analyze_top_artists(self) -> Dict:
        """Analyze user's top artists across different time periods."""
        time_ranges = ['short_term', 'medium_term', 'long_term']
        top_artists = {}
        
        for time_range in time_ranges:
            print(f"  • Analyzing top artists ({time_range})")
            try:
                results = self.sp.current_user_top_artists(limit=50, time_range=time_range)
                artists_data = []
                
                for artist in results['items']:
                    artist_data = {
                        'id': artist['id'],
                        'name': artist['name'],
                        'popularity': artist.get('popularity', 0),
                        'followers': artist['followers']['total'],
                        'genres': artist.get('genres', []),
                        'external_urls': artist.get('external_urls', {})
                    }
                    artists_data.append(artist_data)
                
                top_artists[time_range] = artists_data
                time.sleep(0.2)  # Rate limiting
                
            except Exception as e:
                print(f"{Fore.YELLOW}Warning: Could not get top artists for {time_range}: {e}")
                top_artists[time_range] = []
        
        return top_artists
    
    def _analyze_top_tracks(self) -> Dict:
        """Analyze user's top tracks and their characteristics."""
        time_ranges = ['short_term', 'medium_term', 'long_term']
        top_tracks = {}
        
        for time_range in time_ranges:
            print(f"  • Analyzing top tracks ({time_range})")
            try:
                results = self.sp.current_user_top_tracks(limit=50, time_range=time_range)
                tracks_data = []
                
                # Get track IDs for audio features analysis
                track_ids = [track['id'] for track in results['items']]
                
                # Get audio features for all tracks at once with rate limiting
                audio_features = []
                if track_ids:
                    @safe_spotify_call
                    def get_audio_features(track_ids):
                        return self.sp.audio_features(track_ids)
                    
                    audio_features = get_audio_features(track_ids)
                    if audio_features is None:
                        # Either rate limited or permission issue - skip audio features
                        audio_features = [None] * len(track_ids)
                
                for i, track in enumerate(results['items']):
                    track_data = {
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [{'id': a['id'], 'name': a['name']} for a in track['artists']],
                        'album': {
                            'id': track['album']['id'],
                            'name': track['album']['name']
                        },
                        'popularity': track.get('popularity', 0),
                        'duration_ms': track.get('duration_ms', 0),
                        'explicit': track.get('explicit', False),
                        'audio_features': audio_features[i] if i < len(audio_features) else None
                    }
                    tracks_data.append(track_data)
                
                top_tracks[time_range] = tracks_data
                time.sleep(0.2)  # Rate limiting
                
            except Exception as e:
                print(f"{Fore.YELLOW}Warning: Could not get top tracks for {time_range}: {e}")
                top_tracks[time_range] = []
        
        return top_tracks
    
    def _analyze_recent_activity(self) -> Dict:
        """Analyze recently played tracks for current preferences."""
        print(f"  • Analyzing recent listening activity")
        
        try:
            results = self.sp.current_user_recently_played(limit=50)
            recent_tracks = []
            
            for item in results['items']:
                track = item['track']
                recent_tracks.append({
                    'id': track['id'],
                    'name': track['name'],
                    'artists': [{'id': a['id'], 'name': a['name']} for a in track['artists']],
                    'played_at': item['played_at'],
                    'popularity': track.get('popularity', 0)
                })
            
            return {
                'tracks': recent_tracks,
                'unique_artists': len(set(a['id'] for track in recent_tracks for a in track['artists'])),
                'total_plays': len(recent_tracks)
            }
            
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not get recent activity: {e}")
            return {'tracks': [], 'unique_artists': 0, 'total_plays': 0}
    
    def _analyze_genre_preferences(self, top_artists: Dict, top_tracks: Dict) -> Dict:
        """Analyze user's genre preferences and patterns."""
        print(f"  • Analyzing genre preferences")
        
        # Collect all genres from top artists
        all_genres = []
        genre_by_time = {}
        
        for time_range, artists in top_artists.items():
            time_genres = []
            for artist in artists:
                genres = artist.get('genres', [])
                all_genres.extend(genres)
                time_genres.extend(genres)
            genre_by_time[time_range] = Counter(time_genres)
        
        genre_counts = Counter(all_genres)
        
        # Calculate genre diversity score
        total_genres = len(genre_counts)
        unique_genres = len([g for g, count in genre_counts.items() if count == 1])
        diversity_score = unique_genres / max(total_genres, 1)
        
        # Identify niche vs mainstream genres
        mainstream_genres = {'pop', 'rock', 'hip hop', 'electronic', 'country', 'r&b'}
        niche_preference = sum(1 for genre in genre_counts.keys() 
                              if not any(main in genre.lower() for main in mainstream_genres))
        niche_ratio = niche_preference / max(total_genres, 1)
        
        return {
            'top_genres': dict(genre_counts.most_common(20)),
            'genre_diversity_score': diversity_score,
            'niche_preference_ratio': niche_ratio,
            'by_time_range': genre_by_time,
            'total_unique_genres': total_genres
        }
    
    def _analyze_audio_preferences(self, top_tracks: Dict) -> Dict:
        """Analyze user's audio feature preferences (energy, valence, etc.)."""
        print(f"  • Analyzing audio feature preferences")
        
        # Collect audio features from all time ranges
        all_features = []
        for time_range, tracks in top_tracks.items():
            for track in tracks:
                if track.get('audio_features'):
                    all_features.append(track['audio_features'])
        
        if not all_features:
            print(f"    {Fore.YELLOW}No audio features available - using genre-based analysis only")
            return {
                'error': 'No audio features available', 
                'feature_preferences': {},
                'listening_style': {
                    'energy': 'unknown',
                    'mood': 'unknown'
                },
                'sample_size': 0
            }
        
        # Calculate average preferences
        feature_keys = ['danceability', 'energy', 'speechiness', 'acousticness', 
                       'instrumentalness', 'liveness', 'valence', 'tempo']
        
        preferences = {}
        for key in feature_keys:
            values = [f[key] for f in all_features if f and f.get(key) is not None]
            if values:
                preferences[key] = {
                    'average': sum(values) / len(values),
                    'std_dev': math.sqrt(sum((x - sum(values)/len(values))**2 for x in values) / len(values)),
                    'range': (min(values), max(values))
                }
        
        # Categorize listening style
        if preferences.get('energy', {}).get('average', 0.5) > 0.7:
            energy_style = 'high_energy'
        elif preferences.get('energy', {}).get('average', 0.5) < 0.3:
            energy_style = 'low_energy'
        else:
            energy_style = 'mixed_energy'
        
        if preferences.get('valence', {}).get('average', 0.5) > 0.7:
            mood_style = 'upbeat'
        elif preferences.get('valence', {}).get('average', 0.5) < 0.3:
            mood_style = 'melancholic'
        else:
            mood_style = 'varied_mood'
        
        return {
            'feature_preferences': preferences,
            'listening_style': {
                'energy': energy_style,
                'mood': mood_style
            },
            'sample_size': len(all_features)
        }
    
    def _analyze_discovery_patterns(self, top_artists: Dict) -> Dict:
        """Analyze user's discovery patterns (mainstream vs niche preference)."""
        print(f"  • Analyzing music discovery patterns")
        
        all_artists = []
        for time_range, artists in top_artists.items():
            all_artists.extend(artists)
        
        if not all_artists:
            return {'error': 'No artists data available'}
        
        # Analyze popularity distribution
        popularities = [artist['popularity'] for artist in all_artists]
        followers = [artist['followers'] for artist in all_artists]
        
        avg_popularity = sum(popularities) / len(popularities)
        avg_followers = sum(followers) / len(followers)
        
        # Count artists by popularity ranges
        mainstream_count = len([p for p in popularities if p >= 70])
        moderate_count = len([p for p in popularities if 40 <= p < 70])
        niche_count = len([p for p in popularities if p < 40])
        
        # Calculate discovery preference score
        total_artists = len(all_artists)
        mainstream_ratio = mainstream_count / total_artists
        niche_ratio = niche_count / total_artists
        
        # Determine discovery style
        if niche_ratio > 0.5:
            discovery_style = 'niche_explorer'
        elif mainstream_ratio > 0.6:
            discovery_style = 'mainstream_focused'
        else:
            discovery_style = 'balanced_discovery'
        
        return {
            'average_popularity': avg_popularity,
            'average_followers': avg_followers,
            'popularity_distribution': {
                'mainstream': mainstream_count,
                'moderate': moderate_count,
                'niche': niche_count
            },
            'discovery_ratios': {
                'mainstream': mainstream_ratio,
                'niche': niche_ratio,
                'moderate': moderate_count / total_artists
            },
            'discovery_style': discovery_style
        }
    
    def _create_taste_markers(self, profile: Dict) -> Dict:
        """Create taste markers for similarity matching with other artists."""
        print(f"  • Creating taste similarity markers")
        
        markers = {
            'preferred_genres': [],
            'audio_profile': {},
            'discovery_preference': '',
            'artist_characteristics': {}
        }
        
        # Extract preferred genres
        genre_prefs = profile.get('genre_preferences', {})
        if genre_prefs.get('top_genres'):
            markers['preferred_genres'] = list(genre_prefs['top_genres'].keys())[:10]
        
        # Extract audio profile
        audio_prefs = profile.get('audio_features_preferences', {})
        if audio_prefs.get('feature_preferences'):
            markers['audio_profile'] = {
                key: prefs['average'] 
                for key, prefs in audio_prefs['feature_preferences'].items()
            }
        
        # Extract discovery preference
        discovery = profile.get('discovery_patterns', {})
        markers['discovery_preference'] = discovery.get('discovery_style', 'balanced_discovery')
        
        # Extract artist characteristics from top artists
        all_top_artists = []
        for time_range, artists in profile.get('top_artists', {}).items():
            all_top_artists.extend(artists)
        
        if all_top_artists:
            # Calculate average characteristics of liked artists
            total_popularity = sum(a['popularity'] for a in all_top_artists)
            total_followers = sum(a['followers'] for a in all_top_artists)
            
            markers['artist_characteristics'] = {
                'avg_popularity': total_popularity / len(all_top_artists),
                'avg_followers': total_followers / len(all_top_artists),
                'follows_niche_artists': discovery.get('discovery_ratios', {}).get('niche', 0) > 0.3
            }
        
        return markers
    
    def _analyze_listening_diversity(self, profile: Dict) -> Dict:
        """Analyze how diverse the user's listening habits are."""
        print(f"  • Analyzing listening diversity")
        
        # Genre diversity
        genre_diversity = profile.get('genre_preferences', {}).get('genre_diversity_score', 0)
        
        # Artist diversity (how many different artists in top lists)
        all_artist_ids = set()
        for time_range, artists in profile.get('top_artists', {}).items():
            for artist in artists:
                all_artist_ids.add(artist['id'])
        
        # Popularity diversity
        all_artists = []
        for time_range, artists in profile.get('top_artists', {}).items():
            all_artists.extend(artists)
        
        if all_artists:
            popularities = [a['popularity'] for a in all_artists]
            pop_std_dev = math.sqrt(sum((x - sum(popularities)/len(popularities))**2 for x in popularities) / len(popularities))
            popularity_diversity = min(pop_std_dev / 50, 1.0)  # Normalize to 0-1
        else:
            popularity_diversity = 0
        
        return {
            'genre_diversity': genre_diversity,
            'artist_count': len(all_artist_ids),
            'popularity_diversity': popularity_diversity,
            'overall_diversity_score': (genre_diversity + popularity_diversity) / 2
        }

def calculate_personal_relevance_score(artist_data: Dict, user_profile: Dict) -> Dict:
    """
    Calculate personal relevance score for an artist based on user's taste profile.
    
    This balances general popularity with personal taste alignment.
    """
    taste_markers = user_profile.get('taste_markers', {})
    discovery_patterns = user_profile.get('discovery_patterns', {})
    genre_preferences = user_profile.get('genre_preferences', {})
    
    # Initialize scoring components
    genre_similarity = 0.0
    popularity_alignment = 0.0
    discovery_style_match = 0.0
    
    # 1. Genre similarity score (0-40 points)
    artist_genres = artist_data.get('genres', [])
    preferred_genres = taste_markers.get('preferred_genres', [])
    
    if artist_genres and preferred_genres:
        # Calculate genre overlap
        genre_matches = sum(1 for genre in artist_genres 
                           if any(pref.lower() in genre.lower() or genre.lower() in pref.lower() 
                                 for pref in preferred_genres))
        genre_similarity = min(40, (genre_matches / len(artist_genres)) * 40)
    
    # 2. Popularity alignment with user's discovery style (0-30 points)
    artist_popularity = artist_data.get('popularity', 0)
    user_discovery_style = taste_markers.get('discovery_preference', 'balanced_discovery')
    user_avg_popularity = taste_markers.get('artist_characteristics', {}).get('avg_popularity', 50)
    
    if user_discovery_style == 'niche_explorer':
        # Reward lower popularity artists
        if artist_popularity < 40:
            popularity_alignment = 30
        elif artist_popularity < 60:
            popularity_alignment = 20
        else:
            popularity_alignment = 10
    elif user_discovery_style == 'mainstream_focused':
        # Reward higher popularity artists
        if artist_popularity > 60:
            popularity_alignment = 30
        elif artist_popularity > 40:
            popularity_alignment = 20
        else:
            popularity_alignment = 10
    else:  # balanced_discovery
        # Reward artists similar to user's average
        diff = abs(artist_popularity - user_avg_popularity)
        popularity_alignment = max(0, 30 - (diff / 2))
    
    # 3. Discovery style match (0-30 points)
    # This considers whether the artist fits the user's pattern of discovery
    niche_preference = discovery_patterns.get('discovery_ratios', {}).get('niche', 0)
    
    if niche_preference > 0.4:  # User likes niche artists
        if artist_popularity < 30:
            discovery_style_match = 30
        elif artist_popularity < 50:
            discovery_style_match = 20
        else:
            discovery_style_match = 5
    else:  # User likes more popular artists
        if artist_popularity > 50:
            discovery_style_match = 30
        elif artist_popularity > 30:
            discovery_style_match = 20
        else:
            discovery_style_match = 10
    
    # Calculate final personal relevance score
    personal_relevance = genre_similarity + popularity_alignment + discovery_style_match
    
    # Combine with basic popularity score (external validation still important)
    spotify_base_score = artist_data.get('base_score', 0)
    external_score = artist_data.get('external_validation', {}).get('external_data', {}).get('cross_platform_score', 0)
    
    # Weighted combination that prioritizes personal relevance
    if personal_relevance > 60:
        # High personal relevance - weight heavily toward personal taste
        final_score = (personal_relevance * 0.7) + (spotify_base_score * 0.2) + (external_score * 0.1)
        confidence = "high_personal_match"
    elif personal_relevance > 40:
        # Moderate personal relevance - balanced approach
        final_score = (personal_relevance * 0.5) + (spotify_base_score * 0.3) + (external_score * 0.2)
        confidence = "moderate_personal_match"
    else:
        # Low personal relevance - rely more on general popularity
        final_score = (personal_relevance * 0.3) + (spotify_base_score * 0.4) + (external_score * 0.3)
        confidence = "low_personal_match"
    
    return {
        'personal_relevance_score': personal_relevance,
        'final_score': final_score,
        'confidence': confidence,
        'scoring_breakdown': {
            'genre_similarity': genre_similarity,
            'popularity_alignment': popularity_alignment,
            'discovery_style_match': discovery_style_match,
            'spotify_base_score': spotify_base_score,
            'external_score': external_score
        },
        'recommendation': {
            'safe_to_unfollow': final_score < 30,  # More conservative threshold
            'personal_relevance': personal_relevance > 50,
            'reasoning': _get_scoring_reasoning(personal_relevance, artist_data, user_profile)
        }
    }

def _get_scoring_reasoning(personal_relevance: float, artist_data: Dict, user_profile: Dict) -> str:
    """Generate human-readable reasoning for the score."""
    artist_name = artist_data.get('name', 'Unknown Artist')
    
    if personal_relevance > 60:
        return f"{artist_name} strongly matches your personal taste profile"
    elif personal_relevance > 40:
        return f"{artist_name} moderately aligns with your listening preferences"
    elif personal_relevance > 20:
        return f"{artist_name} has some alignment with your taste but limited"
    else:
        return f"{artist_name} does not match your typical listening patterns"

if __name__ == "__main__":
    # Test the personal relevance analyzer
    print("Personal Relevance Analyzer Test")
    print("This would normally be called by the main cleanup script")