#!/usr/bin/env python3
"""
Tests for spotify_create_from_list.py.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spotify_create_from_list as create_tool

class TestCreateFromList(unittest.TestCase):
    """Test suite for spotify_create_from_list.py."""

    def test_main_function_exists(self):
        """Verify main() exists."""
        self.assertTrue(callable(create_tool.main))

    def test_get_pasted_input(self):
        """Test the pasted input function."""
        with patch('builtins.input', side_effect=['Artist 1 - Title 1', 'Artist 2 - Title 2', '']):
            result = create_tool.get_pasted_input()
            self.assertEqual(result, "Artist 1 - Title 1\nArtist 2 - Title 2")

    @patch('spotify_create_from_list.create_spotify_client')
    @patch('spotify_create_from_list.get_pasted_input')
    @patch('spotify_create_from_list.converter.process_playlist_file')
    @patch('spotify_create_from_list.converter.parse_text_playlist_file')
    @patch('builtins.input')
    @patch('os.unlink')
    @patch('shutil.copy')
    def test_main_flow_pasted(self, mock_copy, mock_unlink, mock_input, mock_parse, mock_process, mock_pasted, mock_client):
        """Test the main flow when using pasted input."""
        # Mocking
        mock_sp = MagicMock()
        mock_client.return_value = mock_sp
        mock_sp.current_user.return_value = {'id': 'test_user', 'display_name': 'Test User'}
        
        # Choice 2 (pasted), Playlist Name (default), Use settings (y)
        mock_input.side_effect = ['2', 'My Playlist', 'y']
        mock_pasted.return_value = "Artist 1 - Title 1"
        mock_parse.return_value = [{'artist': 'Artist 1', 'title': 'Title 1'}]
        mock_process.return_value = (1, 0) # 1 matched, 0 skipped
        
        # Execution
        create_tool.main()
        
        # Verification
        mock_client.assert_called_once()
        mock_pasted.assert_called_once()
        mock_process.assert_called_once()
        self.assertEqual(mock_process.call_args[1]['user_id'], 'test_user')

    @patch('spotify_create_from_list.create_spotify_client')
    @patch('spotify_create_from_list.converter.process_playlist_file')
    @patch('spotify_create_from_list.converter.parse_text_playlist_file')
    @patch('builtins.input')
    @patch('os.path.exists')
    @patch('os.path.isfile')
    def test_main_flow_file(self, mock_isfile, mock_exists, mock_input, mock_parse, mock_process, mock_client):
        """Test the main flow when using a file input."""
        # Mocking
        mock_sp = MagicMock()
        mock_client.return_value = mock_sp
        mock_sp.current_user.return_value = {'id': 'test_user', 'display_name': 'Test User'}
        
        # Choice 1 (file), File Path, Use settings (y)
        mock_input.side_effect = ['1', 'songs.txt', '', 'y']
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_parse.return_value = [{'artist': 'Artist 1', 'title': 'Title 1'}]
        mock_process.return_value = (1, 0)
        
        # Execution
        with patch('os.path.basename', return_value='songs.txt'):
            with patch('os.path.splitext', return_value=('songs', '.txt')):
                with patch('shutil.copy'):
                    with patch('os.unlink'):
                        create_tool.main()
        
        # Verification
        mock_client.assert_called_once()
        mock_process.assert_called_once()

if __name__ == '__main__':
    unittest.main()
