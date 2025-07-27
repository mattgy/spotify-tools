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
import subprocess

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def install_dependencies():
    """Install required dependencies for testing."""
    print("Installing dependencies for testing...")
    
    # Check if we have a virtual environment
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(script_dir, "venv")
    
    if os.path.exists(venv_dir):
        # Use virtual environment Python
        if os.name == 'nt':  # Windows
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        else:  # Unix/Linux/macOS
            venv_python = os.path.join(venv_dir, "bin", "python")
        
        if os.path.exists(venv_python):
            print(f"Using virtual environment: {venv_python}")
            try:
                subprocess.run([venv_python, "install_dependencies.py"], check=True, capture_output=True)
                print("✅ Dependencies installed successfully")
                return True
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to install dependencies: {e}")
                return False
    
    # Fallback to system Python
    try:
        subprocess.run([sys.executable, "install_dependencies.py"], check=True, capture_output=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False
    except FileNotFoundError:
        print("⚠️ install_dependencies.py not found, skipping dependency installation")
        return False

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
        'spotify_remove_duplicates',
        'spotify_identify_skipped',
        'spotify_playlist_manager',
        'spotify_playlist_converter',
        'cache_utils',
        'credentials_manager',
        'constants',
        'spotify_utils',
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
        ('spotify_remove_duplicates', ['main']),
        ('spotify_identify_skipped', ['main']),
        ('spotify_playlist_manager', ['main']),
        ('spotify_playlist_converter', ['main'])
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
    
    # Discover all tests
    suite = loader.discover(start_dir, pattern='test_*.py')
    print("✅ Loaded all test modules")
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    return result.wasSuccessful()

def run_in_venv():
    """Run tests in virtual environment if available."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(script_dir, "venv")
    
    if os.path.exists(venv_dir):
        # Use virtual environment Python
        if os.name == 'nt':  # Windows
            venv_python = os.path.join(venv_dir, "Scripts", "python")
        else:  # Unix/Linux/macOS
            venv_python = os.path.join(venv_dir, "bin", "python")
        
        if os.path.exists(venv_python):
            print(f"🐍 Running tests in virtual environment: {venv_python}")
            # Re-run this script with the venv Python
            env = os.environ.copy()
            env['SPOTIFY_TOOLS_TESTING'] = '1'  # Flag to prevent infinite recursion
            try:
                result = subprocess.run([venv_python, __file__], env=env)
                sys.exit(result.returncode)
            except Exception as e:
                print(f"❌ Error running tests in venv: {e}")
                print("Falling back to system Python...")
    
    return False

def main():
    """Run all tests."""
    # If we're not already in virtual environment, try to run in it
    if not os.environ.get('SPOTIFY_TOOLS_TESTING'):
        if run_in_venv():
            return  # Successfully ran in venv
    
    print("🧪 Matt Y's Spotify Tools - Comprehensive Test Suite")
    print("=" * 60)
    
    # Try to install dependencies first
    print("Checking dependencies...")
    if not install_dependencies():
        print("⚠️ Some dependencies may be missing. Tests will continue but may fail.")
    
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
        print("⚠️ SOME TESTS FAILED!")
        print("Check the output above for details.")
        print("\n💡 Common issues:")
        print("   - Missing dependencies: Run 'python3 install_dependencies.py'")
        print("   - Virtual environment: Use './spotify_run.py' instead of direct execution")
        print("   - API credentials: Set up credentials via menu option 12")
    
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if all_tests_passed else 1)

if __name__ == '__main__':
    main()