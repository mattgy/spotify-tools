#!/usr/bin/env python3
"""
AI-assisted track matching for difficult-to-find songs.

This module provides AI-powered track matching using various LLM services
to help identify songs that regular search can't find.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple
import requests
import time

from credentials_manager import get_ai_credentials
from cache_utils import save_to_cache, load_from_cache

logger = logging.getLogger(__name__)

# Cache AI responses for 7 days
AI_CACHE_EXPIRATION = 7 * 24 * 60 * 60

class AITrackMatcher:
    """AI-assisted track matching using various LLM services."""
    
    def __init__(self):
        """Initialize AI matcher and check available services."""
        self.available_services = self._check_available_services()
        
    def _check_available_services(self) -> Dict[str, str]:
        """Check which AI services have configured API keys."""
        ai_creds = get_ai_credentials()
        if not ai_creds:
            return {}
        return ai_creds
    
    def get_available_services(self) -> List[str]:
        """Get list of available AI services."""
        return list(self.available_services.keys())
    
    def match_track(self, artist: str, title: str, album: Optional[str] = None, 
                   service: Optional[str] = None) -> Optional[Dict]:
        """
        Use AI to help identify a track.
        
        Args:
            artist: Artist name from the playlist
            title: Track title from the playlist
            album: Album name if available
            service: Specific AI service to use, or None to use first available
            
        Returns:
            Dict with corrected track info or None if no match found
        """
        if not self.available_services:
            return None
            
        # Select service
        if service and service in self.available_services:
            use_service = service
        else:
            use_service = list(self.available_services.keys())[0]
            
        # Create cache key
        cache_key = f"ai_match_{use_service}_{artist}_{title}_{album or 'none'}".replace(" ", "_").lower()
        cache_key = re.sub(r'[^\w_-]', '', cache_key)[:100]  # Sanitize and limit length
        
        # Check cache
        cached = load_from_cache(cache_key, AI_CACHE_EXPIRATION)
        if cached:
            logger.debug(f"Using cached AI response for {artist} - {title}")
            return cached
            
        # Call appropriate AI service
        result = None
        if use_service == 'gemini':
            result = self._query_gemini(artist, title, album)
        elif use_service == 'openai':
            result = self._query_openai(artist, title, album)
        elif use_service == 'anthropic':
            result = self._query_anthropic(artist, title, album)
        elif use_service == 'perplexity':
            result = self._query_perplexity(artist, title, album)
            
        # Cache result
        if result:
            save_to_cache(result, cache_key)
            
        return result
    
    def _create_prompt(self, artist: str, title: str, album: Optional[str] = None) -> str:
        """Create a prompt for the AI to identify the track."""
        prompt = f"""I'm trying to find a song on Spotify but the metadata might be incorrect or formatted differently.

Given information:
- Artist: {artist}
- Title: {title}"""
        
        if album:
            prompt += f"\n- Album: {album}"
            
        prompt += """

Please help identify the correct track information. Consider:
1. The artist and title might be swapped
2. There might be typos or alternative spellings
3. It might be a cover version by a different artist
4. The title might include or exclude featuring artists
5. It might be known by an alternative title

Please respond with ONLY a JSON object in this exact format:
{
  "artist": "correct artist name",
  "title": "correct song title",
  "album": "album name if known",
  "confidence": 0.0 to 1.0,
  "notes": "brief explanation of corrections"
}

