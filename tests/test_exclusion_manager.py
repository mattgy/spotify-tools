#!/usr/bin/env python3
"""
Tests for exclusion_manager.py.
"""

import unittest
from unittest.mock import patch, mock_open
import os
import sys
import json

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exclusion_manager

class TestExclusionManager(unittest.TestCase):
    """Test suite for exclusion_manager.py."""

    def setUp(self):
        """Set up test data."""
        self.test_exclusions = {
            "tracks": {"track1": {"name": "Track 1"}},
            "artists": {"artist1": {"name": "Artist 1"}},
            "metadata": {"version": "1.0"}
        }

    @patch('exclusion_manager.EXCLUSIONS_FILE', '/tmp/test_exclusions.json')
    @patch('builtins.open', new_callable=mock_open, read_data='{"tracks": {"track1": {}}, "artists": {}}')
    @patch('os.path.exists', return_value=True)
    def test_load_exclusions(self, mock_exists, mock_file):
        """Test loading exclusions from file."""
        # We need to bypass the global initialization or reset it
        with patch('exclusion_manager.os.makedirs'):
            exclusions = exclusion_manager._load_exclusions()
            self.assertIn("track1", exclusions["tracks"])

    @patch('exclusion_manager.EXCLUSIONS_FILE', '/tmp/test_exclusions.json')
    @patch('os.path.exists', return_value=False)
    @patch('exclusion_manager._save_exclusions')
    def test_load_exclusions_no_file(self, mock_save, mock_exists):
        """Test loading exclusions when file doesn't exist."""
        with patch('exclusion_manager.os.makedirs'):
            exclusions = exclusion_manager._load_exclusions()
            self.assertEqual(exclusions["tracks"], {})
            self.assertEqual(exclusions["artists"], {})

    @patch('exclusion_manager._load_exclusions')
    def test_is_excluded(self, mock_load):
        """Test the is_excluded check."""
        mock_load.return_value = self.test_exclusions
        self.assertTrue(exclusion_manager.is_excluded("track1", "track"))
        self.assertTrue(exclusion_manager.is_excluded("artist1", "artist"))
        self.assertFalse(exclusion_manager.is_excluded("track3", "track"))

    @patch('exclusion_manager._load_exclusions')
    @patch('exclusion_manager._save_exclusions')
    def test_add_exclusion(self, mock_save, mock_load):
        """Test adding a single exclusion."""
        mock_load.return_value = {"tracks": {}, "artists": {}, "metadata": {}}
        exclusion_manager.add_exclusion("new_track", "track", name="New Track")
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        self.assertIn("new_track", saved_data["tracks"])
        self.assertEqual(saved_data["tracks"]["new_track"]["name"], "New Track")

if __name__ == '__main__':
    unittest.main()
