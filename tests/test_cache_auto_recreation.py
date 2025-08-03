#!/usr/bin/env python3
"""
Test cache auto-recreation functionality in cache_utils.py
"""

import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from cache_utils import save_to_cache, load_from_cache, log_cache_corruption, CACHE_DIR


class TestCacheAutoRecreation(unittest.TestCase):
    """Test cases for cache auto-recreation functionality."""
    
    def setUp(self):
        """Set up test environment with temporary cache directory."""
        # Create temporary directory for testing
        self.test_cache_dir = tempfile.mkdtemp()
        
        # Patch CACHE_DIR to use our test directory
        self.cache_dir_patcher = patch('cache_utils.CACHE_DIR', self.test_cache_dir)
        self.cache_dir_patcher.start()
        
        # Also patch the CACHE_DIR in any modules that import it
        import cache_utils
        cache_utils.CACHE_DIR = self.test_cache_dir
    
    def tearDown(self):
        """Clean up test environment."""
        self.cache_dir_patcher.stop()
        
        # Remove test cache directory
        if os.path.exists(self.test_cache_dir):
            shutil.rmtree(self.test_cache_dir)
    
    def test_normal_cache_operation(self):
        """Test that normal cache operations work correctly."""
        test_data = {"key": "value", "number": 42}
        cache_key = "test_normal_cache"
        
        # Save data to cache
        result = save_to_cache(test_data, cache_key)
        self.assertTrue(result)
        
        # Load data from cache
        loaded_data = load_from_cache(cache_key)
        self.assertEqual(loaded_data, test_data)
    
    def test_corrupted_json_auto_recreation(self):
        """Test that corrupted JSON cache files are automatically recreated."""
        cache_key = "test_corrupted_json"
        cache_file = os.path.join(self.test_cache_dir, f"{cache_key}.cache")
        
        # Create corrupted JSON file
        os.makedirs(self.test_cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            f.write("{ invalid json content")
        
        # Verify file exists before test
        self.assertTrue(os.path.exists(cache_file))
        
        # Try to load from corrupted cache
        with patch('cache_utils.print_warning') as mock_warning, \
             patch('cache_utils.print_info') as mock_info:
            
            result = load_from_cache(cache_key, auto_recreate=True)
            
            # Should return None due to corruption
            self.assertIsNone(result)
            
            # Should have printed warning about corruption
            mock_warning.assert_called()
            mock_info.assert_called()
        
        # Corrupted file should be removed
        self.assertFalse(os.path.exists(cache_file))
    
    def test_invalid_cache_structure_auto_recreation(self):
        """Test that cache files with invalid structure are automatically recreated."""
        cache_key = "test_invalid_structure"
        cache_file = os.path.join(self.test_cache_dir, f"{cache_key}.cache")
        
        # Create cache file with invalid structure (missing 'data' key)
        os.makedirs(self.test_cache_dir, exist_ok=True)
        invalid_data = {"timestamp": 1234567890, "invalid": "structure"}
        with open(cache_file, "w") as f:
            json.dump(invalid_data, f)
        
        # Verify file exists before test
        self.assertTrue(os.path.exists(cache_file))
        
        # Try to load from invalid cache
        with patch('cache_utils.print_warning') as mock_warning, \
             patch('cache_utils.print_info') as mock_info:
            
            result = load_from_cache(cache_key, auto_recreate=True)
            
            # Should return None due to invalid structure
            self.assertIsNone(result)
            
            # Should have printed warning about corruption
            mock_warning.assert_called()
            mock_info.assert_called()
        
        # Invalid file should be removed
        self.assertFalse(os.path.exists(cache_file))
    
    def test_auto_recreate_disabled(self):
        """Test that auto-recreation can be disabled."""
        cache_key = "test_auto_recreate_disabled"
        cache_file = os.path.join(self.test_cache_dir, f"{cache_key}.cache")
        
        # Create corrupted JSON file
        os.makedirs(self.test_cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            f.write("{ invalid json content")
        
        # Try to load with auto_recreate=False
        with patch('cache_utils.print_warning') as mock_warning:
            result = load_from_cache(cache_key, auto_recreate=False)
            
            # Should return None due to corruption
            self.assertIsNone(result)
            
            # Should have printed warning
            mock_warning.assert_called()
        
        # File should still exist (not removed)
        self.assertTrue(os.path.exists(cache_file))
    
    def test_cache_corruption_logging(self):
        """Test that cache corruption events are logged."""
        cache_key = "test_corruption_logging"
        error_message = "Test corruption error"
        
        # Test logging function
        log_cache_corruption(cache_key, error_message)
        
        # Check that log file was created
        log_file = os.path.join(self.test_cache_dir, "corruption_log.txt")
        self.assertTrue(os.path.exists(log_file))
        
        # Check log content
        with open(log_file, "r") as f:
            content = f.read()
            self.assertIn(cache_key, content)
            self.assertIn(error_message, content)
    
    def test_io_error_handling(self):
        """Test handling of IO errors during cache operations."""
        cache_key = "test_io_error"
        
        # Create a file that can't be read (simulate IO error)
        cache_file = os.path.join(self.test_cache_dir, f"{cache_key}.cache")
        os.makedirs(self.test_cache_dir, exist_ok=True)
        
        # Create file and make it unreadable
        with open(cache_file, "w") as f:
            f.write('{"data": "test"}')
        
        # Mock open to raise IOError
        with patch('builtins.open', side_effect=IOError("Simulated IO error")):
            with patch('cache_utils.print_warning') as mock_warning:
                result = load_from_cache(cache_key, auto_recreate=True)
                
                # Should return None due to IO error
                self.assertIsNone(result)
                
                # Should have printed warning
                mock_warning.assert_called()
    
    def test_removal_failure_handling(self):
        """Test handling when corrupted cache file removal fails."""
        cache_key = "test_removal_failure"
        cache_file = os.path.join(self.test_cache_dir, f"{cache_key}.cache")
        
        # Create corrupted JSON file
        os.makedirs(self.test_cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            f.write("{ invalid json content")
        
        # Mock os.remove to raise exception
        with patch('os.remove', side_effect=OSError("Permission denied")):
            with patch('cache_utils.print_warning') as mock_warning, \
                 patch('cache_utils.print_error') as mock_error:
                
                result = load_from_cache(cache_key, auto_recreate=True)
                
                # Should return None due to corruption
                self.assertIsNone(result)
                
                # Should have printed both warning and error
                mock_warning.assert_called()
                mock_error.assert_called()
    
    def test_cache_expiration_with_auto_recreation(self):
        """Test that cache expiration works correctly with auto-recreation."""
        test_data = {"key": "value"}
        cache_key = "test_expiration"
        
        # Save data to cache
        save_to_cache(test_data, cache_key)
        
        # Load with very short expiration (should be expired)
        result = load_from_cache(cache_key, expiration=0)
        self.assertIsNone(result)
        
        # Load without expiration (should work)
        result = load_from_cache(cache_key)
        self.assertEqual(result, test_data)
    
    def test_nonexistent_cache_file(self):
        """Test loading from non-existent cache file."""
        result = load_from_cache("nonexistent_cache")
        self.assertIsNone(result)
    
    def test_empty_cache_file(self):
        """Test handling of empty cache files."""
        cache_key = "test_empty_cache"
        cache_file = os.path.join(self.test_cache_dir, f"{cache_key}.cache")
        
        # Create empty file
        os.makedirs(self.test_cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            pass  # Create empty file
        
        # Try to load from empty cache
        with patch('cache_utils.print_warning') as mock_warning:
            result = load_from_cache(cache_key, auto_recreate=True)
            
            # Should return None due to JSON decode error
            self.assertIsNone(result)
            
            # Should have printed warning
            mock_warning.assert_called()
        
        # Empty file should be removed
        self.assertFalse(os.path.exists(cache_file))


if __name__ == '__main__':
    unittest.main()