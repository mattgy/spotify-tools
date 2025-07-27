# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Matt Y's Spotify Tools is a collection of Python utilities for managing Spotify accounts, discovering music, and analyzing listening habits. The project uses a menu-driven interface and includes features like following artists, liking songs, finding similar artists, concert discovery, and music analytics.

## Common Commands

### Running the Application
- Main entry point: `./spotify_run.py` (sets up venv and runs spotify_tools.py)
- Direct execution: `python3 spotify_tools.py` (if venv already exists)

### Environment Management
- Install dependencies: `python3 install_dependencies.py`
- Reset environment: `python3 reset.py` (removes and recreates venv)

### Individual Script Execution
All scripts can be run independently:
- `python3 spotify_follow_artists.py`
- `python3 spotify_like_songs.py`
- `python3 spotify_similar_artists.py`
- `python3 spotify_analytics.py`
- `python3 spotify_backup.py`
- `python3 spotify_playlist_converter.py`
- `python3 spotify_cleanup_artists.py`
- `python3 spotify_remove_christmas.py`
- `python3 spotify_remove_duplicates.py`
- `python3 spotify_identify_skipped.py`
- `python3 spotify_playlist_manager.py`

### Testing
- Comprehensive test suite: `python3 run_tests.py`
- Tests cover imports, syntax, functions, and core functionality
- Run tests in virtual environment for full coverage
- **Always run your test suite after making any significant changes.**
- When making changes, look for opportunities to improve testing e.g. add unit tests, expand the test suite

## Architecture

[... rest of the file remains unchanged ...]