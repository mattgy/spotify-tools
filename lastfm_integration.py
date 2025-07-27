#!/usr/bin/env python3
"""
Last.fm integration for enhanced music recommendations and statistics.
"""

import requests
import time
import sys
import os
from typing import Dict, List, Optional, Any
import json

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from cache_utils import save_to_cache, load_from_cache
from constants import CACHE_EXPIRATION
from credentials_manager import get_lastfm_api_key

class LastFmClient:
    """Client for Last.fm API integration."""
    
    def __init__(self):
        self.api_key = get_lastfm_api_key()
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        self.cache_expiration = CACHE_EXPIRATION.get('long', 7 * 24 * 60 * 60)  # 7 days
        self.api_delay = 0.2  # Last.fm rate limit is generous
    
    def _make_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict]:
        """Make a request to Last.fm API with error handling and caching."""
        if not self.api_key:
            return {'error': 'No Last.fm API key configured'}
        
        # Create cache key from method and params
        cache_key = f"lastfm_{method}_{hash(str(sorted(params.items())))}"
        cached_result = load_from_cache(cache_key, self.cache_expiration)
        
        if cached_result is not None:
            return cached_result
        
        # Add required parameters
        params.update({
            'method': method,
            'api_key': self.api_key,
            'format': 'json'
        })
        
        try:
            time.sleep(self.api_delay)  # Rate limiting
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for Last.fm API errors
            if 'error' in data:
                error_result = {'error': data.get('message', 'Unknown Last.fm error')}
                save_to_cache(error_result, cache_key)
                return error_result
            
            save_to_cache(data, cache_key)
            return data
            
        except requests.exceptions.RequestException as e:
            error_result = {'error': f'Request failed: {str(e)}'}
            save_to_cache(error_result, cache_key)
            return error_result
        except json.JSONDecodeError:
            error_result = {'error': 'Invalid JSON response from Last.fm'}
            save_to_cache(error_result, cache_key)
            return error_result
    
    def get_artist_info(self, artist_name: str) -> Dict[str, Any]:
        """
        Get comprehensive artist information from Last.fm.
        
        Args:
            artist_name: Name of the artist
            
        Returns:
            Dictionary with artist information
        """
        data = self._make_request('artist.getinfo', {'artist': artist_name})
        
        if not data or 'error' in data:
            return data or {'error': 'No data returned'}
        
        artist = data.get('artist', {})
        
        return {
            'name': artist.get('name'),
            'mbid': artist.get('mbid'),
            'url': artist.get('url'),
            'image': self._extract_image_url(artist.get('image', [])),
            'listeners': int(artist.get('stats', {}).get('listeners', 0)),
            'playcount': int(artist.get('stats', {}).get('playcount', 0)),
            'bio': {
                'summary': artist.get('bio', {}).get('summary', ''),
                'content': artist.get('bio', {}).get('content', ''),
                'published': artist.get('bio', {}).get('published', '')
            },
            'tags': [tag.get('name') for tag in artist.get('tags', {}).get('tag', [])],
            'similar_artists': [
                {
                    'name': similar.get('name'),
                    'url': similar.get('url'),
                    'image': self._extract_image_url(similar.get('image', []))
                }
                for similar in artist.get('similar', {}).get('artist', [])
            ]
        }
    
    def get_similar_artists(self, artist_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get similar artists from Last.fm.
        
        Args:
            artist_name: Name of the artist
            limit: Maximum number of similar artists to return
            
        Returns:
            List of similar artist dictionaries
        """
        data = self._make_request('artist.getsimilar', {
            'artist': artist_name,
            'limit': limit
        })
        
        if not data or 'error' in data:
            return []
        
        similar_artists = []
        for artist in data.get('similarartists', {}).get('artist', []):
            similar_artists.append({
                'name': artist.get('name'),
                'mbid': artist.get('mbid'),
                'url': artist.get('url'),
                'image': self._extract_image_url(artist.get('image', [])),
                'match': float(artist.get('match', 0)),
                'streamable': artist.get('streamable') == '1'
            })
        
        return similar_artists
    
    def get_top_artists_by_tag(self, tag: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get top artists for a specific tag/genre.
        
        Args:
            tag: Musical tag/genre
            limit: Maximum number of artists to return
            
        Returns:
            List of artist dictionaries
        """
        data = self._make_request('tag.gettopartists', {
            'tag': tag,
            'limit': limit
        })
        
        if not data or 'error' in data:
            return []
        
        artists = []
        for artist in data.get('topartists', {}).get('artist', []):
            artists.append({
                'name': artist.get('name'),
                'mbid': artist.get('mbid'),
                'url': artist.get('url'),
                'image': self._extract_image_url(artist.get('image', [])),
                'listeners': int(artist.get('listeners', 0)),
                'playcount': int(artist.get('playcount', 0)),
                'rank': int(artist.get('@attr', {}).get('rank', 0))
            })
        
        return artists
    
    def get_track_info(self, artist_name: str, track_name: str) -> Dict[str, Any]:
        """
        Get track information from Last.fm.
        
        Args:
            artist_name: Name of the artist
            track_name: Name of the track
            
        Returns:
            Dictionary with track information
        """
        data = self._make_request('track.getinfo', {
            'artist': artist_name,
            'track': track_name
        })
        
        if not data or 'error' in data:
            return data or {'error': 'No data returned'}
        
        track = data.get('track', {})
        
        return {
            'name': track.get('name'),
            'mbid': track.get('mbid'),
            'url': track.get('url'),
            'duration': int(track.get('duration', 0)),
            'listeners': int(track.get('listeners', 0)),
            'playcount': int(track.get('playcount', 0)),
            'artist': {
                'name': track.get('artist', {}).get('name'),
                'mbid': track.get('artist', {}).get('mbid'),
                'url': track.get('artist', {}).get('url')
            },
            'album': {
                'name': track.get('album', {}).get('title'),
                'mbid': track.get('album', {}).get('mbid'),
                'url': track.get('album', {}).get('url'),
                'image': self._extract_image_url(track.get('album', {}).get('image', []))
            },
            'tags': [tag.get('name') for tag in track.get('toptags', {}).get('tag', [])],
            'wiki': {
                'summary': track.get('wiki', {}).get('summary', ''),
                'content': track.get('wiki', {}).get('content', '')
            }
        }
    
    def search_artists(self, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Search for artists on Last.fm.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of artist search results
        """
        data = self._make_request('artist.search', {
            'artist': query,
            'limit': limit
        })
        
        if not data or 'error' in data:
            return []
        
        artists = []
        for artist in data.get('results', {}).get('artistmatches', {}).get('artist', []):
            artists.append({
                'name': artist.get('name'),
                'mbid': artist.get('mbid'),
                'url': artist.get('url'),
                'image': self._extract_image_url(artist.get('image', [])),
                'listeners': int(artist.get('listeners', 0)),
                'streamable': artist.get('streamable') == '1'
            })
        
        return artists
    
    def get_top_tags(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get top tags/genres from Last.fm.
        
        Args:
            limit: Maximum number of tags to return
            
        Returns:
            List of tag dictionaries
        """
        data = self._make_request('tag.gettoptags', {'limit': limit})
        
        if not data or 'error' in data:
            return []
        
        tags = []
        for tag in data.get('toptags', {}).get('tag', []):
            tags.append({
                'name': tag.get('name'),
                'count': int(tag.get('count', 0)),
                'reach': int(tag.get('reach', 0))
            })
        
        return tags
    
    def get_genre_artists(self, genre: str, page: int = 1, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get artists for a specific genre with pagination.
        
        Args:
            genre: Genre/tag name
            page: Page number for pagination
            limit: Number of artists per page
            
        Returns:
            List of artist dictionaries
        """
        data = self._make_request('tag.gettopartists', {
            'tag': genre,
            'page': page,
            'limit': limit
        })
        
        if not data or 'error' in data:
            return []
        
        return self.get_top_artists_by_tag(genre, limit)
    
    def discover_new_genres(self, known_genres: List[str], limit: int = 20) -> List[str]:
        """
        Discover new genres based on known preferences.
        
        Args:
            known_genres: List of genres the user already likes
            limit: Maximum number of new genres to suggest
            
        Returns:
            List of recommended genre names
        """
        all_tags = self.get_top_tags(500)  # Get a large set of tags
        
        if not all_tags:
            return []
        
        # Filter out known genres and get related ones
        known_set = set(g.lower() for g in known_genres)
        new_genres = []
        
        for tag in all_tags:
            tag_name = tag['name'].lower()
            
            # Skip if already known
            if tag_name in known_set:
                continue
            
            # Look for related genres (simple heuristic)
            is_related = False
            for known in known_genres:
                if any(word in tag_name for word in known.lower().split()) or \
                   any(word in known.lower() for word in tag_name.split()):
                    is_related = True
                    break
            
            if is_related:
                new_genres.append(tag['name'])
                
                if len(new_genres) >= limit:
                    break
        
        return new_genres
    
    def _extract_image_url(self, images: List[Dict]) -> str:
        """Extract the best image URL from Last.fm image list."""
        if not images:
            return ""
        
        # Prefer large, then medium, then small images
        for size in ['extralarge', 'large', 'medium', 'small']:
            for img in images:
                if img.get('size') == size and img.get('#text'):
                    return img['#text']
        
        # Return first available image
        for img in images:
            if img.get('#text'):
                return img['#text']
        
        return ""
    
    def get_artist_recommendations(self, spotify_artists: List[Dict], limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get artist recommendations based on user's Spotify artists.
        
        Args:
            spotify_artists: List of Spotify artist objects
            limit: Maximum number of recommendations
            
        Returns:
            List of recommended artists with metadata
        """
        recommendations = []
        processed_artists = set()
        
        # Get similar artists for top artists
        for artist in spotify_artists[:10]:  # Process top 10 to avoid rate limits
            artist_name = artist.get('name', '')
            
            if artist_name in processed_artists:
                continue
            
            processed_artists.add(artist_name)
            
            similar = self.get_similar_artists(artist_name, 10)
            
            for similar_artist in similar:
                rec_name = similar_artist.get('name', '')
                
                # Skip if already in user's artists
                if any(rec_name.lower() == ua.get('name', '').lower() for ua in spotify_artists):
                    continue
                
                # Skip if already recommended
                if any(rec_name.lower() == r.get('name', '').lower() for r in recommendations):
                    continue
                
                recommendations.append({
                    'name': rec_name,
                    'source_artist': artist_name,
                    'match_score': similar_artist.get('match', 0),
                    'lastfm_url': similar_artist.get('url', ''),
                    'lastfm_image': similar_artist.get('image', ''),
                    'mbid': similar_artist.get('mbid', ''),
                    'listeners': 0,  # Will be filled if we fetch full info
                    'playcount': 0
                })
                
                if len(recommendations) >= limit:
                    break
            
            if len(recommendations) >= limit:
                break
        
        # Sort by match score
        recommendations.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        
        return recommendations[:limit]

# Global Last.fm client instance
lastfm_client = LastFmClient()

def main():
    """Test function for Last.fm integration."""
    print("Testing Last.fm Integration")
    print("=" * 40)
    
    if not lastfm_client.api_key:
        print("No Last.fm API key found. Please configure it in credentials.")
        return
    
    # Test artist info
    print("\nTesting artist info...")
    artist_info = lastfm_client.get_artist_info("Radiohead")
    if not artist_info.get('error'):
        print(f"Artist: {artist_info['name']}")
        print(f"Listeners: {artist_info['listeners']:,}")
        print(f"Play count: {artist_info['playcount']:,}")
        print(f"Top tags: {', '.join(artist_info['tags'][:5])}")
    else:
        print(f"Error: {artist_info['error']}")
    
    # Test similar artists
    print("\nTesting similar artists...")
    similar = lastfm_client.get_similar_artists("Radiohead", 5)
    if similar:
        print("Similar artists:")
        for artist in similar[:5]:
            print(f"  - {artist['name']} (match: {artist['match']:.2f})")
    else:
        print("No similar artists found")
    
    # Test top tags
    print("\nTesting top tags...")
    tags = lastfm_client.get_top_tags(10)
    if tags:
        print("Top tags:")
        for tag in tags[:10]:
            print(f"  - {tag['name']} (count: {tag['count']:,})")
    else:
        print("No tags found")

if __name__ == "__main__":
    main()