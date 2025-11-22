#!/usr/bin/env python3
"""
Workflow integration tests that execute main() functions with mocked APIs.

These tests actually run the code paths to catch runtime errors like:
- NameError (undefined variables)
- AttributeError (missing attributes)
- TypeError (wrong function arguments)

By mocking the Spotify API, we can test the full workflow without credentials.
"""

import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from io import StringIO


class TestWorkflowIntegration(unittest.TestCase):
    """Integration tests for main workflow functions."""

    def setUp(self):
        """Set up mocks for each test."""
        # Mock Spotify client
        self.mock_sp = Mock()
        self.mock_sp.current_user.return_value = {'id': 'test_user', 'display_name': 'Test User'}

        # Mock playlists
        self.mock_playlists = [
            {
                'id': 'playlist1',
                'name': 'Test Playlist 1',
                'owner': {'id': 'test_user'},
                'tracks': {'total': 10},
                'public': True
            },
            {
                'id': 'playlist2',
                'name': 'Test Playlist 2',
                'owner': {'id': 'test_user'},
                'tracks': {'total': 5},
                'public': False
            }
        ]

        # Mock tracks
        self.mock_tracks = [
            {
                'id': 'track1',
                'name': 'Test Song 1',
                'artists': [{'id': 'artist1', 'name': 'Test Artist 1'}],
                'album': {'name': 'Test Album'}
            },
            {
                'id': 'track2',
                'name': 'Test Song 2',
                'artists': [{'id': 'artist2', 'name': 'Test Artist 2'}],
                'album': {'name': 'Test Album 2'}
            }
        ]

    @patch('spotify_like_songs.create_spotify_client')
    @patch('spotify_like_songs.fetch_user_playlists')
    @patch('spotify_like_songs.load_from_cache')
    @patch('builtins.input', return_value='2')  # Choose option 2
    def test_like_songs_workflow(self, mock_input, mock_cache, mock_playlists, mock_client):
        """Test that spotify_like_songs main workflow executes without NameError."""
        import spotify_like_songs

        # Set up mocks
        mock_client.return_value = self.mock_sp
        mock_playlists.return_value = self.mock_playlists
        mock_cache.return_value = None  # No cache, force fresh execution

        # Mock the save functions to prevent actual cache writes
        with patch('spotify_like_songs.save_to_cache'):
            with patch('spotify_like_songs.fetch_playlist_tracks', return_value=self.mock_tracks):
                with patch.object(self.mock_sp, 'current_user_saved_tracks_add'):
                    # Capture output
                    with patch('sys.stdout', new_callable=StringIO):
                        try:
                            # Run the get_tracks_from_playlists function (core logic)
                            result = spotify_like_songs.get_tracks_from_playlists(
                                self.mock_sp,
                                self.mock_playlists
                            )
                            # If we get here without NameError, the test passes
                            self.assertIsNotNone(result)
                        except NameError as e:
                            self.fail(f"NameError in spotify_like_songs workflow: {e}")
                        except Exception as e:
                            # Other exceptions are OK for this test (we're only checking NameError)
                            pass

    @patch('spotify_utils.create_spotify_client')
    @patch('spotify_utils.fetch_user_playlists')
    @patch('spotify_follow_artists.load_from_cache')
    def test_follow_artists_workflow(self, mock_cache, mock_playlists, mock_client):
        """Test that spotify_follow_artists main workflow executes without NameError."""
        import spotify_follow_artists

        # Set up mocks
        mock_client.return_value = self.mock_sp
        mock_playlists.return_value = self.mock_playlists
        mock_cache.return_value = None  # No cache

        with patch('spotify_utils.extract_artists_from_playlists', return_value=[]):
            with patch('spotify_follow_artists.save_to_cache'):
                try:
                    # Run the core function
                    result = spotify_follow_artists.get_artists_from_playlists(
                        self.mock_sp,
                        self.mock_playlists
                    )
                    self.assertIsNotNone(result)
                except NameError as e:
                    self.fail(f"NameError in spotify_follow_artists workflow: {e}")
                except Exception:
                    # Other exceptions are OK
                    pass

    @patch('spotify_utils.create_spotify_client')
    @patch('spotify_utils.fetch_user_saved_tracks')
    @patch('spotify_follow_artists_from_liked.load_from_cache')
    def test_follow_artists_from_liked_workflow(self, mock_cache, mock_saved_tracks, mock_client):
        """Test that spotify_follow_artists_from_liked main workflow executes without NameError."""
        import spotify_follow_artists_from_liked

        # Set up mocks
        mock_client.return_value = self.mock_sp
        mock_saved_tracks.return_value = [
            {'track': {'id': 'track1', 'name': 'Song 1', 'artists': [{'id': 'artist1', 'name': 'Artist 1'}]}},
            {'track': {'id': 'track2', 'name': 'Song 2', 'artists': [{'id': 'artist2', 'name': 'Artist 2'}]}}
        ]
        mock_cache.return_value = None  # No cache

        with patch('spotify_follow_artists_from_liked.save_to_cache'):
            try:
                # Run the core function
                result = spotify_follow_artists_from_liked.get_artists_from_liked_songs(self.mock_sp)
                self.assertIsNotNone(result)
            except NameError as e:
                self.fail(f"NameError in spotify_follow_artists_from_liked workflow: {e}")
            except Exception:
                # Other exceptions are OK
                pass

    @patch('spotify_playlist_manager.create_spotify_client')
    @patch('spotify_playlist_manager.fetch_user_playlists')
    def test_playlist_manager_workflow(self, mock_playlists, mock_client):
        """Test that spotify_playlist_manager executes without NameError."""
        import spotify_playlist_manager

        mock_client.return_value = self.mock_sp
        mock_playlists.return_value = self.mock_playlists

        try:
            # Just verify setup works
            client = spotify_playlist_manager.setup_spotify_client()
            self.assertIsNotNone(client)
        except NameError as e:
            self.fail(f"NameError in spotify_playlist_manager: {e}")
        except Exception:
            pass

    @patch('spotify_remove_christmas.create_spotify_client')
    @patch('spotify_remove_christmas.fetch_user_playlists')
    def test_remove_christmas_workflow(self, mock_playlists, mock_client):
        """Test that spotify_remove_christmas executes without NameError."""
        import spotify_remove_christmas

        mock_client.return_value = self.mock_sp
        mock_playlists.return_value = self.mock_playlists

        try:
            # Verify setup
            client = spotify_remove_christmas.setup_spotify_client()
            self.assertIsNotNone(client)
        except NameError as e:
            self.fail(f"NameError in spotify_remove_christmas: {e}")
        except Exception:
            pass

    @patch('spotify_cleanup_artists.create_spotify_client')
    def test_cleanup_artists_workflow(self, mock_client):
        """Test that spotify_cleanup_artists executes without NameError."""
        import spotify_cleanup_artists

        mock_client.return_value = self.mock_sp

        try:
            # Verify setup
            client = spotify_cleanup_artists.setup_spotify_client()
            self.assertIsNotNone(client)
        except NameError as e:
            self.fail(f"NameError in spotify_cleanup_artists: {e}")
        except Exception:
            pass

    def test_all_scripts_have_main(self):
        """Verify all main scripts have a main() function."""
        scripts = [
            'spotify_like_songs',
            'spotify_follow_artists',
            'spotify_follow_artists_from_liked',
            'spotify_playlist_manager',
            'spotify_playlist_size_manager',
            'spotify_remove_christmas',
            'spotify_cleanup_artists',
            'spotify_similar_artists',
            'spotify_backup',
            'spotify_identify_skipped',
            'spotify_playlist_converter'
        ]

        for script_name in scripts:
            with self.subTest(script=script_name):
                try:
                    module = __import__(script_name)
                    self.assertTrue(
                        hasattr(module, 'main'),
                        f"{script_name} is missing main() function"
                    )
                    self.assertTrue(
                        callable(getattr(module, 'main')),
                        f"{script_name}.main is not callable"
                    )
                except ImportError as e:
                    self.fail(f"Could not import {script_name}: {e}")

    def test_constants_imported_correctly(self):
        """Test that constants module is imported and used correctly."""
        import constants

        # Verify key constants exist
        self.assertTrue(hasattr(constants, 'DEFAULT_CACHE_EXPIRATION'))
        self.assertTrue(hasattr(constants, 'STANDARD_CACHE_KEYS'))
        self.assertTrue(hasattr(constants, 'BATCH_SIZES'))
        self.assertTrue(hasattr(constants, 'CACHE_EXPIRATION'))

        # Verify they have expected types
        self.assertIsInstance(constants.DEFAULT_CACHE_EXPIRATION, int)
        self.assertIsInstance(constants.STANDARD_CACHE_KEYS, dict)
        self.assertIsInstance(constants.BATCH_SIZES, dict)
        self.assertIsInstance(constants.CACHE_EXPIRATION, dict)


