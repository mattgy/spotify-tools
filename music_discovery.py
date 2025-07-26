#!/usr/bin/env python3
"""
Advanced Music Discovery Engine combining multiple data sources.
"""

import sys
import os
from typing import Dict, List, Set, Any, Optional
from collections import defaultdict, Counter
import random

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from musicbrainz_integration import mb_client
from cache_utils import save_to_cache, load_from_cache
from config import get_cache_expiration, config

class MusicDiscoveryEngine:
    """Advanced music discovery engine combining multiple sources."""
    
    def __init__(self):
        self.cache_expiration = get_cache_expiration()
        self.confidence_threshold = config.get("confidence_threshold", 0.8)
        self.similar_artist_limit = config.get("similar_artist_limit", 20)
    
    def discover_artists(self, 
                        user_artists: List[Dict[str, Any]], 
                        lastfm_client=None,
                        spotify_client=None) -> List[Dict[str, Any]]:
        """
        Discover new artists using multiple data sources.
        
        Args:
            user_artists: List of user's current artists
            lastfm_client: Optional Last.fm client for additional recommendations
            spotify_client: Spotify client for recommendations
            
        Returns:
            List of recommended artists with confidence scores
        """
        cache_key = "discovery_recommendations"
        cached_result = load_from_cache(cache_key, self.cache_expiration // 2)  # Shorter cache for discovery
        
        if cached_result is not None:
            return cached_result
        
        print("🔍 Analyzing your music taste...")
        
        # Analyze user's music patterns
        user_analysis = self._analyze_user_taste(user_artists)
        
        print("🎵 Discovering similar artists from multiple sources...")
        
        # Collect recommendations from various sources
        all_recommendations = []
        
        # Source 1: MusicBrainz relationships and tags
        mb_recommendations = self._get_musicbrainz_recommendations(user_artists)
        all_recommendations.extend(mb_recommendations)
        
        # Source 2: Last.fm similar artists (if available)
        if lastfm_client:
            lastfm_recommendations = self._get_lastfm_recommendations(user_artists, lastfm_client)
            all_recommendations.extend(lastfm_recommendations)
        
        # Source 3: Spotify recommendations (if available)
        if spotify_client:
            spotify_recommendations = self._get_spotify_recommendations(user_artists, spotify_client)
            all_recommendations.extend(spotify_recommendations)
        
        # Source 4: Genre and tag-based discovery
        genre_recommendations = self._get_genre_based_recommendations(user_analysis)
        all_recommendations.extend(genre_recommendations)
        
        print("📊 Analyzing and ranking recommendations...")
        
        # Score and rank all recommendations
        final_recommendations = self._score_and_rank_recommendations(
            all_recommendations, user_analysis, user_artists
        )
        
        save_to_cache(final_recommendations, cache_key)
        return final_recommendations
    
    def _analyze_user_taste(self, user_artists: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze user's musical taste patterns."""
        analysis = {
            'genres': Counter(),
            'countries': Counter(),
            'time_periods': Counter(),
            'artist_types': Counter(),
            'tags': Counter(),
            'total_artists': len(user_artists)
        }
        
        for artist in user_artists:
            # Analyze Spotify data
            if 'genres' in artist:
                analysis['genres'].update(artist['genres'])
            
            # Enrich with MusicBrainz data for deeper analysis
            enriched = mb_client.enrich_artist_data(artist)
            mb_data = enriched.get('musicbrainz', {})
            
            if mb_data.get('country'):
                analysis['countries'][mb_data['country']] += 1
            
            if mb_data.get('type'):
                analysis['artist_types'][mb_data['type']] += 1
            
            if mb_data.get('tags'):
                analysis['tags'].update(mb_data['tags'][:5])  # Top 5 tags per artist
            
            # Analyze time periods
            begin_date = mb_data.get('begin_date', '')
            if begin_date and len(begin_date) >= 4:
                try:
                    year = int(begin_date[:4])
                    if year < 1960:
                        period = "Pre-1960"
                    elif year < 1980:
                        period = "1960s-1970s"
                    elif year < 2000:
                        period = "1980s-1990s"
                    elif year < 2010:
                        period = "2000s"
                    else:
                        period = "2010s+"
                    analysis['time_periods'][period] += 1
                except ValueError:
                    pass
        
        return analysis
    
    def _get_musicbrainz_recommendations(self, user_artists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get recommendations from MusicBrainz relationships and tags."""
        recommendations = []
        
        # Sample artists to avoid overwhelming the API
        sample_artists = random.sample(user_artists, min(10, len(user_artists)))
        
        for artist in sample_artists:
            similar = mb_client.get_similar_artists(artist.get('name', ''))
            for similar_artist in similar:
                recommendations.append({
                    'name': similar_artist['name'],
                    'source': 'musicbrainz',
                    'confidence': similar_artist['confidence'],
                    'reason': similar_artist['source'],
                    'seed_artist': artist.get('name', ''),
                    'mbid': similar_artist.get('mbid')
                })
        
        return recommendations
    
    def _get_lastfm_recommendations(self, user_artists: List[Dict[str, Any]], lastfm_client) -> List[Dict[str, Any]]:
        """Get recommendations from Last.fm API."""
        recommendations = []
        
        # Sample artists for Last.fm API
        sample_artists = random.sample(user_artists, min(15, len(user_artists)))
        
        for artist in sample_artists:
            try:
                # Use Last.fm client to get similar artists
                similar = lastfm_client.get_similar_artists(artist.get('name', ''))
                for similar_artist in similar:
                    recommendations.append({
                        'name': similar_artist.get('name', ''),
                        'source': 'lastfm',
                        'confidence': min(float(similar_artist.get('match', 0.5)), 1.0),
                        'reason': 'Last.fm similar artists',
                        'seed_artist': artist.get('name', ''),
                        'playcount': similar_artist.get('playcount', 0)
                    })
            except Exception as e:
                print(f"Error getting Last.fm recommendations for {artist.get('name', '')}: {e}")
        
        return recommendations
    
    def _get_spotify_recommendations(self, user_artists: List[Dict[str, Any]], spotify_client) -> List[Dict[str, Any]]:
        """Get recommendations from Spotify's recommendation engine."""
        recommendations = []
        
        try:
            # Get seed artists (max 5 for Spotify API)
            seed_artists = [artist['id'] for artist in user_artists[:5] if 'id' in artist]
            
            if seed_artists:
                # Get Spotify recommendations
                result = spotify_client.recommendations(
                    seed_artists=seed_artists,
                    limit=50
                )
                
                for track in result.get('tracks', []):
                    for artist in track.get('artists', []):
                        recommendations.append({
                            'name': artist.get('name', ''),
                            'source': 'spotify',
                            'confidence': 0.7,  # Spotify recommendations are generally good
                            'reason': 'Spotify recommendations',
                            'spotify_id': artist.get('id'),
                            'track_context': track.get('name', '')
                        })
        except Exception as e:
            print(f"Error getting Spotify recommendations: {e}")
        
        return recommendations
    
    def _get_genre_based_recommendations(self, user_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get recommendations based on genre and tag analysis."""
        recommendations = []
        
        # Get top genres and tags
        top_genres = user_analysis['genres'].most_common(5)
        top_tags = user_analysis['tags'].most_common(10)
        
        # Search for artists in similar genres/tags
        for genre, count in top_genres:
            try:
                # Search MusicBrainz for artists with this genre/tag
                search_results = mb_client.search_artist(f'tag:{genre}', limit=10)
                for artist in search_results:
                    confidence = min(0.6 + (count / user_analysis['total_artists']) * 0.3, 0.9)
                    recommendations.append({
                        'name': artist.get('name', ''),
                        'source': 'genre_analysis',
                        'confidence': confidence,
                        'reason': f'Popular in your {genre} listening',
                        'genre': genre,
                        'mbid': artist.get('mbid')
                    })
            except Exception as e:
                print(f"Error searching for genre {genre}: {e}")
        
        return recommendations
    
    def _score_and_rank_recommendations(self, 
                                       all_recommendations: List[Dict[str, Any]], 
                                       user_analysis: Dict[str, Any],
                                       user_artists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score and rank all recommendations."""
        # Remove artists user already follows
        user_artist_names = {artist.get('name', '').lower() for artist in user_artists}
        
        # Group recommendations by artist name
        artist_recommendations = defaultdict(list)
        for rec in all_recommendations:
            artist_name = rec.get('name', '').lower()
            if artist_name and artist_name not in user_artist_names:
                artist_recommendations[artist_name].append(rec)
        
        # Calculate final scores
        final_recommendations = []
        for artist_name, recs in artist_recommendations.items():
            if not recs:
                continue
            
            # Base score from multiple sources
            total_confidence = sum(rec.get('confidence', 0.5) for rec in recs)
            source_diversity = len(set(rec.get('source', '') for rec in recs))
            recommendation_count = len(recs)
            
            # Calculate final score
            final_score = (
                (total_confidence / recommendation_count) * 0.6 +  # Average confidence
                min(source_diversity * 0.2, 0.3) +                 # Source diversity bonus
                min(recommendation_count * 0.05, 0.1)              # Multiple recommendation bonus
            )
            
            # Take the most detailed recommendation
            best_rec = max(recs, key=lambda x: len(str(x)))
            best_rec['final_score'] = min(final_score, 1.0)
            best_rec['recommendation_count'] = recommendation_count
            best_rec['sources'] = list(set(rec.get('source', '') for rec in recs))
            
            final_recommendations.append(best_rec)
        
        # Sort by final score and apply confidence threshold
        final_recommendations.sort(key=lambda x: x['final_score'], reverse=True)
        filtered_recommendations = [
            rec for rec in final_recommendations 
            if rec['final_score'] >= self.confidence_threshold
        ]
        
        return filtered_recommendations[:self.similar_artist_limit]
    
    def get_discovery_insights(self, user_artists: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get insights about user's music taste for discovery purposes."""
        analysis = self._analyze_user_taste(user_artists)
        
        insights = {
            'top_genres': analysis['genres'].most_common(10),
            'top_countries': analysis['countries'].most_common(5),
            'time_period_distribution': dict(analysis['time_periods']),
            'artist_type_distribution': dict(analysis['artist_types']),
            'discovery_suggestions': []
        }
        
        # Generate discovery suggestions
        if analysis['genres']:
            top_genre = analysis['genres'].most_common(1)[0][0]
            insights['discovery_suggestions'].append(
                f"Explore more {top_genre} artists"
            )
        
        if analysis['countries']:
            top_country = analysis['countries'].most_common(1)[0][0]
            insights['discovery_suggestions'].append(
                f"Discover more artists from {top_country}"
            )
        
        if analysis['time_periods']:
            periods = list(analysis['time_periods'].keys())
            if len(periods) > 1:
                insights['discovery_suggestions'].append(
                    "Try exploring different time periods of music"
                )
        
        return insights

# Global discovery engine instance
discovery_engine = MusicDiscoveryEngine()