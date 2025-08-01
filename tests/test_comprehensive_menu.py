#!/usr/bin/env python3
"""
Comprehensive menu testing without requiring full dependencies.

This test suite focuses on testing the core menu structure, script availability,
and basic functionality that doesn't require external APIs or heavy dependencies.
"""

import unittest
import sys
import os
import py_compile
import tempfile
import json
from pathlib import Path

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestMenuStructure(unittest.TestCase):
    """Test the main menu structure and script availability."""
    
    def setUp(self):
        """Set up test environment."""
        self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    def test_all_menu_scripts_exist(self):
        """Test that all scripts referenced in the main menu exist."""
        required_scripts = [
            'spotify_tools.py',           # Main menu
            'spotify_follow_artists.py',  # Menu option 6
            'spotify_like_songs.py',      # Menu option 2
            'spotify_similar_artists.py', # Menu option 7
            'spotify_playlist_converter.py', # Menu option 1
            'spotify_cleanup_artists.py', # Menu option 6
            'spotify_backup.py',          # Menu option 7
            'spotify_remove_christmas.py', # Menu option 3
            'spotify_identify_skipped.py', # Menu option 5
            'spotify_playlist_manager.py', # Additional feature
            'cache_utils.py',             # Utility
            'credentials_manager.py',     # Utility
            'constants.py',               # Constants
            'spotify_utils.py',           # Utilities
            'tqdm_utils.py',              # Progress bars
            'install_dependencies.py',   # Dependency management
            'reset.py',                   # Environment reset
        ]
        
        missing_scripts = []
        for script_name in required_scripts:
            script_path = os.path.join(self.script_dir, script_name)
            if not os.path.exists(script_path):
                missing_scripts.append(script_name)
        
        self.assertEqual([], missing_scripts, 
                        f"Missing required scripts: {missing_scripts}")
    
    def test_script_syntax_validation(self):
        """Test that all Python scripts have valid syntax."""
        scripts_to_check = [
            'spotify_tools.py',
            'spotify_follow_artists.py',
            'spotify_like_songs.py',
            'spotify_similar_artists.py',
            'spotify_cleanup_artists.py',
            'spotify_backup.py',
            'spotify_remove_christmas.py',
            'spotify_identify_skipped.py',
            'cache_utils.py',
            'credentials_manager.py',
            'constants.py',
            'spotify_utils.py',
            'tqdm_utils.py',
        ]
        
        syntax_errors = []
        for script_name in scripts_to_check:
            script_path = os.path.join(self.script_dir, script_name)
            if os.path.exists(script_path):
                try:
                    py_compile.compile(script_path, doraise=True)
                except py_compile.PyCompileError as e:
                    syntax_errors.append(f"{script_name}: {e}")
                except Exception as e:
                    # Could be import errors, which we'll ignore for syntax checking
                    pass
        
        self.assertEqual([], syntax_errors, 
                        f"Scripts with syntax errors: {syntax_errors}")

class TestCoreModules(unittest.TestCase):
    """Test core modules that don't require external dependencies."""
    
    def setUp(self):
        """Set up test environment."""
        self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, self.script_dir)
    
    def test_constants_module(self):
        """Test that constants module loads and has required constants."""
        try:
            import constants
            
            # Test that key constants exist
            self.assertTrue(hasattr(constants, 'CACHE_EXPIRATION'))
            self.assertTrue(hasattr(constants, 'CONFIDENCE_THRESHOLDS'))
            self.assertTrue(hasattr(constants, 'BATCH_SIZES'))
            self.assertTrue(hasattr(constants, 'SPOTIFY_SCOPES'))
            
            # Test that they're dictionaries with expected structure
            self.assertIsInstance(constants.CACHE_EXPIRATION, dict)
            self.assertIsInstance(constants.CONFIDENCE_THRESHOLDS, dict)
            self.assertIsInstance(constants.BATCH_SIZES, dict)
            self.assertIsInstance(constants.SPOTIFY_SCOPES, dict)
            
        except ImportError as e:
            self.fail(f"Failed to import constants module: {e}")
    
    def test_credentials_manager_basic_functions(self):
        """Test basic credential manager functionality."""
        try:
            import credentials_manager
            
            # Test that key functions exist
            self.assertTrue(hasattr(credentials_manager, 'get_spotify_credentials'))
            self.assertTrue(hasattr(credentials_manager, 'get_lastfm_api_key'))
            self.assertTrue(hasattr(credentials_manager, 'save_credentials'))
            
        except ImportError as e:
            self.fail(f"Failed to import credentials_manager: {e}")

