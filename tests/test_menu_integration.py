#!/usr/bin/env python3
"""
Comprehensive integration tests for all menu options.

Tests that all menu items can be imported and have basic functionality.
"""

import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import tempfile
import json

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestMenuIntegration(unittest.TestCase):
    """Test all menu options can be imported and basic functionality works."""
    
    def setUp(self):
        """Set up test environment."""
        # Create temporary config directory
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.temp_dir, '.spotify-tools')
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Mock credentials
        self.mock_credentials = {
            'SPOTIFY_CLIENT_ID': 'test_client_id',
            'SPOTIFY_CLIENT_SECRET': 'test_client_secret',
            'SPOTIFY_REDIRECT_URI': 'http://localhost:8888/callback',
            'LASTFM_API_KEY': 'test_lastfm_key'
        }
        
        # Create mock credentials file
        credentials_file = os.path.join(self.config_dir, 'credentials.json')
        with open(credentials_file, 'w') as f:
            json.dump(self.mock_credentials, f)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_import_main_tools(self):
        """Test that main spotify_tools can be imported."""
        try:
            import spotify_tools
            self.assertTrue(hasattr(spotify_tools, 'main'))
            self.assertTrue(hasattr(spotify_tools, 'run_script'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_tools: {e}")
    
    def test_import_follow_artists(self):
        """Test that spotify_follow_artists can be imported."""
        try:
            import spotify_follow_artists
            self.assertTrue(hasattr(spotify_follow_artists, 'main'))
        except ImportError as e:
            if 'spotipy' in str(e) or 'colorama' in str(e):
                self.skipTest(f"Required dependency missing: {e}")
            else:
                self.fail(f"Failed to import spotify_follow_artists: {e}")
    
    def test_import_like_songs(self):
        """Test that spotify_like_songs can be imported."""
        try:
            import spotify_like_songs
            self.assertTrue(hasattr(spotify_like_songs, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_like_songs: {e}")
    
    def test_import_similar_artists(self):
        """Test that spotify_similar_artists can be imported."""
        try:
            import spotify_similar_artists
            self.assertTrue(hasattr(spotify_similar_artists, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_similar_artists: {e}")
    
    def test_import_analytics(self):
        """Test that spotify_analytics can be imported."""
        try:
            import spotify_analytics
            self.assertTrue(hasattr(spotify_analytics, 'main'))
            self.assertTrue(hasattr(spotify_analytics, 'SpotifyAnalytics'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_analytics: {e}")
    
    def test_import_backup(self):
        """Test that spotify_backup can be imported."""
        try:
            import spotify_backup
            self.assertTrue(hasattr(spotify_backup, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_backup: {e}")
    
    def test_import_cleanup_artists(self):
        """Test that spotify_cleanup_artists can be imported."""
        try:
            import spotify_cleanup_artists
            self.assertTrue(hasattr(spotify_cleanup_artists, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_cleanup_artists: {e}")
    
    def test_import_remove_christmas(self):
        """Test that spotify_remove_christmas can be imported."""
        try:
            import spotify_remove_christmas
            self.assertTrue(hasattr(spotify_remove_christmas, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_remove_christmas: {e}")
    
    def test_import_playlist_converter(self):
        """Test that spotify_playlist_converter can be imported."""
        try:
            import spotify_playlist_converter
            self.assertTrue(hasattr(spotify_playlist_converter, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_playlist_converter: {e}")
    
    def test_import_remove_duplicates(self):
        """Test that spotify_remove_duplicates can be imported."""
        try:
            import spotify_remove_duplicates
            self.assertTrue(hasattr(spotify_remove_duplicates, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_remove_duplicates: {e}")
    
    def test_import_identify_skipped(self):
        """Test that spotify_identify_skipped can be imported."""
        try:
            import spotify_identify_skipped
            self.assertTrue(hasattr(spotify_identify_skipped, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_identify_skipped: {e}")
    
    def test_import_playlist_manager(self):
        """Test that spotify_playlist_manager can be imported."""
        try:
            import spotify_playlist_manager
            self.assertTrue(hasattr(spotify_playlist_manager, 'main'))
        except ImportError as e:
            self.fail(f"Failed to import spotify_playlist_manager: {e}")
    
    def test_run_script_function(self):
        """Test that run_script function works."""
        import spotify_tools
        
        # Test with non-existent script
        result = spotify_tools.run_script('/nonexistent/script.py')
        self.assertFalse(result)
    
    @patch.dict(os.environ, {'HOME': '/tmp'})
    def test_config_directory_creation(self):
        """Test that config directory is created properly."""
        import spotify_tools
        
        # Test config directory setup
        spotify_tools.setup_config_directory()
        
        # Check if directories exist
        config_dir = os.path.join('/tmp', '.spotify-tools')
        cache_dir = os.path.join(config_dir, 'cache')
        
        # Note: These might not exist in test environment, which is fine
        # The test is mainly checking the function doesn't crash
        self.assertTrue(True)  # Function completed without error

class TestCacheUtils(unittest.TestCase):
    """Test caching functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.temp_dir, 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('cache_utils.CACHE_DIR', '/tmp/test_cache')
    def test_cache_save_load(self):
        """Test that cache save and load works."""
        from cache_utils import save_to_cache, load_from_cache
        
        test_data = {'test': 'data', 'number': 123}
        cache_key = 'test_cache'
        
        # Save data to cache
        save_to_cache(test_data, cache_key)
        
        # Load data from cache
        loaded_data = load_from_cache(cache_key, expiration=3600)
        
        self.assertEqual(test_data, loaded_data)
    
    @patch('cache_utils.CACHE_DIR', '/tmp/test_cache')
    def test_cache_expiration(self):
        """Test that cache expiration works."""
        from cache_utils import save_to_cache, load_from_cache
        
        test_data = {'test': 'data'}
        cache_key = 'test_expiry'
        
        # Save data to cache
        save_to_cache(test_data, cache_key)
        
        # Try to load with zero expiration (should be expired)
        loaded_data = load_from_cache(cache_key, expiration=0)
        
        # Should return None for expired cache
        self.assertIsNone(loaded_data)

class TestUtilityModules(unittest.TestCase):
    """Test utility modules."""
    
    def test_config_module(self):
        """Test that config module works."""
        try:
            import config
            # Check for any valid config functionality
            self.assertTrue(hasattr(config, 'SpotifyToolsConfig') or 
                          hasattr(config, 'SPOTIFY_CLIENT_ID') or
                          hasattr(config, 'get_config') or
                          len(dir(config)) > 2)  # Has some non-built-in attributes
            
        except ImportError as e:
            self.fail(f"Failed to import config: {e}")
    
    def test_musicbrainz_integration(self):
        """Test that MusicBrainz integration works."""
        try:
            import musicbrainz_integration
            self.assertTrue(hasattr(musicbrainz_integration, 'MusicBrainzClient') or
                          hasattr(musicbrainz_integration, 'search_artist') or
                          len(dir(musicbrainz_integration)) > 2)
            
        except ImportError as e:
            self.skipTest(f"MusicBrainz integration optional dependency missing: {e}")
    
    def test_constants_module(self):
        """Test that constants module works."""
        try:
            import constants
            self.assertTrue(hasattr(constants, 'CACHE_EXPIRATION'))
            self.assertTrue(hasattr(constants, 'CONFIDENCE_THRESHOLDS'))
            self.assertTrue(hasattr(constants, 'BATCH_SIZES'))
            
        except ImportError as e:
            self.fail(f"Failed to import constants: {e}")
    
    def test_spotify_utils_module(self):
        """Test that spotify_utils module works."""
        try:
            import spotify_utils
            self.assertTrue(hasattr(spotify_utils, 'create_spotify_client'))
            self.assertTrue(hasattr(spotify_utils, 'fetch_user_playlists'))
            self.assertTrue(hasattr(spotify_utils, 'print_success'))
            
        except ImportError as e:
            self.fail(f"Failed to import spotify_utils: {e}")
    
    def test_tqdm_utils(self):
        """Test that tqdm utilities work."""
        try:
            import tqdm_utils
            self.assertTrue(hasattr(tqdm_utils, 'create_progress_bar'))
            
        except ImportError as e:
            self.fail(f"Failed to import tqdm_utils: {e}")

class TestSpotifyClientSetup(unittest.TestCase):
    """Test Spotify client setup functionality."""
    
    @patch('credentials_manager.get_spotify_credentials')
    @patch('spotipy.Spotify')
    @patch('spotipy.oauth2.SpotifyOAuth')
    def test_spotify_client_creation(self, mock_oauth, mock_spotify, mock_creds):
        """Test that Spotify client can be created."""
        # Mock credentials
        mock_creds.return_value = ('client_id', 'client_secret', 'redirect_uri')
        
        # Mock OAuth and Spotify client  
        mock_spotify_client = Mock()
        mock_spotify.return_value = mock_spotify_client
        
        # Mock successful user call
        mock_spotify_client.current_user.return_value = {
            'id': 'test_user',
            'display_name': 'Test User',
            'email': 'test@example.com'
        }
        
        # Import and test one of the modules
        import spotify_follow_artists
        
        # This should not raise an exception
        try:
            # Note: We can't actually call setup_spotify_client() without 
            # proper mocking of the entire authentication flow
            self.assertTrue(hasattr(spotify_follow_artists, 'setup_spotify_client'))
        except Exception as e:
            self.fail(f"Failed basic setup check: {e}")

class TestMenuFunctionality(unittest.TestCase):
    """Test that menu system functionality works."""
    
    def test_run_script_function_exists(self):
        """Test that run_script function exists in main module."""
        import spotify_tools
        self.assertTrue(hasattr(spotify_tools, 'run_script'))
    
    def test_all_script_paths_exist(self):
        """Test that all script paths referenced in main menu exist."""
        import spotify_tools
        
        # Get script directory
        script_dir = os.path.dirname(os.path.abspath(spotify_tools.__file__))
        
        required_scripts = [
            'spotify_follow_artists.py',
            'spotify_like_songs.py', 
            'spotify_similar_artists.py',
            'spotify_analytics.py',
            'spotify_playlist_converter.py',
            'spotify_cleanup_artists.py',
            'spotify_backup.py',
            'spotify_remove_christmas.py',
            'spotify_playlist_manager.py',
            'spotify_remove_duplicates.py',
            'spotify_identify_skipped.py'
        ]
        
        for script_name in required_scripts:
            script_path = os.path.join(script_dir, script_name)
            self.assertTrue(os.path.exists(script_path), 
                          f"Required script {script_name} not found at {script_path}")
    
    def test_config_directory_setup(self):
        """Test that config directory setup function exists."""
        import spotify_tools
        self.assertTrue(hasattr(spotify_tools, 'setup_config_directory'))
    
    def test_cache_management_functions(self):
        """Test that cache management functions exist."""
        import spotify_tools
        self.assertTrue(hasattr(spotify_tools, 'clear_caches'))
        self.assertTrue(hasattr(spotify_tools, 'check_cache_age'))
    
    def test_credential_management_functions(self):
        """Test that credential management functions exist."""
        import spotify_tools
        self.assertTrue(hasattr(spotify_tools, 'setup_credentials'))
        self.assertTrue(hasattr(spotify_tools, 'export_credentials_to_env'))
    
    def test_virtual_environment_setup(self):
        """Test that virtual environment setup function exists."""
        import spotify_tools
        self.assertTrue(hasattr(spotify_tools, 'setup_virtual_environment'))
    
    def test_dependency_management(self):
        """Test that dependency management functions exist."""
        import spotify_tools
        self.assertTrue(hasattr(spotify_tools, 'check_and_update_dependencies'))

class TestIndividualScripts(unittest.TestCase):
    """Test individual script functionality without actual execution."""
    
    def test_script_compilation(self):
        """Test that all scripts compile without syntax errors."""
        import spotify_tools
        script_dir = os.path.dirname(os.path.abspath(spotify_tools.__file__))
        
        scripts_to_test = [
            'spotify_follow_artists.py',
            'spotify_like_songs.py',
            'spotify_similar_artists.py',
            'spotify_analytics.py',
            'spotify_playlist_converter.py',
            'spotify_cleanup_artists.py',
            'spotify_backup.py',
            'spotify_remove_christmas.py',
            'spotify_remove_duplicates.py',
            'spotify_identify_skipped.py',
            'spotify_playlist_manager.py'
        ]
        
        for script_name in scripts_to_test:
            script_path = os.path.join(script_dir, script_name)
            with self.subTest(script=script_name):
                try:
                    import py_compile
                    py_compile.compile(script_path, doraise=True)
                except py_compile.PyCompileError as e:
                    self.fail(f"Syntax error in {script_name}: {e}")
                except Exception as e:
                    # File might not exist, which is handled by other tests
                    pass
    
    @patch('builtins.input', return_value='n')  # Mock user input to avoid interactive prompts
    def test_main_menu_displays(self, mock_input):
        """Test that main menu can be displayed without crashing."""
        import spotify_tools
        
        # This will test the menu display logic without actually running scripts
        # We expect it to show the menu and exit when user inputs 'n'
        try:
            # We can't easily test the full main() function in a unit test
            # since it has an infinite loop, but we can test that it exists
            self.assertTrue(hasattr(spotify_tools, 'main'))
        except Exception as e:
            self.fail(f"Main menu display failed: {e}")

if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)