If you cannot identify the track with reasonable confidence, return:
{
  "artist": null,
  "title": null,
  "album": null,
  "confidence": 0.0,
  "notes": "explanation"
}"""
        
        return prompt
    
    def _parse_ai_response(self, response_text: str) -> Optional[Dict]:
        """Parse AI response and extract track information."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if not json_match:
                return None
                
            result = json.loads(json_match.group())
            
            # Validate response
            if not result.get('artist') or not result.get('title'):
                return None
                
            # Ensure confidence is a float
            if 'confidence' in result:
                result['confidence'] = float(result['confidence'])
            else:
                result['confidence'] = 0.5
                
            return result
            
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return None
    
    def _query_gemini(self, artist: str, title: str, album: Optional[str] = None) -> Optional[Dict]:
        """Query Google Gemini for track identification."""
        api_key = self.available_services.get('gemini')
        if not api_key:
            return None
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}"
        
        prompt = self._create_prompt(artist, title, album)
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 512
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'candidates' in data and data['candidates']:
                text = data['candidates'][0]['content']['parts'][0]['text']
                return self._parse_ai_response(text)
                
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            
        return None
    
    def _query_openai(self, artist: str, title: str, album: Optional[str] = None) -> Optional[Dict]:
        """Query OpenAI for track identification."""
        api_key = self.available_services.get('openai')
        if not api_key:
            return None
            
        url = "https://api.openai.com/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = self._create_prompt(artist, title, album)
        
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a music expert helping to identify songs for Spotify search."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 1024
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'choices' in data and data['choices']:
                text = data['choices'][0]['message']['content']
                return self._parse_ai_response(text)
                
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            
        return None
    
    def _query_anthropic(self, artist: str, title: str, album: Optional[str] = None) -> Optional[Dict]:
        """Query Anthropic Claude for track identification."""
        api_key = self.available_services.get('anthropic')
        if not api_key:
            return None
            
        url = "https://api.anthropic.com/v1/messages"
        
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        prompt = self._create_prompt(artist, title, album)

        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            if 'content' in data and data['content']:
                text = data['content'][0]['text']
                return self._parse_ai_response(text)

        except requests.exceptions.HTTPError as e:
            # Log the actual API response for debugging
            try:
                error_detail = response.json()
                logger.error(f"Anthropic API error: {e}\nResponse: {error_detail}")
            except:
                logger.error(f"Anthropic API error: {e}\nStatus: {response.status_code}")
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")

        return None
    
    def _query_perplexity(self, artist: str, title: str, album: Optional[str] = None) -> Optional[Dict]:
        """Query Perplexity for track identification."""
        api_key = self.available_services.get('perplexity')
        if not api_key:
            return None
            
        url = "https://api.perplexity.ai/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = self._create_prompt(artist, title, album)
        
        payload = {
            "model": "pplx-70b-online",
            "messages": [
                {"role": "system", "content": "You are a music expert helping to identify songs for Spotify search."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 512
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'choices' in data and data['choices']:
                text = data['choices'][0]['message']['content']
                return self._parse_ai_response(text)
                
        except Exception as e:
            logger.error(f"Perplexity API error: {e}")
            
        return None


def ai_assisted_search(sp, artist: str, title: str, album: Optional[str] = None,
                      min_confidence: float = 0.7) -> Optional[Dict]:
    """
    Try AI-assisted search when regular search fails.

    Args:
        sp: Spotify client
        artist: Artist name
        title: Track title
        album: Album name if available
        min_confidence: Minimum AI confidence to attempt search

    Returns:
        Spotify track match or None
    """
    from spotify_playlist_converter import search_track_on_spotify
    from preferences_manager import get_preference

    # Initialize AI matcher
    ai_matcher = AITrackMatcher()

    if not ai_matcher.get_available_services():
        return None

    # Get preferred AI service from user preferences
    preferred_service = get_preference("ai.ai_service", "gemini")

    # Check if preferred service is available
    available_services = ai_matcher.get_available_services()
    if preferred_service not in available_services:
        logger.warning(f"Preferred AI service '{preferred_service}' not available (no API key configured)")
        if available_services:
            preferred_service = available_services[0]
            logger.info(f"Falling back to first available service: {preferred_service}")
        else:
            logger.error("No AI services available - check credentials_manager.py for API keys")
            return None

    logger.info(f"Attempting AI-assisted match for: {artist} - {title}")
    logger.info(f"Using AI service: {preferred_service}")

    # Get AI suggestion with preferred service
    ai_result = ai_matcher.match_track(artist, title, album, service=preferred_service)
    
    if not ai_result or ai_result.get('confidence', 0) < min_confidence:
        return None
        
    logger.info(f"AI suggestion: {ai_result['artist']} - {ai_result['title']} (confidence: {ai_result['confidence']:.2f})")
    
    # Try searching with AI-corrected information
    match = search_track_on_spotify(
        sp, 
        ai_result['artist'], 
        ai_result['title'], 
        ai_result.get('album')
    )
    
    if match:
        # Add AI info to the match
        match['ai_assisted'] = True
        match['ai_confidence'] = ai_result['confidence']
        match['ai_notes'] = ai_result.get('notes', '')
        
    return match