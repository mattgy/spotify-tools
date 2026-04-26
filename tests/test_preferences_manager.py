#!/usr/bin/env python3
"""
Tests for preferences_manager.py.
"""

import unittest
from unittest.mock import patch, mock_open
import os
import sys
import json

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import preferences_manager

class TestPreferencesManager(unittest.TestCase):
    """Test suite for preferences_manager.py."""

    @patch('preferences_manager.PREFERENCES_FILE', '/tmp/test_prefs.json')
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data='{"auto_like_behavior": "aggressive"}')
    def test_get_preference(self, mock_file, mock_exists):
        """Test getting a preference."""
        val = preferences_manager.get_preference("auto_like_behavior")
        self.assertEqual(val, "aggressive")
        
        # Test default value
        val_default = preferences_manager.get_preference("nonexistent.key", "default_val")
        self.assertEqual(val_default, "default_val")

    @patch('preferences_manager._load_preferences')
    @patch('preferences_manager._save_preferences')
    def test_set_preference(self, mock_save, mock_load):
        """Test setting a preference."""
        mock_load.return_value = {"filters": {"skip_unplayed": True}}
        preferences_manager.set_preference("filters.skip_unplayed", False)
        
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        self.assertEqual(saved_data["filters"]["skip_unplayed"], False)

    @patch('preferences_manager.PREFERENCES_FILE', '/tmp/test_prefs.json')
    def test_save_preferences(self):
        """Test saving preferences to file."""
        m = mock_open()
        with patch('builtins.open', m):
            preferences_manager._save_preferences({"key": "val"})
                
        # Check that open was called with the right path and 'w'
        m.assert_called_once_with('/tmp/test_prefs.json', 'w')

if __name__ == '__main__':
    unittest.main()
