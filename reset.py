#!/usr/bin/env python3
"""
Standalone script to reset the Spotify Tools environment.
This script must be run with the system Python, not from within the virtual environment.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import os
import sys
import subprocess
import shutil

def main():
    """Main function to reset the environment."""
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define virtual environment path
    venv_dir = os.path.join(script_dir, "venv")
    
    print("Resetting Spotify Tools environment...")
    
    # Remove existing virtual environment if it exists
    if os.path.exists(venv_dir):
        print("Removing existing virtual environment...")
        try:
            shutil.rmtree(venv_dir)
        except Exception as e:
            print(f"Error removing virtual environment: {e}")
            print("Trying alternative method...")
            try:
                if os.name == "nt":  # Windows
                    subprocess.run(["rmdir", "/s", "/q", venv_dir], check=True, shell=True)
                else:  # Unix/Linux/Mac
                    subprocess.run(["rm", "-rf", venv_dir], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error removing virtual environment: {e}")
                sys.exit(1)
    
    # Create a new virtual environment
    print("Creating new virtual environment...")
    try:
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error creating virtual environment: {e}")
        sys.exit(1)
    
    # Get path to pip in the new virtual environment
    if os.name == "nt":  # Windows
        pip_path = os.path.join(venv_dir, "Scripts", "pip")
    else:  # Unix/Linux/Mac
        pip_path = os.path.join(venv_dir, "bin", "pip")
    
    # Upgrade pip
    print("Upgrading pip...")
    try:
        subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error upgrading pip: {e}")
        sys.exit(1)
    
    # Install dependencies from requirements.txt
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
    
    print("Environment reset successfully.")
    print("Please restart the application to use the new environment.")

if __name__ == "__main__":
    main()
