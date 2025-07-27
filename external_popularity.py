#!/usr/bin/env python3
"""
External popularity validation for artists using multiple APIs.

This module cross-references artist popularity across different platforms
to provide a more comprehensive view than Spotify's internal metrics alone.

APIs used:
- Last.fm (play counts, listener counts)
- MusicBrainz (comprehensive metadata, tags)
- Wikipedia (if available via MusicBrainz)
- YouTube Music (via search popularity)

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import time
import json
import requests
from typing import Dict, List, Optional, Tuple
import re
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from cache_utils import save_to_cache, load_from_cache
from credentials_manager import get_lastfm_api_key

# Cache expiration for external API calls (longer since this data changes slowly)
EXTERNAL_CACHE_EXPIRATION = 60 * 60 * 24 * 30  # 30 days

class ExternalPopularityChecker:
    """Check artist popularity across multiple external platforms."""
    
    def __init__(self):
        self.lastfm_api_key = self._get_lastfm_key()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SpotifyTools/1.0 (https://github.com/your-repo)'
        })
    
    def _get_lastfm_key(self):
        """Get Last.fm API key."""
        try:
            return get_lastfm_api_key()
        except:
            return None
    
    def get_comprehensive_popularity(self, artist_name: str, spotify_data: dict = None) -> Dict:
        """
        Get comprehensive popularity data for an artist across multiple platforms.
        
        Args:
            artist_name: Name of the artist
            spotify_data: Optional Spotify artist data for cross-reference
            
        Returns:
            Dict with popularity metrics from various sources
        """
        cache_key = f"external_popularity_{artist_name.lower().replace(' ', '_')}"
        cached_data = load_from_cache(cache_key, EXTERNAL_CACHE_EXPIRATION)
        
        if cached_data:
            return cached_data
        
        print(f"{Fore.BLUE}Checking external popularity for: {artist_name}")
        
        popularity_data = {
            'artist_name': artist_name,
            'lastfm': self._get_lastfm_data(artist_name),
            'musicbrainz': self._get_musicbrainz_data(artist_name),
            'youtube_search': self._get_youtube_search_popularity(artist_name),
            'cross_platform_score': 0,
            'popularity_indicators': [],
            'warning_flags': []
        }
        
        # Calculate cross-platform popularity score
        popularity_data['cross_platform_score'] = self._calculate_cross_platform_score(popularity_data)
        
        # Add popularity indicators and warnings
        self._add_popularity_analysis(popularity_data, spotify_data)
        
        # Cache the results
        save_to_cache(popularity_data, cache_key)
        
        return popularity_data
    
    def _get_lastfm_data(self, artist_name: str) -> Dict:
        """Get Last.fm artist data."""
        if not self.lastfm_api_key:
            return {'error': 'No Last.fm API key available'}
        
        try:
            # Get artist info
            url = "http://ws.audioscrobbler.com/2.0/"
            params = {
                'method': 'artist.getinfo',
                'artist': artist_name,
                'api_key': self.lastfm_api_key,
                'format': 'json'
            }
            
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'artist' in data:
                    artist_data = data['artist']
                    return {
                        'name': artist_data.get('name', artist_name),
                        'listeners': int(artist_data.get('stats', {}).get('listeners', 0)),
                        'playcount': int(artist_data.get('stats', {}).get('playcount', 0)),
                        'tags': [tag['name'] for tag in artist_data.get('tags', {}).get('tag', [])],
                        'url': artist_data.get('url', ''),
                        'bio_summary': artist_data.get('bio', {}).get('summary', ''),
                        'similar_artists': [
                            sim['name'] for sim in artist_data.get('similar', {}).get('artist', [])[:5]
                        ]
                    }
                else:
                    return {'error': 'Artist not found on Last.fm'}
            else:
                return {'error': f'Last.fm API error: {response.status_code}'}
                
        except Exception as e:
            return {'error': f'Last.fm API exception: {str(e)}'}
    
    def _get_musicbrainz_data(self, artist_name: str) -> Dict:
        """Get MusicBrainz artist data."""
        try:
            # Search for artist
            url = "https://musicbrainz.org/ws/2/artist"
            params = {
                'query': f'artist:"{artist_name}"',
                'fmt': 'json',
                'limit': 5
            }
            
            response = self.session.get(url, params=params, timeout=10)
            time.sleep(1)  # Be respectful to MusicBrainz
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('artists'):
                    # Find best match
                    best_match = None
                    for artist in data['artists']:
                        if artist['name'].lower() == artist_name.lower():
                            best_match = artist
                            break
                    
                    if not best_match:
                        best_match = data['artists'][0]  # Take first result
                    
                    # Get detailed info if we have an ID
                    if best_match.get('id'):
                        detail_url = f"https://musicbrainz.org/ws/2/artist/{best_match['id']}"
                        detail_params = {
                            'inc': 'aliases+tags+genres+releases+release-groups',
                            'fmt': 'json'
                        }
                        
                        detail_response = self.session.get(detail_url, params=detail_params, timeout=10)
                        time.sleep(1)
                        
                        if detail_response.status_code == 200:
                            detail_data = detail_response.json()
                            
                            return {
                                'name': detail_data.get('name', artist_name),
                                'id': detail_data.get('id'),
                                'type': detail_data.get('type', ''),
                                'country': detail_data.get('country', ''),
                                'begin_year': detail_data.get('life-span', {}).get('begin', ''),
                                'genres': [genre['name'] for genre in detail_data.get('genres', [])],
                                'tags': [tag['name'] for tag in detail_data.get('tags', [])],
                                'aliases': [alias['name'] for alias in detail_data.get('aliases', [])],
                                'release_groups': len(detail_data.get('release-groups', [])),
                                'releases': len(detail_data.get('releases', []))
                            }
                
                return {'error': 'Artist not found on MusicBrainz'}
            else:
                return {'error': f'MusicBrainz API error: {response.status_code}'}
                
        except Exception as e:
            return {'error': f'MusicBrainz API exception: {str(e)}'}
    
    def _get_youtube_search_popularity(self, artist_name: str) -> Dict:
        """
        Estimate YouTube popularity through search result analysis.
        Note: This is a simplified approach since YouTube Data API requires API key.
        """
        try:
            # Use a simple web search approach to estimate popularity
            # This is basic but can give us some signal
            
            search_terms = [
                f'"{artist_name}" music',
                f'"{artist_name}" songs',
                f'"{artist_name}" live'
            ]
            
            popularity_signals = {
                'search_variations': len(search_terms),
                'estimated_popularity': 'unknown',
                'note': 'Limited data without YouTube API key'
            }
            
            # Could be enhanced with YouTube Data API in the future
            return popularity_signals
            
        except Exception as e:
            return {'error': f'YouTube search exception: {str(e)}'}
    
    def _calculate_cross_platform_score(self, popularity_data: Dict) -> float:
        """Calculate a cross-platform popularity score (0-100)."""
        import math
        
        external_score = 0.0
        weight_sum = 0.0
        
        # Last.fm factors (if available) - Weight: 60%
        lastfm = popularity_data.get('lastfm', {})
        if not lastfm.get('error'):
            listeners = lastfm.get('listeners', 0)
            playcount = lastfm.get('playcount', 0)
            
            # Listeners score (0-60 scale)
            if listeners > 0:
                listener_score = min(60, max(0, math.log10(listeners) * 9))
                external_score += listener_score * 0.6
                weight_sum += 0.6
            
            # Playcount provides additional signal (0-30 scale)
            if playcount > 0:
                play_score = min(30, max(0, math.log10(playcount) * 5))
                external_score += play_score * 0.3
                weight_sum += 0.3
        
        # MusicBrainz factors (if available) - Weight: 30%
        mb = popularity_data.get('musicbrainz', {})
        if not mb.get('error'):
            releases = mb.get('releases', 0)
            
            # Artists with many releases are generally more established
            if releases > 0:
                release_score = min(30, max(0, math.log10(releases + 1) * 12))
                external_score += release_score * 0.3
                weight_sum += 0.3
        
        # Normalize by actual weights (in case some data is missing)
        if weight_sum > 0:
            external_score = external_score / weight_sum * 100
        
        return min(100, max(0, external_score))
    
    def calculate_final_artist_score(self, spotify_data: dict, external_data: dict) -> Dict:
        """
        Calculate final comprehensive artist importance score.
        
        Combines Spotify data with external platform data to create a single
        0-100 score that better represents true artist popularity.
        """
        # Get Spotify base score
        spotify_base = spotify_data.get('base_score', 0)
        
        # Get external cross-platform score
        external_score = external_data.get('cross_platform_score', 0)
        
        # Weighted combination:
        # - If external score is significantly higher, trust it more
        # - If external score is low/missing, rely on Spotify data
        # - Balanced approach for moderate scores
        
        if external_score > 40:
            # High external popularity - weight heavily toward external data
            final_score = (spotify_base * 0.3) + (external_score * 0.7)
            confidence = "high"
            reasoning = "Strong external platform presence"
        elif external_score > 20:
            # Moderate external popularity - balanced approach  
            final_score = (spotify_base * 0.5) + (external_score * 0.5)
            confidence = "medium"
            reasoning = "Moderate cross-platform presence"
        elif external_score > 0:
            # Low external data - lean toward Spotify but consider external
            final_score = (spotify_base * 0.7) + (external_score * 0.3)
            confidence = "medium"
            reasoning = "Limited external data available"
        else:
            # No external data - use Spotify data only
            final_score = spotify_base
            confidence = "low"
            reasoning = "No external validation data"
        
        return {
            'final_score': final_score,
            'spotify_base_score': spotify_base,
            'external_score': external_score,
            'confidence': confidence,
            'reasoning': reasoning,
            'recommendation': {
                'safe_to_unfollow': final_score < 25,  # Conservative threshold
                'confidence_level': confidence
            }
        }
    
    def _add_popularity_analysis(self, popularity_data: Dict, spotify_data: dict = None):
        """Add human-readable popularity analysis."""
        cross_score = popularity_data['cross_platform_score']
        indicators = []
        warnings = []
        
        # Last.fm analysis
        lastfm = popularity_data.get('lastfm', {})
        if not lastfm.get('error'):
            listeners = lastfm.get('listeners', 0)
            playcount = lastfm.get('playcount', 0)
            
            if listeners > 100000:
                indicators.append(f"High Last.fm listeners ({listeners:,})")
            elif listeners > 10000:
                indicators.append(f"Moderate Last.fm listeners ({listeners:,})")
            elif listeners > 1000:
                indicators.append(f"Some Last.fm listeners ({listeners:,})")
            else:
                warnings.append(f"Low Last.fm listeners ({listeners:,})")
            
            if playcount > 1000000:
                indicators.append(f"High Last.fm plays ({playcount:,})")
        
        # MusicBrainz analysis
        mb = popularity_data.get('musicbrainz', {})
        if not mb.get('error'):
            releases = mb.get('releases', 0)
            if releases > 10:
                indicators.append(f"Prolific artist ({releases} releases)")
            elif releases > 5:
                indicators.append(f"Established artist ({releases} releases)")
        
        # Cross-reference with Spotify data
        if spotify_data:
            spotify_pop = spotify_data.get('popularity', 0)
            spotify_followers = spotify_data.get('followers', {}).get('total', 0)
            
            # Flag potential discrepancies
            if cross_score > 40 and spotify_pop < 20:
                warnings.append("HIGH EXTERNAL POPULARITY but low Spotify score - check manually!")
            
            if cross_score > 30 and spotify_followers < 1000:
                warnings.append("External popularity suggests this artist may be more popular than Spotify data indicates")
        
        popularity_data['popularity_indicators'] = indicators
        popularity_data['warning_flags'] = warnings

def validate_artist_for_unfollowing(artist_name: str, spotify_data: dict) -> Dict:
    """
    Validate whether an artist should be considered for unfollowing.
    
    Returns comprehensive analysis with recommendation.
    """
    checker = ExternalPopularityChecker()
    external_data = checker.get_comprehensive_popularity(artist_name, spotify_data)
    
    # Make recommendation
    recommendation = {
        'safe_to_unfollow': True,
        'confidence': 'medium',
        'reason': '',
        'should_check_manually': False
    }
    
    cross_score = external_data.get('cross_platform_score', 0)
    warnings = external_data.get('warning_flags', [])
    
    if cross_score > 50:
        recommendation['safe_to_unfollow'] = False
        recommendation['confidence'] = 'high'
        recommendation['reason'] = 'High external popularity score - likely a popular artist'
    elif cross_score > 30:
        recommendation['safe_to_unfollow'] = False
        recommendation['confidence'] = 'medium'
        recommendation['reason'] = 'Moderate external popularity - recommend keeping'
    elif warnings:
        recommendation['should_check_manually'] = True
        recommendation['confidence'] = 'low'
        recommendation['reason'] = 'Conflicting data between platforms - manual review recommended'
    
    return {
        'external_data': external_data,
        'recommendation': recommendation
    }

def print_artist_popularity_report(artist_name: str, spotify_data: dict = None):
    """Print a detailed popularity report for an artist."""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}External Popularity Report: {artist_name}")
    print("=" * 60)
    
    validation = validate_artist_for_unfollowing(artist_name, spotify_data)
    external_data = validation['external_data']
    recommendation = validation['recommendation']
    
    # Last.fm data
    lastfm = external_data.get('lastfm', {})
    if not lastfm.get('error'):
        print(f"\n{Fore.YELLOW}Last.fm Data:")
        print(f"  Listeners: {lastfm.get('listeners', 0):,}")
        print(f"  Play count: {lastfm.get('playcount', 0):,}")
        if lastfm.get('tags'):
            print(f"  Genres: {', '.join(lastfm['tags'][:5])}")
    else:
        print(f"\n{Fore.RED}Last.fm: {lastfm.get('error', 'No data')}")
    
    # MusicBrainz data
    mb = external_data.get('musicbrainz', {})
    if not mb.get('error'):
        print(f"\n{Fore.BLUE}MusicBrainz Data:")
        print(f"  Type: {mb.get('type', 'Unknown')}")
        print(f"  Country: {mb.get('country', 'Unknown')}")
        print(f"  Releases: {mb.get('releases', 0)}")
        if mb.get('genres'):
            print(f"  Genres: {', '.join(mb['genres'][:5])}")
    else:
        print(f"\n{Fore.RED}MusicBrainz: {mb.get('error', 'No data')}")
    
    # Cross-platform score
    print(f"\n{Fore.GREEN}Cross-Platform Popularity Score: {external_data.get('cross_platform_score', 0):.1f}/100")
    
    # Indicators
    indicators = external_data.get('popularity_indicators', [])
    if indicators:
        print(f"\n{Fore.GREEN}Popularity Indicators:")
        for indicator in indicators:
            print(f"  ✅ {indicator}")
    
    # Warnings
    warnings = external_data.get('warning_flags', [])
    if warnings:
        print(f"\n{Fore.YELLOW}Warning Flags:")
        for warning in warnings:
            print(f"  ⚠️  {warning}")
    
    # Recommendation
    rec = recommendation
    color = Fore.RED if not rec['safe_to_unfollow'] else Fore.GREEN
    print(f"\n{color}{Style.BRIGHT}Recommendation:")
    print(f"{color}  Safe to unfollow: {'No' if not rec['safe_to_unfollow'] else 'Yes'}")
    print(f"{color}  Confidence: {rec['confidence']}")
    print(f"{color}  Reason: {rec['reason']}")
    
    if rec['should_check_manually']:
        print(f"\n{Fore.MAGENTA}💡 Manual Check Recommended:")
        print(f"  1. Open Spotify app and search for '{artist_name}'")
        print(f"  2. Check monthly listeners on artist page")
        print(f"  3. Listen to a few songs to refresh your memory")

if __name__ == "__main__":
    # Test the external popularity checker
    if len(sys.argv) > 1:
        artist_name = " ".join(sys.argv[1:])
        print_artist_popularity_report(artist_name)
    else:
        # Test with known examples
        test_artists = ["Lyrics Born", "Bobo Stenson Trio"]
        for artist in test_artists:
            print_artist_popularity_report(artist)
            print("\n" + "="*60 + "\n")