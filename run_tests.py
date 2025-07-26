#!/usr/bin/env python3
"""
Test runner for Spotify Tools.
Run all tests with: python3 run_tests.py
Run specific test: python3 run_tests.py tests.test_cache_utils
"""

import unittest
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_tests(test_pattern=None):
    """Run tests with optional pattern matching."""
    if test_pattern:
        # Run specific test
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(test_pattern)
    else:
        # Discover and run all tests
        loader = unittest.TestLoader()
        start_dir = os.path.join(os.path.dirname(__file__), 'tests')
        suite = loader.discover(start_dir, pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == '__main__':
    test_pattern = sys.argv[1] if len(sys.argv) > 1 else None
    success = run_tests(test_pattern)
    sys.exit(0 if success else 1)