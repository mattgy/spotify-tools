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
- Fix venv issues: `python3 fix_venv.py`

### Individual Script Execution
All scripts can be run independently:
- `python3 spotify_follow_artists.py`
- `python3 spotify_like_songs.py`
- `python3 spotify_similar_artists.py`
- `python3 spotify_find_concerts.py`
- `python3 spotify_stats.py`
- `python3 spotify_dashboard.py`
- `python3 spotify_playlist_converter.py`
- `python3 spotify_cleanup_artists.py`

### Testing
No formal test suite exists. The project relies on manual testing through the interactive menu system.

## Architecture

### Core Components

1. **Main Entry Points**
   - `spotify_run.py`: Bootstrap script that sets up venv and launches main app
   - `spotify_tools.py`: Main menu interface and application controller

2. **Utility Modules**
   - `credentials_manager.py`: Handles API credential storage and retrieval
   - `cache_utils.py`: Manages local cache files for API responses
   - `tqdm_utils.py`: Progress bar utilities

3. **Feature Scripts**
   - Each major feature is implemented as a standalone script prefixed with `spotify_`
   - Scripts can be run independently or through the main menu

4. **Dashboard System**
   - `dashboard/`: Web-based music analytics dashboard
   - `deploy/`: Production-ready dashboard assets for AWS deployment
   - Uses Flask for local serving, static files for deployment

### Configuration Management

- User config stored in `~/.spotify-tools/`
- Credentials in `~/.spotify-tools/credentials.json`
- Cache files in `~/.spotify-tools/cache/`
- Environment variables automatically loaded from credentials file

### API Integration

- **Spotify Web API**: Primary integration using spotipy library
- **Last.fm API**: For similar artist discovery
- **Web scraping**: For concert information (Songkick API deprecated)

### Data Flow

1. Main script loads credentials from config directory
2. Individual feature scripts use shared credential and cache utilities
3. API responses cached locally with configurable expiration
4. Dashboard aggregates data from multiple sources into JSON files

### Virtual Environment

The project uses a self-managing virtual environment:
- Auto-created on first run via `spotify_run.py`
- Dependencies from `requirements.txt`
- Includes repair mechanisms for broken venv states

## Key Dependencies

- **spotipy**: Spotify Web API client
- **requests**: HTTP client for external APIs
- **flask**: Local dashboard server
- **matplotlib/pandas**: Data visualization and analysis
- **tqdm**: Progress bars
- **colorama**: Cross-platform colored terminal output
- **beautifulsoup4**: Web scraping for concerts

## Development Notes

- No formal build process - Python scripts run directly
- Configuration is environment-based rather than code-based
- Each feature maintains its own error handling and user interaction
- Extensive use of caching to avoid API rate limits
- Graceful degradation when optional APIs are unavailable

## ⚠️ Safety Guidelines for Library Modifications

**CRITICAL: This is Matt Y's personal Spotify library. Exercise extreme caution when making changes.**

### Before Making Any Changes:
1. **Always backup** - Ensure all changes are reversible
2. **Test thoroughly** - Use dev/test accounts when possible
3. **Start small** - Make incremental changes, not wholesale modifications
4. **User consent** - Always confirm before bulk operations on user's library
5. **Dry run mode** - Implement preview/dry-run functionality for destructive operations

### Safe Operations:
- ✅ Reading/analyzing existing data
- ✅ Adding new discovery features
- ✅ Cache management and cleanup
- ✅ Export/backup functionality
- ✅ Dashboard and statistics generation

### Dangerous Operations (Require Extra Caution):
- ⚠️ Following/unfollowing artists in bulk
- ⚠️ Modifying playlists
- ⚠️ Adding/removing liked songs
- ⚠️ Any operation that changes user's library state

### Recommended Approach:
1. Always implement confirmation prompts for library modifications
2. Add undo functionality where possible
3. Maintain detailed logs of all changes made
4. Implement batch operation limits to prevent accidental mass changes
5. Add preview modes that show what would be changed before executing