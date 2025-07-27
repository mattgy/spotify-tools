#!/usr/bin/env python3
"""
Master script for Matt Y's Spotify Tools.
This script provides a menu to access all the Spotify utilities.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import subprocess
import shutil

# Get the directory of this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def check_dependencies():
    """Check if required dependencies are installed and install them if needed."""
    # Define virtual environment path
    venv_dir = os.path.join(SCRIPT_DIR, "venv")
    
    # Check if virtual environment exists
    if not os.path.exists(venv_dir):
        print("Setting up virtual environment...")
        try:
            # Run the install dependencies script
            install_script = os.path.join(SCRIPT_DIR, "install_dependencies.py")
            subprocess.run([sys.executable, install_script], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error setting up virtual environment: {e}")
            sys.exit(1)
    
    # Get path to python in virtual environment
    if os.name == "nt":  # Windows
        python_path = os.path.join(venv_dir, "Scripts", "python")
    else:  # Unix/Linux/Mac
        python_path = os.path.join(venv_dir, "bin", "python")
    
    # Check if python exists in the virtual environment
    if not os.path.exists(python_path):
        print(f"Error: Could not find Python in virtual environment at {python_path}")
        print("Attempting to reinstall dependencies...")
        try:
            # First remove the virtual environment completely if it exists
            if os.path.exists(venv_dir):
                print("Removing existing virtual environment...")
                shutil.rmtree(venv_dir)
            
            # Run the install dependencies script with force flag
            install_script = os.path.join(SCRIPT_DIR, "install_dependencies.py")
            subprocess.run([sys.executable, install_script, "--force"], check=True)
            
            # Check again if python exists in the virtual environment
            if not os.path.exists(python_path):
                print(f"Error: Still could not find Python in virtual environment at {python_path}")
                sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"Error reinstalling dependencies: {e}")
            sys.exit(1)
    
    return python_path

def main():
    """Main function to run the master script."""
    # Check dependencies and get path to python in virtual environment
    python_path = check_dependencies()
    
    # Check if the master script exists
    master_script = os.path.join(SCRIPT_DIR, "spotify_tools.py")
    
    if not os.path.exists(master_script):
        print("Error: Could not find the master script.")
        print(f"Expected location: {master_script}")
        sys.exit(1)
    
    # Run the master script using the python from the virtual environment
    try:
        # Check if the python path exists before running
        if not os.path.exists(python_path):
            print(f"Error: Python executable not found at {python_path}")
            print("Attempting to repair the virtual environment...")
            python_path = check_dependencies()  # This will recreate the venv if needed
            
            if not os.path.exists(python_path):
                print(f"Error: Still could not find Python at {python_path}")
                print("Please try running the script again.")
                sys.exit(1)
        
        # Pass a special environment variable to prevent duplicate setup messages
        env = os.environ.copy()
        env["SPOTIFY_TOOLS_INITIALIZED"] = "1"
        
        subprocess.run([python_path, master_script], check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"Error running the master script: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)

if __name__ == "__main__":
    main()
