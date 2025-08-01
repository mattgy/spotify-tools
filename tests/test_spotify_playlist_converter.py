#!/usr/bin/env python3
"""
Unit tests for spotify_playlist_converter.py

Tests the core functionality of the playlist conversion system including:
- File path parsing and track info extraction
- Track searching and matching algorithms  
- Playlist creation and management
- Cache management and decision storage
- Error handling and edge cases

Author: Matt Y
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
import sys
import os
import tempfile
import json

# Add the script directory to the Python path
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, script_dir)

# Import the module under test
import spotify_playlist_converter as spc

class TestTrackInfoExtraction(unittest.TestCase):
    """Test track information extraction from various file paths."""
    
    def test_extract_track_info_basic_dash_format(self):
        """Test basic 'Artist - Title.mp3' format."""
        path = "Artist Name - Song Title.mp3"
        result = spc.extract_track_info_from_path(path)
        
        self.assertEqual(result['artist'], 'Artist Name')
        self.assertEqual(result['title'], 'Song Title')
        self.assertEqual(result['path'], path)
    
    def test_extract_track_info_with_track_numbers(self):
        """Test extraction with track numbers."""
        path = "01 - Artist - Title.mp3"
        result = spc.extract_track_info_from_path(path)
        
        self.assertEqual(result['artist'], 'Artist')
        self.assertEqual(result['title'], 'Title')
    
    def test_extract_track_info_windows_path(self):
        """Test Windows path parsing like 'M:\\Artist\\Album\\Artist-03-Title.mp3'."""
        path = r"M:\Turntables Electronics\Joshua Idehen\Routes\Joshua Idehen-03-Northern Line.mp3"
        result = spc.extract_track_info_from_path(path)
        
        self.assertEqual(result['artist'], 'Joshua Idehen')
        self.assertEqual(result['title'], 'Northern Line')
        self.assertEqual(result['album'], 'Routes')
    
    def test_extract_track_info_underscore_format(self):
        """Test underscore-separated format."""
        path = "various_artists_-_artist_name__song_title.wav"
        result = spc.extract_track_info_from_path(path)
        
        self.assertEqual(result['artist'], 'artist name')
        self.assertEqual(result['title'], 'song title')
    
    def test_extract_track_info_non_english_characters(self):
        """Test non-English characters in filenames."""
        path = "刘东明 - 04 - 少年时光.mp3"
        result = spc.extract_track_info_from_path(path)
        
        self.assertEqual(result['artist'], '刘东明')
        self.assertEqual(result['title'], '少年时光')
    
    def test_extract_track_info_complex_path_structure(self):
        """Test complex directory structure extraction."""
        path = r"M:\.NEW\Ada\Meine Zarten Pfoten\04 - Ada - The Jazz Singer (Re-Imagined By Ada).mp3"
        result = spc.extract_track_info_from_path(path)
        
        self.assertEqual(result['artist'], 'Ada')
        self.assertEqual(result['title'], 'The Jazz Singer (Re-Imagined By Ada)')
        self.assertEqual(result['album'], 'Meine Zarten Pfoten')

class TestTrackSearching(unittest.TestCase):
    """Test track searching and matching functionality."""
    
    def setUp(self):
        """Set up mock Spotify client for testing."""
        self.mock_sp = Mock()
        self.mock_sp.search.return_value = {
            'tracks': {
                'items': [
                    {
                        'id': 'track123',
                        'name': 'Test Song',
                        'artists': [{'name': 'Test Artist', 'id': 'artist123'}],
                        'album': {'name': 'Test Album'},
                        'uri': 'spotify:track:track123',
                        'popularity': 75
                    }
                ]
            }
        }
    
    @patch('spotify_playlist_converter.load_from_cache')
    @patch('spotify_playlist_converter.save_to_cache')
    def test_search_track_basic(self, mock_save_cache, mock_load_cache):
        """Test basic track searching functionality."""
        mock_load_cache.return_value = None  # No cache hit
        
        result = spc.search_track_on_spotify(self.mock_sp, "Test Artist", "Test Song")
        
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Test Song')
        self.assertEqual(result['artists'], ['Test Artist'])
        
        # Verify search was called
        self.assertTrue(self.mock_sp.search.called)
        # Verify result was cached
        self.assertTrue(mock_save_cache.called)
    
    @patch('spotify_playlist_converter.load_from_cache')
    def test_search_track_cache_hit(self, mock_load_cache):
        """Test that cached results are returned without API call."""
        cached_result = {
            'id': 'cached123',
            'name': 'Cached Song',
            'artists': ['Cached Artist']
        }
        mock_load_cache.return_value = cached_result
        
        result = spc.search_track_on_spotify(self.mock_sp, "Test Artist", "Test Song")
        
        self.assertEqual(result, cached_result)
        # Verify no search API call was made
        self.assertFalse(self.mock_sp.search.called)
    
    def test_search_track_no_results(self):
        """Test behavior when no tracks are found."""
        self.mock_sp.search.return_value = {'tracks': {'items': []}}
        
        result = spc.search_track_on_spotify(self.mock_sp, "Unknown Artist", "Unknown Song")
        
        self.assertIsNone(result)
    
    def test_search_track_with_parenthetical_fallback(self):
        """Test fallback search for titles with parenthetical content."""
        # First search fails, second search (simplified title) succeeds
        self.mock_sp.search.side_effect = [
            {'tracks': {'items': []}},  # First search fails
            {
                'tracks': {
                    'items': [
                        {
                            'id': 'track123',
                            'name': 'Test Song',
                            'artists': [{'name': 'Test Artist', 'id': 'artist123'}],
                            'album': {'name': 'Test Album'},
                            'uri': 'spotify:track:track123',
                            'popularity': 75
                        }
                    ]
                }
            }  # Second search succeeds
        ]
        
        with patch('spotify_playlist_converter.load_from_cache', return_value=None):
            with patch('spotify_playlist_converter.save_to_cache'):
                result = spc.search_track_on_spotify(self.mock_sp, "Test Artist", "Test Song (Remix)")
        
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Test Song')
        # Should have made multiple search calls (exact count may vary based on fallback strategies)
        self.assertGreater(self.mock_sp.search.call_count, 1)

class TestPlaylistManagement(unittest.TestCase):
    """Test playlist creation and management functionality."""
    
    def setUp(self):
        """Set up mock Spotify client."""
        self.mock_sp = Mock()
        self.mock_sp.current_user.return_value = {'id': 'test_user'}
        self.mock_sp.user_playlist_create.return_value = {
            'id': 'new_playlist_123',
            'name': 'Test Playlist',
            'external_urls': {'spotify': 'https://open.spotify.com/playlist/new_playlist_123'}
        }
    
    @patch('spotify_playlist_converter.get_user_playlists')
    def test_create_playlist_new(self, mock_get_playlists):
        """Test creating a new playlist."""
        mock_get_playlists.return_value = []  # No existing playlists
        
        result = spc.create_or_update_spotify_playlist(
            self.mock_sp, "Test Playlist", [], "test_user"
        )
        
        self.assertIsNotNone(result)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)  # Should return (playlist_id, track_count)
        self.assertEqual(result[0], 'new_playlist_123')  # playlist_id
        self.assertEqual(result[1], 0)  # track_count
        self.assertTrue(self.mock_sp.user_playlist_create.called)
    
    @patch('spotify_playlist_converter.get_user_playlists')
    @patch('spotify_playlist_converter.check_for_duplicate_playlists')
    def test_duplicate_playlist_detection(self, mock_check_duplicates, mock_get_playlists):
        """Test detection of duplicate playlist names."""
        existing_playlists = [
            {'name': 'Test Playlist', 'id': 'existing123', 'tracks': {'total': 0}}
        ]
        mock_get_playlists.return_value = existing_playlists
        
        # Mock the duplicate check to return exact matches
        mock_check_duplicates.return_value = (existing_playlists, [], [])
        
        with patch('builtins.input', return_value='n'):  # Don't create duplicate
            with patch('spotify_playlist_converter.get_playlist_tracks', return_value=[]):
                result = spc.create_or_update_spotify_playlist(
                    self.mock_sp, "Test Playlist", [], "test_user"
                )
        
        self.assertIsNotNone(result)  # Should still return something (update existing)
        self.assertFalse(self.mock_sp.user_playlist_create.called)

class TestCacheAndDecisionManagement(unittest.TestCase):
    """Test caching and decision storage functionality."""
    
    def test_create_decision_cache_key(self):
        """Test decision cache key creation."""
        track_info = {'artist': 'Test Artist', 'title': 'Test Song'}
        match_info = {'name': 'Matched Song', 'artists': ['Matched Artist']}
        
        key = spc.create_decision_cache_key(track_info, match_info)
        
        self.assertIsInstance(key, str)
        self.assertTrue(key.startswith('user_decision_'))
    
    @patch('spotify_playlist_converter.save_to_cache')
    def test_save_user_decision(self, mock_save_cache):
        """Test saving user decisions to cache."""
        track_info = {'artist': 'Test Artist', 'title': 'Test Song'}
        match_info = {'name': 'Matched Song', 'artists': ['Matched Artist']}
        
        spc.save_user_decision(track_info, match_info, 'accept')
        
        self.assertTrue(mock_save_cache.called)
        # Verify the decision data structure
        call_args = mock_save_cache.call_args
        decision_data = call_args[0][0]  # First argument (data)
        self.assertEqual(decision_data['decision'], 'accept')
        self.assertIn('timestamp', decision_data)
    
    @patch('spotify_playlist_converter.load_from_cache')
    def test_get_cached_user_decision(self, mock_load_cache):
        """Test retrieving cached user decisions."""
        cached_decision = {
            'decision': 'accept',
            'timestamp': 1234567890
        }
        mock_load_cache.return_value = cached_decision
        
        track_info = {'artist': 'Test Artist', 'title': 'Test Song'}
        match_info = {'name': 'Matched Song', 'artists': ['Matched Artist']}
        
        result = spc.get_cached_user_decision(track_info, match_info)
        
        self.assertEqual(result, 'accept')

class TestFileFormatParsing(unittest.TestCase):
    """Test parsing of different playlist file formats."""
    
    def test_parse_m3u_basic(self):
        """Test basic M3U playlist parsing."""
        m3u_content = """#EXTM3U
