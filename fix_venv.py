#!/usr/bin/env python3
"""
Script to fix the virtual environment for Matt Y's Spotify Tools.
"""

import os
import sys
import subprocess

def main():
    """Main function to fix the virtual environment."""
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define virtual environment path
    venv_dir = os.path.join(script_dir, "venv")
    
    # Remove existing virtual environment if it exists
    if os.path.exists(venv_dir):
        print("Removing existing virtual environment...")
        try:
            # Use appropriate command based on OS
            if os.name == "nt":  # Windows
                subprocess.run(["rmdir", "/s", "/q", venv_dir], check=True)
            else:  # Unix/Linux/Mac
                subprocess.run(["rm", "-rf", venv_dir], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error removing virtual environment: {e}")
            sys.exit(1)
    
    # Create virtual environment
    print("Creating new virtual environment...")
    try:
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error creating virtual environment: {e}")
        sys.exit(1)
    
    # Get path to pip in virtual environment
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
    
    print("Virtual environment fixed and dependencies installed successfully.")

if __name__ == "__main__":
    main()
