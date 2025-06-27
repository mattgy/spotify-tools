#!/usr/bin/env python3
"""
Script to install dependencies for Matt Y's Spotify Tools.

This script:
1. Checks if the virtual environment exists
2. Creates the virtual environment if it doesn't exist
3. Installs or updates dependencies from requirements.txt

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import subprocess
import argparse

def main():
    """Main function to install dependencies."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Install dependencies for Matt Y's Spotify Tools.")
    parser.add_argument("--force", action="store_true", help="Force reinstallation of dependencies")
    args = parser.parse_args()
    
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define virtual environment path
    venv_dir = os.path.join(script_dir, "venv")
    
    # Check if virtual environment exists
    venv_exists = os.path.exists(venv_dir)
    
    # Create virtual environment if it doesn't exist or if force flag is set
    if not venv_exists or args.force:
        print("Setting up virtual environment...")
        
        # Remove existing virtual environment if it exists and force flag is set
        if venv_exists and args.force:
            print("Removing existing virtual environment...")
            try:
                # Use appropriate command based on OS
                if os.name == "nt":  # Windows
                    subprocess.run(["rmdir", "/s", "/q", venv_dir], check=True, shell=True)
                else:  # Unix/Linux/Mac
                    subprocess.run(["rm", "-rf", venv_dir], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error removing virtual environment: {e}")
                sys.exit(1)
        
        # Create virtual environment
        try:
            # First make sure the directory doesn't exist
            if os.path.exists(venv_dir):
                # Use appropriate command based on OS to remove it completely
                if os.name == "nt":  # Windows
                    subprocess.run(["rmdir", "/s", "/q", venv_dir], check=True, shell=True)
                else:  # Unix/Linux/Mac
                    subprocess.run(["rm", "-rf", venv_dir], check=True)
            
            # Now create a fresh virtual environment
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error creating virtual environment: {e}")
            sys.exit(1)
    
    # Get path to pip in virtual environment
    if os.name == "nt":  # Windows
        pip_path = os.path.join(venv_dir, "Scripts", "pip")
    else:  # Unix/Linux/Mac
        pip_path = os.path.join(venv_dir, "bin", "pip")
    
    # Check if pip exists
    if not os.path.exists(pip_path):
        print(f"Error: Could not find pip at {pip_path}")
        sys.exit(1)
    
    # Upgrade pip
    print("Upgrading pip...")
    try:
        subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error upgrading pip: {e}")
        sys.exit(1)
    
    # Install dependencies
    print("Installing dependencies...")
    requirements_file = os.path.join(script_dir, "requirements.txt")
    
    if not os.path.exists(requirements_file):
        print(f"Error: Could not find requirements.txt at {requirements_file}")
        sys.exit(1)
    
    try:
        subprocess.run([pip_path, "install", "-r", requirements_file], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        sys.exit(1)
    
    print("Dependencies installed successfully.")

if __name__ == "__main__":
    main()
