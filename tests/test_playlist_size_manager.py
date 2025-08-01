#!/usr/bin/env python3
"""
Tests for the Spotify Playlist Size Manager.

Tests the functionality for finding and managing playlists by track count.
"""

import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import json

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spotify_playlist_size_manager import PlaylistSizeManager


class TestPlaylistSizeManager(unittest.TestCase):
    """Test cases for the PlaylistSizeManager class."""
    
    def setUp(self):
        """Set up test environment."""
        self.manager = PlaylistSizeManager()
        
        # Mock Spotify client
        self.mock_sp = Mock()
        self.manager.sp = self.mock_sp
        self.manager.user_id = 'test_user'
        
        # Sample playlists for testing
        self.sample_playlists = [
            {
                'id': 'playlist1',
                'name': 'Empty Playlist',
                'owner': {'id': 'test_user'},
                'tracks': {'total': 0},
                'public': True,
                'collaborative': False,
                'description': 'An empty playlist',
                'external_urls': {'spotify': 'https://spotify.com/playlist1'}
            },
            {
                'id': 'playlist2',
                'name': 'Small Playlist',
                'owner': {'id': 'test_user'},
                'tracks': {'total': 5},
                'public': False,
                'collaborative': False,
                'description': '',
                'external_urls': {'spotify': 'https://spotify.com/playlist2'}
            },
            {
                'id': 'playlist3',
                'name': 'Medium Playlist',
                'owner': {'id': 'test_user'},
                'tracks': {'total': 25},
                'public': True,
                'collaborative': True,
                'description': 'A collaborative playlist',
                'external_urls': {'spotify': 'https://spotify.com/playlist3'}
            },
            {
                'id': 'playlist4',
                'name': 'Large Playlist',
                'owner': {'id': 'test_user'},
                'tracks': {'total': 100},
                'public': True,
                'collaborative': False,
                'description': 'A large playlist with many tracks',
                'external_urls': {'spotify': 'https://spotify.com/playlist4'}
            },
            {
                'id': 'playlist5',
                'name': 'Other User Playlist',
                'owner': {'id': 'other_user'},
                'tracks': {'total': 10},
                'public': True,
                'collaborative': False,
                'description': 'Not owned by test user',
                'external_urls': {'spotify': 'https://spotify.com/playlist5'}
            }
        ]
    
    @patch('spotify_playlist_size_manager.create_spotify_client')
    def test_setup_success(self, mock_setup_client):
        """Test successful setup."""
        # Create a fresh manager instance
        manager = PlaylistSizeManager()
        
        # Mock the Spotify client
        mock_client = Mock()
        mock_setup_client.return_value = mock_client
        
        # Mock user info
        mock_client.current_user.return_value = {
            'id': 'test_user',
            'display_name': 'Test User'
        }
        
        # Test setup
        result = manager.setup()
        
        self.assertTrue(result)
        self.assertEqual(manager.user_id, 'test_user')
        mock_setup_client.assert_called_once()
        mock_client.current_user.assert_called_once()
    
    @patch('spotify_playlist_size_manager.create_spotify_client')
    def test_setup_failure(self, mock_setup_client):
        """Test setup failure."""
        # Create a fresh manager instance
        manager = PlaylistSizeManager()
        
        # Mock the Spotify client
        mock_client = Mock()
        mock_setup_client.return_value = mock_client
        
        # Mock user info failure
        mock_client.current_user.side_effect = Exception("API Error")
        
        # Test setup
        result = manager.setup()
        
        self.assertFalse(result)
        self.assertIsNone(manager.user_id)
    
    @patch('spotify_playlist_size_manager.fetch_user_playlists')
    @patch('spotify_playlist_size_manager.load_from_cache')
    @patch('spotify_playlist_size_manager.save_to_cache')
    def test_get_playlists_by_size(self, mock_save_cache, mock_load_cache, mock_fetch):
        """Test getting playlists by size."""
        # Setup
        mock_load_cache.return_value = None  # No cache
        mock_fetch.return_value = self.sample_playlists
        
        # Test with max_tracks = 10
        result = self.manager.get_playlists_by_size(10)
        
        # Verify results (should include playlists with 0, 5, and 10 tracks from test_user)
        self.assertEqual(len(result), 2)  # Only user's playlists
        self.assertEqual(result[0]['name'], 'Empty Playlist')
        self.assertEqual(result[0]['track_count'], 0)
        self.assertEqual(result[1]['name'], 'Small Playlist')
        self.assertEqual(result[1]['track_count'], 5)
        
        # Verify cache was saved
        mock_save_cache.assert_called_once()
        
    @patch('spotify_playlist_size_manager.fetch_user_playlists')
    @patch('spotify_playlist_size_manager.load_from_cache')
    def test_get_playlists_from_cache(self, mock_load_cache, mock_fetch):
        """Test getting playlists from cache."""
        # Setup cached data
        cached_data = [
            {'id': 'p1', 'name': 'Cached Playlist', 'track_count': 3}
        ]
        mock_load_cache.return_value = cached_data
        
        # Test with cache
        result = self.manager.get_playlists_by_size(10, use_cache=True)
        
        # Verify cache was used
        self.assertEqual(result, cached_data)
        mock_fetch.assert_not_called()  # Should not fetch from API
    
    def test_get_playlists_empty_result(self):
        """Test when no playlists match criteria."""
        with patch('spotify_playlist_size_manager.fetch_user_playlists') as mock_fetch:
            mock_fetch.return_value = self.sample_playlists
            
            # Test with max_tracks = 0 (only empty playlists)
            result = self.manager.get_playlists_by_size(0)
            
            # Only the empty playlist should match
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['name'], 'Empty Playlist')
    
    @patch('builtins.input')
    @patch('os.system')
    def test_display_playlists_paginated_quit(self, mock_system, mock_input):
        """Test quitting from pagination display."""
        # Setup
        playlists = [
            {'id': f'p{i}', 'name': f'Playlist {i}', 'track_count': i, 
             'public': True, 'collaborative': False, 'description': ''}
            for i in range(15)  # More than one page
        ]
        
        mock_input.return_value = 'q'  # Quit immediately
        
        # Test
        result = self.manager.display_playlists_paginated(playlists)
        
        self.assertIsNone(result)
        mock_system.assert_called()  # Clear screen was called
    
    @patch('builtins.input')
    @patch('os.system')
    def test_display_playlists_pagination_navigation(self, mock_system, mock_input):
        """Test pagination navigation."""
        # Setup
        playlists = [
            {'id': f'p{i}', 'name': f'Playlist {i}', 'track_count': i, 
             'public': True, 'collaborative': False, 'description': ''}
            for i in range(15)  # More than one page
        ]
        
        # Simulate navigation: next, previous, then quit
        mock_input.side_effect = ['n', 'p', 'q']
        
        # Test
        result = self.manager.display_playlists_paginated(playlists)
        
        self.assertIsNone(result)
        self.assertEqual(mock_input.call_count, 3)
    
    @patch('builtins.input')
    @patch('os.system')
    def test_display_playlists_selection(self, mock_system, mock_input):
        """Test selecting playlists for deletion."""
        # Setup
        playlists = [
            {'id': 'p1', 'name': 'Playlist 1', 'track_count': 1, 
             'public': True, 'collaborative': False, 'description': ''},
            {'id': 'p2', 'name': 'Playlist 2', 'track_count': 2, 
             'public': False, 'collaborative': False, 'description': ''}
        ]
        
        # Simulate selecting playlist 1, then delete
        mock_input.side_effect = ['1', 'd']
        
        # Test
        result = self.manager.display_playlists_paginated(playlists)
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 'p1')
    
    @patch('builtins.input')
    @patch('os.system')
    def test_display_playlists_toggle_all(self, mock_system, mock_input):
        """Test toggling all playlists on current page."""
        # Setup
        playlists = [
            {'id': f'p{i}', 'name': f'Playlist {i}', 'track_count': i, 
             'public': True, 'collaborative': False, 'description': ''}
            for i in range(5)
        ]
        
        # Simulate toggling all, then delete
        mock_input.side_effect = ['a', 'd']
        
        # Test
        result = self.manager.display_playlists_paginated(playlists)
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 5)  # All playlists selected
    
    @patch('builtins.input')
    @patch('time.sleep')
    @patch('cache_utils.clear_cache')
    def test_delete_playlists_confirm(self, mock_clear_cache, mock_sleep, mock_input):
        """Test confirming playlist deletion."""
        # Setup
        playlists = [
            {'id': 'p1', 'name': 'Playlist 1', 'track_count': 10},
            {'id': 'p2', 'name': 'Playlist 2', 'track_count': 20}
        ]
        
        mock_input.return_value = 'DELETE'  # Confirm deletion
        
        # Test
        self.manager.delete_playlists(playlists)
        
        # Verify deletions
        expected_calls = [
            call('p1'),
            call('p2')
        ]
        self.mock_sp.current_user_unfollow_playlist.assert_has_calls(expected_calls)
        self.assertEqual(self.mock_sp.current_user_unfollow_playlist.call_count, 2)
        
        # Verify cache was cleared
        mock_clear_cache.assert_called_once()
    
    @patch('builtins.input')
    def test_delete_playlists_cancel(self, mock_input):
        """Test cancelling playlist deletion."""
        # Setup
        playlists = [{'id': 'p1', 'name': 'Playlist 1', 'track_count': 10}]
        
        mock_input.return_value = 'CANCEL'  # Don't confirm
        
        # Test
        self.manager.delete_playlists(playlists)
        
        # Verify no deletions
        self.mock_sp.current_user_unfollow_playlist.assert_not_called()
    
    @patch('builtins.input')
    @patch('time.sleep')
    def test_delete_playlists_with_errors(self, mock_sleep, mock_input):
        """Test handling errors during deletion."""
        # Setup
        playlists = [
            {'id': 'p1', 'name': 'Playlist 1', 'track_count': 10},
            {'id': 'p2', 'name': 'Playlist 2', 'track_count': 20}
        ]
        
        mock_input.return_value = 'DELETE'
        
        # Make first deletion fail
        self.mock_sp.current_user_unfollow_playlist.side_effect = [
            Exception("API Error"),
            None  # Second one succeeds
        ]
        
        # Test
        self.manager.delete_playlists(playlists)
        
        # Verify both deletions were attempted
        self.assertEqual(self.mock_sp.current_user_unfollow_playlist.call_count, 2)
    
    @patch('spotify_playlist_size_manager.PlaylistSizeManager.setup')
    @patch('spotify_playlist_size_manager.PlaylistSizeManager.get_playlists_by_size')
    @patch('spotify_playlist_size_manager.PlaylistSizeManager.display_playlists_paginated')
    @patch('builtins.input')
    def test_run_full_flow(self, mock_input, mock_display, mock_get_playlists, mock_setup):
        """Test the full run flow."""
        # Setup
        mock_setup.return_value = True
        mock_get_playlists.return_value = [
            {'id': 'p1', 'name': 'Small Playlist', 'track_count': 5}
        ]
        mock_display.return_value = None  # No selection
        
        # User inputs: 10 tracks, then quit
        mock_input.side_effect = ['10', 'n']
        
        # Test
        self.manager.run()
        
        # Verify flow
        mock_setup.assert_called_once()
        mock_get_playlists.assert_called_once_with(10)
        mock_display.assert_called_once()
    
    @patch('spotify_playlist_size_manager.PlaylistSizeManager.setup')
    def test_run_setup_failure(self, mock_setup):
        """Test run when setup fails."""
        mock_setup.return_value = False
        
        # Test
        self.manager.run()
        
        # Should exit early
        mock_setup.assert_called_once()
        # No other methods should be called