#EXTINF:180,Artist Name - Song Title
/path/to/song.mp3
#EXTINF:200,Another Artist - Another Song
/path/to/another.mp3
"""
        
        with patch('builtins.open', mock_open(read_data=m3u_content)):
            tracks = spc.parse_m3u_playlist('/fake/path/playlist.m3u')
        
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]['artist'], 'Artist Name')
        self.assertEqual(tracks[0]['title'], 'Song Title')
        self.assertEqual(tracks[0]['duration'], 180)
    
    def test_parse_text_playlist(self):
        """Test parsing text playlist files."""
        text_content = """Artist 1 - Song 1
Artist 2 - Song 2
Artist 3 - Song 3
"""
        
        with patch('builtins.open', mock_open(read_data=text_content)):
            tracks = spc.parse_text_playlist_file('/fake/path/playlist.txt')
        
        self.assertEqual(len(tracks), 3)
        self.assertEqual(tracks[0]['artist'], 'Artist 1')
        self.assertEqual(tracks[0]['title'], 'Song 1')
    
    def test_is_text_playlist_file_detection(self):
        """Test detection of text playlist files."""
        valid_playlist = """Artist 1 - Song 1
Artist 2 - Song 2
Artist 3 - Song 3
"""
        
        invalid_file = """This is just some random text
