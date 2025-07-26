#!/usr/bin/env python3
"""
MusicBrainz integration for enhanced artist metadata.
"""

import musicbrainzngs
import time
import sys
import os
from typing import Dict, List, Optional, Any

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from cache_utils import save_to_cache, load_from_cache
from config import get_cache_expiration, get_api_delay

# Configure MusicBrainz
musicbrainzngs.set_useragent("SpotifyTools", "1.0", "https://github.com/user/spotify-tools")

class MusicBrainzClient:
    """Client for MusicBrainz API integration."""
    
    def __init__(self):
        self.cache_expiration = get_cache_expiration()
        self.api_delay = get_api_delay()
    
    def search_artist(self, artist_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for artist information in MusicBrainz.
        
        Args:
            artist_name: Name of the artist to search for
            limit: Maximum number of results to return
            
        Returns:
            List of artist information dictionaries
        """
        cache_key = f"mb_artist_search_{artist_name.lower().replace(' ', '_')}"
        cached_result = load_from_cache(cache_key, self.cache_expiration)
        
        if cached_result is not None:
            return cached_result
        
        try:
            # Add delay to respect rate limits
            time.sleep(self.api_delay)
            
            result = musicbrainzngs.search_artists(artist=artist_name, limit=limit)
            artists = []
            
            for artist in result.get('artist-list', []):
                artist_info = {
                    'mbid': artist.get('id'),
                    'name': artist.get('name'),
                    'sort_name': artist.get('sort-name'),
                    'type': artist.get('type'),
                    'gender': artist.get('gender'),
                    'country': artist.get('area', {}).get('name') if 'area' in artist else None,
                    'begin_date': artist.get('life-span', {}).get('begin'),
                    'end_date': artist.get('life-span', {}).get('end'),
                    'aliases': [alias.get('name') for alias in artist.get('alias-list', [])],
                    'tags': [tag.get('name') for tag in artist.get('tag-list', [])],
                    'score': artist.get('ext:score', 0)
                }
                artists.append(artist_info)
            
            # Sort by score (relevance)
            artists.sort(key=lambda x: x.get('score', 0), reverse=True)
            
            save_to_cache(artists, cache_key)
            return artists
            
        except Exception as e:
            print(f"Error searching MusicBrainz for {artist_name}: {e}")
            return []
    
    def get_artist_details(self, mbid: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed artist information by MusicBrainz ID.
        
        Args:
            mbid: MusicBrainz ID for the artist
            
        Returns:
            Detailed artist information dictionary
        """
        cache_key = f"mb_artist_details_{mbid}"
        cached_result = load_from_cache(cache_key, self.cache_expiration)
        
        if cached_result is not None:
            return cached_result
        
        try:
            time.sleep(self.api_delay)
            
            result = musicbrainzngs.get_artist_by_id(
                mbid, 
                includes=['aliases', 'tags', 'ratings', 'url-rels', 'artist-rels']
            )
            
            artist = result.get('artist', {})
            
            artist_details = {
                'mbid': artist.get('id'),
                'name': artist.get('name'),
                'sort_name': artist.get('sort-name'),
                'type': artist.get('type'),
                'gender': artist.get('gender'),
                'country': artist.get('area', {}).get('name') if 'area' in artist else None,
                'begin_date': artist.get('life-span', {}).get('begin'),
                'end_date': artist.get('life-span', {}).get('end'),
                'aliases': [alias.get('name') for alias in artist.get('alias-list', [])],
                'tags': [tag.get('name') for tag in artist.get('tag-list', [])],
                'urls': {},
                'related_artists': []
            }
            
            # Extract URLs
            for relation in artist.get('url-relation-list', []):
                url_type = relation.get('type')
                url = relation.get('target')
                if url_type and url:
                    artist_details['urls'][url_type] = url
            
            # Extract related artists
            for relation in artist.get('artist-relation-list', []):
                if relation.get('type') in ['member of band', 'collaboration', 'is person']:
                    related_artist = {
                        'mbid': relation.get('artist', {}).get('id'),
                        'name': relation.get('artist', {}).get('name'),
                        'relationship': relation.get('type')
                    }
                    artist_details['related_artists'].append(related_artist)
            
            save_to_cache(artist_details, cache_key)
            return artist_details
            
        except Exception as e:
            print(f"Error getting MusicBrainz details for {mbid}: {e}")
            return None
    
    def get_similar_artists(self, artist_name: str) -> List[Dict[str, Any]]:
        """
        Find similar artists using MusicBrainz relationships and tags.
        
        Args:
            artist_name: Name of the artist to find similar artists for
            
        Returns:
            List of similar artist information
        """
        # First search for the artist
        search_results = self.search_artist(artist_name, limit=1)
        if not search_results:
            return []
        
        artist_mbid = search_results[0]['mbid']
        artist_details = self.get_artist_details(artist_mbid)
        
        if not artist_details:
            return []
        
        similar_artists = []
        
        # Add related artists
        for related in artist_details.get('related_artists', []):
            similar_artists.append({
                'name': related['name'],
                'mbid': related['mbid'],
                'source': f"Related: {related['relationship']}",
                'confidence': 0.8
            })
        
        # Find artists with similar tags
        artist_tags = set(artist_details.get('tags', []))
        if artist_tags:
            try:
                # Search for artists with similar tags (simplified approach)
                for tag in list(artist_tags)[:3]:  # Use top 3 tags
                    time.sleep(self.api_delay)
                    tag_results = musicbrainzngs.search_artists(tag=tag, limit=5)
                    
                    for tag_artist in tag_results.get('artist-list', []):
                        if tag_artist.get('name') != artist_name:
                            similar_artists.append({
                                'name': tag_artist.get('name'),
                                'mbid': tag_artist.get('id'),
                                'source': f"Similar tag: {tag}",
                                'confidence': 0.6
                            })
            except Exception as e:
                print(f"Error finding tag-based similar artists: {e}")
        
        # Remove duplicates and sort by confidence
        seen_names = set()
        unique_similar = []
        for artist in similar_artists:
            if artist['name'] not in seen_names:
                seen_names.add(artist['name'])
                unique_similar.append(artist)
        
        unique_similar.sort(key=lambda x: x['confidence'], reverse=True)
        return unique_similar[:20]  # Return top 20
    
    def enrich_artist_data(self, spotify_artist: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich Spotify artist data with MusicBrainz information.
        
        Args:
            spotify_artist: Spotify artist data
            
        Returns:
            Enriched artist data combining Spotify and MusicBrainz info
        """
        artist_name = spotify_artist.get('name', '')
        mb_results = self.search_artist(artist_name, limit=1)
        
        enriched = spotify_artist.copy()
        enriched['musicbrainz'] = {}
        
        if mb_results:
            mb_artist = mb_results[0]
            mb_details = self.get_artist_details(mb_artist['mbid'])
            
            if mb_details:
                enriched['musicbrainz'] = {
                    'mbid': mb_details['mbid'],
                    'country': mb_details.get('country'),
                    'begin_date': mb_details.get('begin_date'),
                    'end_date': mb_details.get('end_date'),
                    'type': mb_details.get('type'),
                    'aliases': mb_details.get('aliases', []),
                    'tags': mb_details.get('tags', []),
                    'urls': mb_details.get('urls', {}),
                    'related_artists': mb_details.get('related_artists', [])
                }
        
        return enriched

# Global MusicBrainz client instance
mb_client = MusicBrainzClient()