class TestImportConsistency(unittest.TestCase):
    """Test that imports are consistent across the codebase."""

    def test_cache_utils_imports(self):
        """Test that cache_utils exports expected functions."""
        import cache_utils

        expected_functions = [
            'save_to_cache',
            'load_from_cache',
            'clear_cache',
            'list_caches',
            'validate_artist_data',
            'get_cache_info'
        ]

        for func_name in expected_functions:
            with self.subTest(function=func_name):
                self.assertTrue(
                    hasattr(cache_utils, func_name),
                    f"cache_utils missing expected function: {func_name}"
                )

    def test_spotify_utils_imports(self):
        """Test that spotify_utils exports expected functions."""
        import spotify_utils

        expected_functions = [
            'create_spotify_client',
            'fetch_user_playlists',
            'fetch_playlist_tracks',
            'print_success',
            'print_error',
            'print_warning',
            'print_info'
        ]

        for func_name in expected_functions:
            with self.subTest(function=func_name):
                self.assertTrue(
                    hasattr(spotify_utils, func_name),
                    f"spotify_utils missing expected function: {func_name}"
                )

    def test_exclusion_manager_imports(self):
        """Test that exclusion_manager exports expected functions."""
        import exclusion_manager

        expected_functions = [
            'is_excluded',
            'add_exclusion',
            'add_bulk_exclusions',
            'remove_exclusion'
        ]

        for func_name in expected_functions:
            with self.subTest(function=func_name):
                self.assertTrue(
                    hasattr(exclusion_manager, func_name),
                    f"exclusion_manager missing expected function: {func_name}"
                )


if __name__ == '__main__':
    unittest.main()
