#!/usr/bin/env python3
"""
Tests for spotify_like_songs.py.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spotify_like_songs

class TestSpotifyLikeSongs(unittest.TestCase):
    """Test suite for spotify_like_songs.py."""

    def test_is_christmas_song(self):
        """Test Christmas song detection."""
        # Christmas song
        track1 = {
            'name': 'All I Want for Christmas Is You',
            'artists': [{'name': 'Mariah Carey'}],
            'album': 'Merry Christmas'
        }
        self.assertTrue(spotify_like_songs.is_christmas_song(track1))
        
        # Non-Christmas song
        track2 = {
            'name': 'Bohemian Rhapsody',
            'artists': [{'name': 'Queen'}],
            'album': 'A Night at the Opera'
        }
        self.assertFalse(spotify_like_songs.is_christmas_song(track2))

    def test_filter_christmas_songs(self):
        """Test filtering of Christmas songs."""
        tracks = [
            {'name': 'Jingle Bell Rock', 'artists': [{'name': 'Bobby Helms'}], 'album': 'Unknown'},
            {'name': 'Shape of You', 'artists': [{'name': 'Ed Sheeran'}], 'album': 'Divide'}
        ]
        
        # Case 1: Filtering enabled
        filtered = spotify_like_songs.filter_christmas_songs(tracks, exclude_christmas=True)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['name'], 'Shape of You')
        
        # Case 2: Filtering disabled
        all_tracks = spotify_like_songs.filter_christmas_songs(tracks, exclude_christmas=False)
        self.assertEqual(len(all_tracks), 2)

    def test_analyze_artist_frequency(self):
        """Test artist frequency analysis."""
        tracks = [
            {
                'name': 'Song 1',
                'artists': [{'id': 'artist1', 'name': 'Artist 1'}]
            },
            {
                'name': 'Song 2',
                'artists': [{'id': 'artist1', 'name': 'Artist 1'}]
            },
            {
                'name': 'Song 3',
                'artists': [{'id': 'artist2', 'name': 'Artist 2'}]
            }
        ]
        
        counts, _ = spotify_like_songs.analyze_artist_frequency(tracks)
        self.assertEqual(counts['artist1'], 2)
        self.assertEqual(counts['artist2'], 1)

    @patch('spotify_like_songs.fetch_followed_artists')
    def test_get_followed_artists(self, mock_fetch):
        """Test fetching followed artists with progress."""
        mock_fetch.return_value = [{'id': 'artist1'}, {'id': 'artist2'}]
        sp = MagicMock()
        
        ids = spotify_like_songs.get_followed_artists(sp)
        
        self.assertEqual(ids, {'artist1', 'artist2'})
        mock_fetch.assert_called_once()
        # Verify show_progress is True as we updated it
        self.assertTrue(mock_fetch.call_args[1]['show_progress'])

if __name__ == '__main__':
    unittest.main()
