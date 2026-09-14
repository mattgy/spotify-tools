#!/usr/bin/env python3
"""
Tests for spotify_like_songs.py.
"""

import unittest
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

if __name__ == '__main__':
    unittest.main()
