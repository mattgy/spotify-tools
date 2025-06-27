#!/bin/bash
# Script to reset the Spotify Tools environment

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Define virtual environment path
VENV_DIR="$SCRIPT_DIR/venv"

# Remove existing virtual environment if it exists
if [ -d "$VENV_DIR" ]; then
    echo "Removing existing virtual environment..."
    rm -rf "$VENV_DIR"
fi

# Create a new virtual environment
echo "Creating new virtual environment..."
python3 -m venv "$VENV_DIR"

# Install dependencies
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo "Environment reset successfully."
echo "Please run ./spotify_run.py to start the application."
