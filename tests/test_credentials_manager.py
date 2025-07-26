#!/usr/bin/env python3
"""
Unit tests for credentials_manager module.
"""

import unittest
import tempfile
import os
import json
import shutil
from unittest.mock import patch
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from credentials_manager import get_spotify_credentials, get_lastfm_api_key


class TestCredentialsManager(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment with temporary config directory."""
        self.test_config_dir = tempfile.mkdtemp()
        self.test_credentials_file = os.path.join(self.test_config_dir, "credentials.json")
        
        # Mock the CONFIG_DIR and CREDENTIALS_FILE constants
        self.config_dir_patcher = patch('credentials_manager.CONFIG_DIR', self.test_config_dir)
        self.credentials_file_patcher = patch('credentials_manager.CREDENTIALS_FILE', self.test_credentials_file)
        self.config_dir_patcher.start()
        self.credentials_file_patcher.start()
    
    def tearDown(self):
        """Clean up test environment."""
        self.config_dir_patcher.stop()
        self.credentials_file_patcher.stop()
        if os.path.exists(self.test_config_dir):
            shutil.rmtree(self.test_config_dir)
    
    def test_get_spotify_credentials_with_file(self):
        """Test getting Spotify credentials when file exists."""
        # Create test credentials file
        test_credentials = {
            "SPOTIFY_CLIENT_ID": "test_client_id",
            "SPOTIFY_CLIENT_SECRET": "test_client_secret",
            "SPOTIFY_REDIRECT_URI": "http://localhost:8888/callback"
        }
        
        with open(self.test_credentials_file, 'w') as f:
            json.dump(test_credentials, f)
        
        client_id, client_secret, redirect_uri = get_spotify_credentials()
        
        self.assertEqual(client_id, "test_client_id")
        self.assertEqual(client_secret, "test_client_secret")
        self.assertEqual(redirect_uri, "http://localhost:8888/callback")
    
    def test_get_spotify_credentials_from_env(self):
        """Test getting Spotify credentials from environment variables."""
        with patch.dict(os.environ, {
            'SPOTIFY_CLIENT_ID': 'env_client_id',
            'SPOTIFY_CLIENT_SECRET': 'env_client_secret',
            'SPOTIFY_REDIRECT_URI': 'http://env-redirect.com/callback'
        }):
            client_id, client_secret, redirect_uri = get_spotify_credentials()
            
            self.assertEqual(client_id, "env_client_id")
            self.assertEqual(client_secret, "env_client_secret")
            self.assertEqual(redirect_uri, "http://env-redirect.com/callback")
    
    def test_get_spotify_credentials_missing(self):
        """Test behavior when Spotify credentials are missing."""
        # Ensure no environment variables are set
        env_vars_to_remove = ['SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET', 'SPOTIFY_REDIRECT_URI']
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                get_spotify_credentials()
    
    def test_get_lastfm_api_key_with_file(self):
        """Test getting Last.fm API key when file exists."""
        test_credentials = {
            "LASTFM_API_KEY": "test_lastfm_key"
        }
        
        with open(self.test_credentials_file, 'w') as f:
            json.dump(test_credentials, f)
        
        api_key = get_lastfm_api_key()
        self.assertEqual(api_key, "test_lastfm_key")
    
    def test_get_lastfm_api_key_from_env(self):
        """Test getting Last.fm API key from environment variables."""
        with patch.dict(os.environ, {'LASTFM_API_KEY': 'env_lastfm_key'}):
            api_key = get_lastfm_api_key()
            self.assertEqual(api_key, "env_lastfm_key")
    
    def test_get_lastfm_api_key_missing(self):
        """Test behavior when Last.fm API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            api_key = get_lastfm_api_key()
            self.assertIsNone(api_key)
    
    def test_credentials_file_priority_over_env(self):
        """Test that credentials file takes priority over environment variables."""
        # Set environment variables
        with patch.dict(os.environ, {
            'SPOTIFY_CLIENT_ID': 'env_client_id',
            'SPOTIFY_CLIENT_SECRET': 'env_client_secret',
            'SPOTIFY_REDIRECT_URI': 'http://env-redirect.com/callback'
        }):
            # Create credentials file with different values
            test_credentials = {
                "SPOTIFY_CLIENT_ID": "file_client_id",
                "SPOTIFY_CLIENT_SECRET": "file_client_secret",
                "SPOTIFY_REDIRECT_URI": "http://file-redirect.com/callback"
            }
            
            with open(self.test_credentials_file, 'w') as f:
                json.dump(test_credentials, f)
            
            client_id, client_secret, redirect_uri = get_spotify_credentials()
            
            # Should use file values, not environment values
            self.assertEqual(client_id, "file_client_id")
            self.assertEqual(client_secret, "file_client_secret")
            self.assertEqual(redirect_uri, "http://file-redirect.com/callback")


if __name__ == '__main__':
    unittest.main()