that doesn't look like a playlist
at all really.
"""
        
        with patch('builtins.open', mock_open(read_data=valid_playlist)):
            self.assertTrue(spc.is_text_playlist_file('/fake/valid.txt'))
        
        # Create content that definitely won't match playlist patterns
        non_playlist = """This file contains no music metadata.
It has multiple lines but no artist-song patterns.
Just random text that should not be detected as a playlist.
"""
        with patch('builtins.open', mock_open(read_data=non_playlist)):
            self.assertFalse(spc.is_text_playlist_file('/fake/invalid.txt'))

class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases."""
    
    def setUp(self):
        """Set up mock Spotify client that can simulate errors."""
        self.mock_sp = Mock()
    
    def test_handle_api_rate_limit(self):
        """Test handling of Spotify API rate limits."""
        # Mock rate limit error
        self.mock_sp.search.side_effect = Exception("rate limit exceeded")
        
        result = spc.search_track_on_spotify(self.mock_sp, "Artist", "Song", retries=1)
        
        # Should handle gracefully and return None
        self.assertIsNone(result)
    
    def test_handle_invalid_file_path(self):
        """Test handling of invalid file paths."""
        result = spc.extract_track_info_from_path("")
        
        self.assertEqual(result['artist'], '')
        self.assertEqual(result['title'], '')
        self.assertEqual(result['path'], '')
    
    def test_handle_corrupted_cache(self):
        """Test handling of corrupted cache data."""
        with patch('spotify_playlist_converter.load_from_cache', return_value="corrupted_data"):
            result = spc.search_track_on_spotify(self.mock_sp, "Artist", "Song")
        
        # Should handle corrupted cache gracefully
        self.assertIsNotNone(result)  # Should attempt fresh search
    
    def test_handle_missing_track_info(self):
        """Test handling of missing track information."""
        result = spc.search_track_on_spotify(self.mock_sp, "", "")
        
        self.assertIsNone(result)  # Should return None for empty info

class TestStringNormalization(unittest.TestCase):
    """Test string normalization and matching utilities."""
    
    def test_normalize_string_basic(self):
        """Test basic string normalization."""
        result = spc.normalize_string("Test String!")
        
        self.assertIsInstance(result, str)
        self.assertEqual(result.lower(), result)  # Should be lowercase
    
    def test_normalize_string_unicode(self):
        """Test normalization with Unicode characters."""
        result = spc.normalize_string("测试字符串")
        
        self.assertIsInstance(result, str)
        self.assertIn('测试', result)  # Should preserve Chinese characters
    
    def test_remove_track_numbers(self):
        """Test track number removal."""
        test_cases = [
            ("01 - Song Title", "Song Title"),
            ("1. Song Title", "Song Title"),
            ("Track 05 - Title", "Title"),
            ("Song Title", "Song Title")  # No track number
        ]
        
        for input_str, expected in test_cases:
            result = spc.remove_track_numbers(input_str)
            self.assertEqual(result.strip(), expected)

if __name__ == '__main__':
    # Set up test mode to avoid external dependencies
    os.environ['SPOTIFY_TOOLS_TEST_MODE'] = '1'
    
    # Run the tests
    unittest.main(verbosity=2)