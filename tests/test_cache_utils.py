#!/usr/bin/env python3
"""
Unit tests for cache_utils module.
"""

import unittest
import tempfile
import os
import json
import time
import shutil
from unittest.mock import patch
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cache_utils import save_to_cache, load_from_cache, clear_cache, get_cache_info, list_caches


class TestCacheUtils(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment with temporary cache directory."""
        self.test_cache_dir = tempfile.mkdtemp()
        # Mock the CACHE_DIR constant
        self.cache_dir_patcher = patch('cache_utils.CACHE_DIR', self.test_cache_dir)
        self.cache_dir_patcher.start()
    
    def tearDown(self):
        """Clean up test environment."""
        self.cache_dir_patcher.stop()
        if os.path.exists(self.test_cache_dir):
            shutil.rmtree(self.test_cache_dir)
    
    def test_save_and_load_cache(self):
        """Test basic save and load functionality."""
        test_data = {"test_key": "test_value", "number": 42}
        cache_key = "test_cache"
        
        # Save data to cache
        save_to_cache(test_data, cache_key)
        
        # Load data from cache
        loaded_data = load_from_cache(cache_key, 3600)  # 1 hour expiration
        
        self.assertEqual(test_data, loaded_data)
    
    def test_cache_expiration(self):
        """Test that expired cache returns None."""
        test_data = {"expired": "data"}
        cache_key = "expired_cache"
        
        # Save data to cache
        save_to_cache(test_data, cache_key)
        
        # Load with very short expiration (should return None for expired cache)
        loaded_data = load_from_cache(cache_key, 0)  # Immediate expiration
        
        self.assertIsNone(loaded_data)
    
    def test_nonexistent_cache(self):
        """Test loading non-existent cache returns None."""
        loaded_data = load_from_cache("nonexistent_cache", 3600)
        self.assertIsNone(loaded_data)
    
    def test_clear_specific_cache(self):
        """Test clearing a specific cache file."""
        test_data = {"to_be_cleared": "data"}
        cache_key = "clear_test"
        
        # Save and verify data exists
        save_to_cache(test_data, cache_key)
        loaded_data = load_from_cache(cache_key, 3600)
        self.assertEqual(test_data, loaded_data)
        
        # Clear the cache
        clear_cache(cache_key)
        
        # Verify data is gone
        loaded_data = load_from_cache(cache_key, 3600)
        self.assertIsNone(loaded_data)
    
    def test_clear_all_caches(self):
        """Test clearing all cache files."""
        # Create multiple cache files
        save_to_cache({"data1": "value1"}, "cache1")
        save_to_cache({"data2": "value2"}, "cache2")
        
        # Verify they exist
        self.assertIsNotNone(load_from_cache("cache1", 3600))
        self.assertIsNotNone(load_from_cache("cache2", 3600))
        
        # Clear all caches
        clear_cache()
        
        # Verify they're gone
        self.assertIsNone(load_from_cache("cache1", 3600))
        self.assertIsNone(load_from_cache("cache2", 3600))
    
    def test_get_cache_info(self):
        """Test cache information retrieval."""
        # Create some cache files
        save_to_cache({"small": "data"}, "small_cache")
        save_to_cache({"large": "data" * 1000}, "large_cache")
        
        info = get_cache_info()
        
        self.assertGreaterEqual(info['count'], 2)
        self.assertGreater(info['total_size'], 0)
        self.assertIsNotNone(info['oldest'])
        self.assertIsNotNone(info['newest'])
    
    def test_list_caches(self):
        """Test listing cache files."""
        # Create cache files
        save_to_cache({"data1": "value1"}, "test_cache_1")
        save_to_cache({"data2": "value2"}, "test_cache_2")
        
        caches = list_caches()
        
        self.assertGreaterEqual(len(caches), 2)
        cache_names = [cache['name'] for cache in caches]
        self.assertIn('test_cache_1', cache_names)
        self.assertIn('test_cache_2', cache_names)
        
        # Check cache structure
        for cache in caches:
            self.assertIn('name', cache)
            self.assertIn('size', cache)
            self.assertIn('mtime', cache)


if __name__ == '__main__':
    unittest.main()