class TestPlaylistSizeManagerIntegration(unittest.TestCase):
    """Integration tests for the playlist size manager."""
    
    def test_script_imports(self):
        """Test that the script can be imported."""
        try:
            import spotify_playlist_size_manager
            self.assertTrue(hasattr(spotify_playlist_size_manager, 'main'))
            self.assertTrue(hasattr(spotify_playlist_size_manager, 'PlaylistSizeManager'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_playlist_size_manager: {e}")
    
    def test_constants_defined(self):
        """Test that required constants are defined."""
        import spotify_playlist_size_manager
        
        self.assertTrue(hasattr(spotify_playlist_size_manager, 'PAGE_SIZE'))
        self.assertTrue(hasattr(spotify_playlist_size_manager, 'CACHE_KEY_PREFIX'))
        self.assertTrue(hasattr(spotify_playlist_size_manager, 'CACHE_EXPIRATION'))
    
    @patch('spotify_playlist_size_manager.PlaylistSizeManager.run')
    def test_main_function(self, mock_run):
        """Test the main function."""
        import spotify_playlist_size_manager
        
        # Test normal execution
        spotify_playlist_size_manager.main()
        mock_run.assert_called_once()
    
    @patch('spotify_playlist_size_manager.PlaylistSizeManager.run')
    def test_main_keyboard_interrupt(self, mock_run):
        """Test handling KeyboardInterrupt in main."""
        import spotify_playlist_size_manager
        
        mock_run.side_effect = KeyboardInterrupt()
        
        # Should handle gracefully
        spotify_playlist_size_manager.main()
        mock_run.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)