class TestMenuFunctionality(unittest.TestCase):
    """Test main menu functionality without executing scripts."""
    
    def setUp(self):
        """Set up test environment."""
        self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, self.script_dir)
    
    def test_main_tools_functions(self):
        """Test that main spotify_tools has required functions."""
        try:
            import spotify_tools
            
            # Test required functions exist
            required_functions = [
                'main',
                'run_script',
                'setup_config_directory',
                'clear_caches',
                'check_cache_age',
                'setup_credentials',
                'export_credentials_to_env',
                'setup_virtual_environment',
                'check_and_update_dependencies'
            ]
            
            missing_functions = []
            for func_name in required_functions:
                if not hasattr(spotify_tools, func_name):
                    missing_functions.append(func_name)
            
            self.assertEqual([], missing_functions,
                           f"Missing functions in spotify_tools: {missing_functions}")
            
        except ImportError as e:
            # If colorama is missing, that's expected in test environment
            if 'colorama' in str(e):
                self.skipTest("Colorama dependency not available in test environment")
            else:
                self.fail(f"Failed to import spotify_tools: {e}")
    
    def test_script_main_functions_exist(self):
        """Test that all menu scripts have main functions (without importing)."""
        scripts_with_main = [
            'spotify_follow_artists.py',
            'spotify_like_songs.py',
            'spotify_similar_artists.py',
            'spotify_cleanup_artists.py',
            'spotify_backup.py',
            'spotify_remove_christmas.py',
            'spotify_identify_skipped.py',
            'spotify_playlist_manager.py',
        ]
        
        scripts_without_main = []
        for script_name in scripts_with_main:
            script_path = os.path.join(self.script_dir, script_name)
            if os.path.exists(script_path):
                try:
                    with open(script_path, 'r') as f:
                        content = f.read()
                    
                    # Check for main function definition
                    if 'def main(' not in content:
                        scripts_without_main.append(script_name)
                        
                except Exception as e:
                    scripts_without_main.append(f"{script_name} (read error: {e})")
        
        self.assertEqual([], scripts_without_main,
                        f"Scripts missing main() function: {scripts_without_main}")

class TestConfigurationManagement(unittest.TestCase):
    """Test configuration and setup functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.temp_dir, '.spotify-tools')
        os.makedirs(self.config_dir, exist_ok=True)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_config_directory_structure(self):
        """Test that expected config directory structure can be created."""
        cache_dir = os.path.join(self.config_dir, 'cache')
        credentials_file = os.path.join(self.config_dir, 'credentials.json')
        
        # Create expected structure
        os.makedirs(cache_dir, exist_ok=True)
        
        # Create mock credentials file
        mock_credentials = {
            'SPOTIFY_CLIENT_ID': 'test_id',
            'SPOTIFY_CLIENT_SECRET': 'test_secret',
            'SPOTIFY_REDIRECT_URI': 'http://localhost:8888/callback'
        }
        
        with open(credentials_file, 'w') as f:
            json.dump(mock_credentials, f)
        
        # Verify structure exists
        self.assertTrue(os.path.exists(self.config_dir))
        self.assertTrue(os.path.exists(cache_dir))
        self.assertTrue(os.path.exists(credentials_file))
        
        # Verify credentials can be loaded
        with open(credentials_file, 'r') as f:
            loaded_creds = json.load(f)
        
        self.assertEqual(mock_credentials, loaded_creds)

class TestUtilityModules(unittest.TestCase):
    """Test utility modules basic functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, self.script_dir)
    
    def test_cache_utils_structure(self):
        """Test cache utils has expected functions (without executing)."""
        cache_utils_path = os.path.join(self.script_dir, 'cache_utils.py')
        
        if os.path.exists(cache_utils_path):
            with open(cache_utils_path, 'r') as f:
                content = f.read()
            
            # Check for expected function definitions
            expected_functions = [
                'save_to_cache',
                'load_from_cache',
                'clear_cache',
                'list_caches',
                'get_cache_info'
            ]
            
            missing_functions = []
            for func_name in expected_functions:
                if f'def {func_name}(' not in content:
                    missing_functions.append(func_name)
            
            self.assertEqual([], missing_functions,
                           f"Missing functions in cache_utils: {missing_functions}")
        else:
            self.fail("cache_utils.py not found")
    
    def test_tqdm_utils_structure(self):
        """Test tqdm utils has expected functions (without executing)."""
        tqdm_utils_path = os.path.join(self.script_dir, 'tqdm_utils.py')
        
        if os.path.exists(tqdm_utils_path):
            with open(tqdm_utils_path, 'r') as f:
                content = f.read()
            
            # Check for expected function definitions
            expected_functions = [
                'create_progress_bar',
                'update_progress_bar',
                'close_progress_bar'
            ]
            
            missing_functions = []
            for func_name in expected_functions:
                if f'def {func_name}(' not in content:
                    missing_functions.append(func_name)
            
            self.assertEqual([], missing_functions,
                           f"Missing functions in tqdm_utils: {missing_functions}")
        else:
            self.fail("tqdm_utils.py not found")

if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)