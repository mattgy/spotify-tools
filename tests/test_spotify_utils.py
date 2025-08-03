#!/usr/bin/env python3
"""
Unit tests for spotify_utils.py - focusing on new batch functions and optimizations.

Tests the batch API functions, caching mechanisms, and optimization utilities
added for improved API efficiency.

Author: Matt Y
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import tempfile
import json

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, script_dir)

# Import the module under test
import spotify_utils as su

class TestBatchFunctions(unittest.TestCase):
    """Test batch API functions for efficiency."""
    
    def setUp(self):
        """Set up mock Spotify client for testing."""
        self.mock_sp = Mock()
        
    def test_batch_get_artist_details_basic(self):
        """Test basic batch artist details retrieval."""
        # Mock the sp.artists() response
        self.mock_sp.artists.return_value = {
            'artists': [
                {
                    'id': 'artist1',
                    'name': 'Test Artist 1',
                    'followers': {'total': 1000},
                    'popularity': 75,
                    'genres': ['rock', 'indie']
                },
                {
                    'id': 'artist2', 
                    'name': 'Test Artist 2',
                    'followers': {'total': 2000},
                    'popularity': 80,
                    'genres': ['pop', 'electronic']
                }
            ]
        }
        
        artist_ids = ['artist1', 'artist2']
        
        with patch('cache_utils.load_from_cache', return_value=None):
            with patch('cache_utils.save_to_cache'):
                result = su.batch_get_artist_details(
                    self.mock_sp, 
                    artist_ids, 
                    show_progress=False
                )
        
        self.assertEqual(len(result), 2)
        self.assertIn('artist1', result)
        self.assertIn('artist2', result)
        self.assertEqual(result['artist1']['name'], 'Test Artist 1')
        self.assertEqual(result['artist2']['followers']['total'], 2000)
        
        # Verify sp.artists was called with correct batch
        self.mock_sp.artists.assert_called_once_with(['artist1', 'artist2'])
    
    def test_batch_get_artist_details_with_cache(self):
        """Test that cached artist details are returned without API calls."""
        artist_ids = ['artist1', 'artist2']
        
        # Mock cache to return data for artist1
        def mock_load_cache(key, expiration):
            if 'artist_details_artist1' in key:
                return {'id': 'artist1', 'name': 'Cached Artist 1'}
            return None
        
        # Mock API response for uncached artist2
        self.mock_sp.artists.return_value = {
            'artists': [
                {
                    'id': 'artist2',
                    'name': 'Fresh Artist 2',
                    'followers': {'total': 1500}
                }
            ]
        }
        
        with patch('cache_utils.load_from_cache', side_effect=mock_load_cache):
            with patch('cache_utils.save_to_cache'):
                result = su.batch_get_artist_details(
                    self.mock_sp,
                    artist_ids,
                    show_progress=False
                )
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result['artist1']['name'], 'Cached Artist 1')
        self.assertEqual(result['artist2']['name'], 'Fresh Artist 2')
        
        # Verify API was only called for uncached artist
        self.mock_sp.artists.assert_called_once_with(['artist2'])
    
    def test_batch_search_tracks_basic(self):
        """Test basic batch track searching."""
        queries = ['artist:"Test Artist" track:"Song 1"', '"Test Artist" "Song 2"']
        
        # Mock search responses
        def mock_search(q, type, limit):
            if 'Song 1' in q:
                return {
                    'tracks': {
                        'items': [
                            {
                                'id': 'track1',
                                'name': 'Song 1',
                                'artists': [{'name': 'Test Artist'}],
                                'album': {'name': 'Test Album'}
                            }
                        ]
                    }
                }
            elif 'Song 2' in q:
                return {
                    'tracks': {
                        'items': [
                            {
                                'id': 'track2',
                                'name': 'Song 2', 
                                'artists': [{'name': 'Test Artist'}],
                                'album': {'name': 'Test Album 2'}
                            }
                        ]
                    }
                }
            return {'tracks': {'items': []}}
        
        self.mock_sp.search.side_effect = mock_search
        
        with patch('cache_utils.load_from_cache', return_value=None):
            with patch('cache_utils.save_to_cache'):
                result = su.batch_search_tracks(
                    self.mock_sp,
                    queries,
                    show_progress=False
                )
        
        self.assertEqual(len(result), 2)
        self.assertIn(queries[0], result)
        self.assertIn(queries[1], result)
        self.assertEqual(len(result[queries[0]]['tracks']['items']), 1)
        self.assertEqual(result[queries[0]]['tracks']['items'][0]['name'], 'Song 1')
        
        # Verify both searches were called
        self.assertEqual(self.mock_sp.search.call_count, 2)
    
    def test_get_playlist_artist_frequency_basic(self):
        """Test playlist artist frequency analysis."""
        playlist_ids = ['playlist1', 'playlist2']
        
        # Mock fetch_playlist_tracks responses
        def mock_fetch_tracks(sp, playlist_id, **kwargs):
            if playlist_id == 'playlist1':
                return [
                    {'track': {'artists': [{'id': 'artist1', 'name': 'Artist 1'}]}},
                    {'track': {'artists': [{'id': 'artist2', 'name': 'Artist 2'}]}}
                ]
            elif playlist_id == 'playlist2':
                return [
                    {'track': {'artists': [{'id': 'artist1', 'name': 'Artist 1'}]}},  # Same artist
                    {'track': {'artists': [{'id': 'artist3', 'name': 'Artist 3'}]}}
                ]
            return []
        
        with patch('cache_utils.load_from_cache', return_value=None):
            with patch('cache_utils.save_to_cache'):
                with patch('spotify_utils.fetch_playlist_tracks', side_effect=mock_fetch_tracks):
                    result = su.get_playlist_artist_frequency(
                        self.mock_sp,
                        playlist_ids,
                        show_progress=False
                    )
        
        # Artist 1 should appear in both playlists (count=2)
        # Artist 2 and 3 should appear in one playlist each (count=1)
        self.assertEqual(result['artist1']['count'], 2)
        self.assertEqual(len(result['artist1']['playlists']), 2)
        self.assertEqual(result['artist2']['count'], 1)
        self.assertEqual(result['artist3']['count'], 1)
    
    def test_optimized_track_search_strategies_basic(self):
        """Test optimized track search with multiple strategies."""
        artist = "Test Artist"
        title = "Test Song"
        album = "Test Album"
        
        # Mock batch_search_tracks to return results
        mock_search_results = {
            'artist:"Test Artist" album:"Test Album" track:"Test Song"': {
                'tracks': {
                    'items': [
                        {
                            'id': 'track1',
                            'name': 'Test Song',
                            'artists': [{'name': 'Test Artist'}],
                            'album': {'name': 'Test Album'},
                            'uri': 'spotify:track:track1'
                        }
                    ]
                }
            }
        }
        
        with patch('cache_utils.load_from_cache', return_value=None):
            with patch('cache_utils.save_to_cache'):
                with patch('spotify_utils.batch_search_tracks', return_value=mock_search_results):
                    result = su.optimized_track_search_strategies(
                        self.mock_sp,
                        artist,
                        title,
                        album
                    )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['id'], 'track1')
        self.assertEqual(result['name'], 'Test Song')
        self.assertEqual(result['artists'], ['Test Artist'])
        self.assertGreater(result['score'], 0)
    
    def test_optimized_track_search_strategies_cached(self):
        """Test that cached results are returned for optimized search."""
        artist = "Cached Artist"
        title = "Cached Song"
        
        cached_result = {
            'id': 'cached_track',
            'name': 'Cached Song',
            'artists': ['Cached Artist'],
            'album': 'Cached Album',
            'uri': 'spotify:track:cached_track',
            'score': 95
        }
        
        with patch('cache_utils.load_from_cache', return_value=cached_result):
            result = su.optimized_track_search_strategies(
                self.mock_sp,
                artist,
                title
            )
        
        self.assertEqual(result, cached_result)
        self.assertEqual(result['id'], 'cached_track')
    
    def test_batch_functions_handle_empty_input(self):
        """Test that batch functions handle empty input gracefully."""
        # Test batch_get_artist_details with empty list
        result = su.batch_get_artist_details(self.mock_sp, [], show_progress=False)
        self.assertEqual(result, {})
        
        # Test batch_search_tracks with empty list
        result = su.batch_search_tracks(self.mock_sp, [], show_progress=False)
        self.assertEqual(result, {})
        
        # Test get_playlist_artist_frequency with empty list
        with patch('cache_utils.load_from_cache', return_value=None):
            with patch('cache_utils.save_to_cache'):
                result = su.get_playlist_artist_frequency(self.mock_sp, [], show_progress=False)
                self.assertEqual(result, {})
    
    def test_batch_functions_handle_api_errors(self):
        """Test that batch functions handle API errors gracefully."""
        # Test batch_get_artist_details with API error
        self.mock_sp.artists.side_effect = Exception("API Error")
        
        result = su.batch_get_artist_details(
            self.mock_sp, 
            ['artist1'], 
            show_progress=False
        )
        
        # Should return empty dict when all API calls fail
        self.assertEqual(result, {})
        
        # Test batch_search_tracks with API error
        self.mock_sp.search.side_effect = Exception("Search API Error")
        
        with patch('cache_utils.load_from_cache', return_value=None):
            with patch('cache_utils.save_to_cache'):
                result = su.batch_search_tracks(
                    self.mock_sp,
                    ['test query'],
                    show_progress=False
                )
        
        # Should return dict with empty results for failed queries
        self.assertIn('test query', result)
        self.assertEqual(result['test query']['tracks']['items'], [])

class TestExistingFunctions(unittest.TestCase):
    """Test existing functions to ensure they still work after optimizations."""
    
    def setUp(self):
        """Set up mock Spotify client."""
        self.mock_sp = Mock()
    
    def test_create_spotify_client_function_exists(self):
        """Test that create_spotify_client function exists and is callable."""
        self.assertTrue(hasattr(su, 'create_spotify_client'))
        self.assertTrue(callable(su.create_spotify_client))
    
    def test_print_functions_exist(self):
        """Test that print utility functions exist."""
        print_functions = ['print_success', 'print_error', 'print_warning', 'print_info', 'print_header']
        
        for func_name in print_functions:
            self.assertTrue(hasattr(su, func_name))
            self.assertTrue(callable(getattr(su, func_name)))
    
    def test_fetch_functions_exist(self):
        """Test that centralized fetch functions exist."""
        fetch_functions = [
            'fetch_user_playlists',
            'fetch_user_saved_tracks', 
            'fetch_playlist_tracks',
            'fetch_followed_artists'
        ]
        
        for func_name in fetch_functions:
            self.assertTrue(hasattr(su, func_name))
            self.assertTrue(callable(getattr(su, func_name)))
    
    def test_safe_spotify_call_decorator(self):
        """Test that safe_spotify_call decorator exists and works."""
        self.assertTrue(hasattr(su, 'safe_spotify_call'))
        self.assertTrue(callable(su.safe_spotify_call))
        
        # Test that it can decorate a function
        @su.safe_spotify_call
        def test_function():
            return "success"
        
        result = test_function()
        self.assertEqual(result, "success")

class TestCacheIntegration(unittest.TestCase):
    """Test caching integration for batch functions."""
    
    def test_batch_functions_use_cache_keys_safely(self):
        """Test that batch functions create safe cache keys."""
        mock_sp = Mock()
        
        # Test with special characters that could cause filesystem issues
        artist_ids = ['artist:with:colons', 'artist/with/slashes', 'artist*with*stars']
        
        # Mock API to return some artists so cache save is triggered
        mock_sp.artists.return_value = {
            'artists': [
                {'id': 'artist:with:colons', 'name': 'Test Artist 1'},
                {'id': 'artist/with/slashes', 'name': 'Test Artist 2'},
                {'id': 'artist*with*stars', 'name': 'Test Artist 3'}
            ]
        }
        
        with patch('cache_utils.load_from_cache', return_value=None) as mock_load:
            with patch('cache_utils.save_to_cache') as mock_save:
                su.batch_get_artist_details(mock_sp, artist_ids, show_progress=False)
                
                # Verify cache functions were called (meaning keys were created successfully)
                self.assertTrue(mock_load.called)
                self.assertTrue(mock_save.called)
    
    def test_search_queries_hashed_safely(self):
        """Test that complex search queries are hashed for cache keys."""
        mock_sp = Mock()
        mock_sp.search.return_value = {'tracks': {'items': []}}
        
        # Test with very long and complex query
        complex_query = 'artist:"Very Long Artist Name With Special Characters!@#$%^&*()_+" track:"Very Long Song Title With More Special Characters" album:"Album With Émojis 🎵 and Ünicode"'
        
        with patch('cache_utils.load_from_cache', return_value=None) as mock_load:
            with patch('cache_utils.save_to_cache') as mock_save:
                su.batch_search_tracks(mock_sp, [complex_query], show_progress=False)
                
                # Verify cache operations completed without errors
                self.assertTrue(mock_load.called)
                self.assertTrue(mock_save.called)

if __name__ == '__main__':
    # Set up test mode to avoid external dependencies
    os.environ['SPOTIFY_TOOLS_TEST_MODE'] = '1'
    
    # Run the tests
    unittest.main(verbosity=2)