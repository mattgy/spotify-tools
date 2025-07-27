#!/usr/bin/env python3
"""
Test runner for Matt Y's Spotify Tools.

This script runs all the unit tests for the Spotify tools project.
Also includes integration tests for menu functionality.
"""

import unittest
import sys
import os
import importlib
import traceback

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_all_imports():
    """Test that all main modules can be imported."""
    modules_to_test = [
        'spotify_tools',
        'spotify_follow_artists', 
        'spotify_like_songs',
        'spotify_similar_artists',
        'spotify_analytics',
        'spotify_backup',
        'spotify_cleanup_artists',
        'spotify_remove_christmas',
        'spotify_stats',
        'cache_utils',
        'credentials_manager',
        'config',
        'musicbrainz_integration',
        'music_discovery',
        'tqdm_utils'
    ]
    
    failed_imports = []
    successful_imports = []
    
    print("Testing module imports...")
    print("=" * 50)
    
    for module_name in modules_to_test:
        try:
            importlib.import_module(module_name)
            print(f"✅ {module_name}")
            successful_imports.append(module_name)
        except Exception as e:
            print(f"❌ {module_name}: {str(e)}")
            failed_imports.append((module_name, str(e)))
    
    print("\n" + "=" * 50)
    print(f"Import Results: {len(successful_imports)}/{len(modules_to_test)} successful")
    
    if failed_imports:
        print("\nFailed imports:")
        for module, error in failed_imports:
            print(f"  - {module}: {error}")
    
    return len(failed_imports) == 0

def test_menu_script_functions():
    """Test that menu scripts have required functions."""
    scripts_to_test = [
        ('spotify_tools', ['main', 'run_script']),
        ('spotify_follow_artists', ['main']),
        ('spotify_like_songs', ['main']),
        ('spotify_similar_artists', ['main']),
        ('spotify_analytics', ['main', 'SpotifyAnalytics']),
        ('spotify_backup', ['main']),
        ('spotify_cleanup_artists', ['main']),
        ('spotify_remove_christmas', ['main']),
        ('spotify_stats', ['main'])
    ]
    
    print("\nTesting script functions...")
    print("=" * 50)
    
    all_passed = True
    
    for script_name, required_functions in scripts_to_test:
        try:
            module = importlib.import_module(script_name)
            missing_functions = []
            
            for func_name in required_functions:
                if not hasattr(module, func_name):
                    missing_functions.append(func_name)
            
            if missing_functions:
                print(f"❌ {script_name}: missing {missing_functions}")
                all_passed = False
            else:
                print(f"✅ {script_name}: all required functions present")
                
        except Exception as e:
            print(f"❌ {script_name}: import error - {str(e)}")
            all_passed = False
    
    return all_passed

def run_unit_tests():
    """Run formal unit tests."""
    print("\nRunning unit tests...")
    print("=" * 50)
    
    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests')
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    return result.wasSuccessful()

def main():
    """Run all tests."""
    print("🧪 Matt Y's Spotify Tools - Comprehensive Test Suite")
    print("=" * 60)
    
    all_tests_passed = True
    
    # Test 1: Module imports
    if not test_all_imports():
        all_tests_passed = False
    
    # Test 2: Script functions
    if not test_menu_script_functions():
        all_tests_passed = False
    
    # Test 3: Unit tests
    if not run_unit_tests():
        all_tests_passed = False
    
    # Final summary
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 ALL TESTS PASSED!")
        print("All menu options should work correctly.")
    else:
        print("⚠️  SOME TESTS FAILED!")
        print("Check the output above for details.")
    
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if all_tests_passed else 1)

if __name__ == '__main__':
    main()