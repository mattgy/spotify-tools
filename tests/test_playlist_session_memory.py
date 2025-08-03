#!/usr/bin/env python3
"""
Test session memory for deleted playlists in playlist size manager.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from spotify_playlist_size_manager import PlaylistSizeManager


class TestPlaylistSessionMemory(unittest.TestCase):
    """Test cases for playlist session memory functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.manager = PlaylistSizeManager()
        self.manager.sp = Mock()
        self.manager.user_id = "test_user"
        
        # Mock playlists
        self.mock_playlists = [
            {
                'id': 'playlist_1',
                'name': 'Small Playlist 1',
                'tracks': {'total': 5},
                'public': True,
                'collaborative': False,
                'owner': {'id': 'test_user'},
                'external_urls': {'spotify': 'https://open.spotify.com/playlist/playlist_1'}
            },
            {
                'id': 'playlist_2',
                'name': 'Small Playlist 2',
                'tracks': {'total': 3},
                'public': False,
                'collaborative': False,
                'owner': {'id': 'test_user'},
                'external_urls': {'spotify': 'https://open.spotify.com/playlist/playlist_2'}
            },
            {
                'id': 'playlist_3',
                'name': 'Small Playlist 3',
                'tracks': {'total': 8},
                'public': True,
                'collaborative': False,
                'owner': {'id': 'test_user'},
                'external_urls': {'spotify': 'https://open.spotify.com/playlist/playlist_3'}
            }
        ]
    
    @patch('spotify_playlist_size_manager.fetch_user_playlists')
    @patch('spotify_playlist_size_manager.load_from_cache')
    @patch('spotify_playlist_size_manager.save_to_cache')
    def test_deleted_playlists_excluded_from_subsequent_searches(self, mock_save_cache, mock_load_cache, mock_fetch):
        """Test that deleted playlists are excluded from subsequent searches."""
        # Mock fetch_user_playlists to return our test playlists
        mock_fetch.return_value = self.mock_playlists
        
        # Mock cache to return None (force fresh fetch)
        mock_load_cache.return_value = None
        
        # First search - should return all 3 playlists
        playlists = self.manager.get_playlists_by_size(10)
        self.assertEqual(len(playlists), 3)
        
        # Mark playlist_1 as deleted
        self.manager.deleted_playlist_ids.add('playlist_1')
        
        # Second search - should return only 2 playlists (excluding deleted one)
        playlists = self.manager.get_playlists_by_size(10)
        self.assertEqual(len(playlists), 2)
        
        # Verify playlist_1 is not in the results
        playlist_ids = [p['id'] for p in playlists]
        self.assertNotIn('playlist_1', playlist_ids)
        self.assertIn('playlist_2', playlist_ids)
        self.assertIn('playlist_3', playlist_ids)
    
    @patch('spotify_playlist_size_manager.fetch_user_playlists')
    @patch('spotify_playlist_size_manager.load_from_cache')
    @patch('spotify_playlist_size_manager.save_to_cache')
    def test_cached_data_filtered_for_deleted_playlists(self, mock_save_cache, mock_load_cache, mock_fetch):
        """Test that cached data is filtered to exclude deleted playlists."""
        # Mock cached data
        cached_playlists = [
            {'id': 'playlist_1', 'name': 'Cached Playlist 1', 'track_count': 5},
            {'id': 'playlist_2', 'name': 'Cached Playlist 2', 'track_count': 3}
        ]
        mock_load_cache.return_value = cached_playlists
        
        # Mark playlist_1 as deleted
        self.manager.deleted_playlist_ids.add('playlist_1')
        
        # Should return cached data but filtered
        playlists = self.manager.get_playlists_by_size(10)
        
        # Should only have playlist_2
        self.assertEqual(len(playlists), 1)
        self.assertEqual(playlists[0]['id'], 'playlist_2')
        
        # Verify fetch was not called (used cache)
        mock_fetch.assert_not_called()
    
    @patch('spotify_playlist_size_manager.fetch_user_playlists')
    @patch('spotify_playlist_size_manager.load_from_cache')
    @patch('spotify_playlist_size_manager.save_to_cache')
    def test_no_caching_when_playlists_deleted(self, mock_save_cache, mock_load_cache, mock_fetch):
        """Test that results are not cached when playlists have been deleted in session."""
        # Mock fetch_user_playlists to return our test playlists
        mock_fetch.return_value = self.mock_playlists
        mock_load_cache.return_value = None
        
        # Mark a playlist as deleted
        self.manager.deleted_playlist_ids.add('playlist_1')
        
        # Search for playlists
        playlists = self.manager.get_playlists_by_size(10)
        
        # Should not save to cache because we have deleted playlists
        mock_save_cache.assert_not_called()
    
    @patch('spotify_playlist_size_manager.fetch_user_playlists')
    @patch('spotify_playlist_size_manager.load_from_cache')
    @patch('spotify_playlist_size_manager.save_to_cache')
    def test_caching_works_when_no_deletions(self, mock_save_cache, mock_load_cache, mock_fetch):
        """Test that caching works normally when no deletions have occurred."""
        # Mock fetch_user_playlists to return our test playlists
        mock_fetch.return_value = self.mock_playlists
        mock_load_cache.return_value = None
        
        # No deleted playlists
        self.assertEqual(len(self.manager.deleted_playlist_ids), 0)
        
        # Search for playlists
        playlists = self.manager.get_playlists_by_size(10)
        
        # Should save to cache because no deletions occurred
        mock_save_cache.assert_called_once()
    
    def test_delete_playlists_tracks_ids(self):
        """Test that delete_playlists method tracks deleted playlist IDs."""
        # Mock the Spotify API call
        self.manager.sp.current_user_unfollow_playlist = Mock()
        
        # Create test playlists to delete
        playlists_to_delete = [
            {'id': 'playlist_1', 'name': 'Test Playlist 1', 'track_count': 5},
            {'id': 'playlist_2', 'name': 'Test Playlist 2', 'track_count': 3}
        ]
        
        # Mock user confirmation
        with patch('builtins.input', return_value='DELETE'):
            with patch('spotify_playlist_size_manager.print_header'), \
                 patch('spotify_playlist_size_manager.print_info'), \
                 patch('spotify_playlist_size_manager.print_success'), \
                 patch('cache_utils.clear_cache'):
                
                self.manager.delete_playlists(playlists_to_delete)
        
        # Verify playlist IDs were tracked
        self.assertIn('playlist_1', self.manager.deleted_playlist_ids)
        self.assertIn('playlist_2', self.manager.deleted_playlist_ids)
        self.assertEqual(len(self.manager.deleted_playlist_ids), 2)
    
    def test_delete_playlists_handles_failures(self):
        """Test that failed deletions are not tracked as deleted."""
        # Mock the Spotify API call to fail for playlist_1
        def mock_unfollow(playlist_id):
            if playlist_id == 'playlist_1':
                raise Exception("API Error")
        
        self.manager.sp.current_user_unfollow_playlist = Mock(side_effect=mock_unfollow)
        
        # Create test playlists to delete
        playlists_to_delete = [
            {'id': 'playlist_1', 'name': 'Test Playlist 1', 'track_count': 5},
            {'id': 'playlist_2', 'name': 'Test Playlist 2', 'track_count': 3}
        ]
        
        # Mock user confirmation
        with patch('builtins.input', return_value='DELETE'):
            with patch('spotify_playlist_size_manager.print_header'), \
                 patch('spotify_playlist_size_manager.print_info'), \
                 patch('spotify_playlist_size_manager.print_success'), \
                 patch('spotify_playlist_size_manager.print_error'), \
                 patch('cache_utils.clear_cache'):
                
                self.manager.delete_playlists(playlists_to_delete)
        
        # Only playlist_2 should be tracked (playlist_1 failed)
        self.assertNotIn('playlist_1', self.manager.deleted_playlist_ids)
        self.assertIn('playlist_2', self.manager.deleted_playlist_ids)
        self.assertEqual(len(self.manager.deleted_playlist_ids), 1)


if __name__ == '__main__':
    unittest.main()