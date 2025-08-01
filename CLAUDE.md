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
- `python3 spotify_backup.py`
- `python3 spotify_playlist_converter.py`
- `python3 spotify_cleanup_artists.py`
- `python3 spotify_remove_christmas.py`
- `python3 spotify_identify_skipped.py`
- `python3 spotify_playlist_manager.py`
- `python3 spotify_playlist_size_manager.py`

### Testing
- Comprehensive test suite: `python3 run_tests.py`
- Tests cover imports, syntax, functions, and core functionality
- Run tests in virtual environment for full coverage
- **CRITICAL**: Always run your test suite after making ANY changes, even small ones
- **MANDATORY**: Fix ALL test failures before proceeding with additional changes
- When making changes, look for opportunities to improve testing e.g. add unit tests, expand the test suite
- Test Mode: Set `SPOTIFY_TOOLS_TEST_MODE=1` to avoid credential prompts during testing
- Core test modules: cache_utils, credentials_manager, playlist_size_manager, spotify_playlist_converter

## Development Workflow
- **TEST FIRST**: Run tests before and after every change using `SPOTIFY_TOOLS_TEST_MODE=1 python3 run_tests.py`
- **MANDATORY**: All tests must pass before committing any changes
- Ask whether I want to commit to Git/GitHub after each set of major changes, and automatically look for any sensitive information before committing.
- Update CLAUDE.md with important workflow/architecture changes after major modifications
- Never claim tests are passing without actually running them and verifying the results

## Confidentiality and Communication Guidelines
- **CRITICAL**: Never mention Claude, AI, or any AI tool in Git commit messages, README, or other documentation
- **IMPORTANT**: Do not use phrases like "Generated with Claude Code" or "Co-Authored-By: Claude" in commits
- Keep commit messages professional and focused on the technical changes only

## Recent Changes & Important Notes

### Playlist Converter (Option 1) - MAJOR UPDATE
- Main menu only prompts for directory, threshold selection handled by converter script itself
- Converter script provides full explanation of confidence scores before prompting
- Dual threshold system: auto-accept (70-100, default 85) and manual review (50-auto, default auto-5)
- Includes duplicate playlist detection before creation
- **NEW**: AI-assisted track matching using Gemini, OpenAI, Claude, or Perplexity
- **NEW**: Enhanced text file parsing for various playlist formats
- **NEW**: Artist/title swap detection (e.g., "Sabali - Amadou & Mariam")
- **NEW**: Intelligent featuring artist handling (Ft., Feat., featuring variations)
- **NEW**: Session memory - remembers previous decisions between runs
- **NEW**: Incremental sync with content hashing
- **NEW**: Parallel playlist processing for efficiency
- **NEW**: Bulk track search with deduplication
- **FIXED**: Auto-sync mode now includes text playlist files automatically
- **FIXED**: Delete duplicates no longer prompts twice for text files


### Cache Corruption Fixes
- Added defensive programming across multiple scripts for artist data corruption
- Scripts now handle both proper artist objects and string IDs/names gracefully
- Common pattern: type checking with isinstance() before accessing dict methods
- Artist cleanup tool (option 7) now auto-detects and repairs corrupted cache
- When corruption detected, cache is cleared and user prompted to restart

### Menu Structure Changes - MAJOR UPDATE
- Removed options 4, 5, and 9 from the menu:
  - Option 4: "Remove duplicate songs from Liked Songs" (deleted script)
  - Option 5: "Scan for duplicate tracks in your playlists" (deleted script)  
  - Option 9: "Enhanced analytics & music insights" (deleted script)
- Added new option 4: "Find and manage playlists by track count"
- Moved "Backup & export" from Analytics section to System Management
- Menu now has options 1-12 (was 1-14)
- API credential management is now option 10

### Playlist Size Manager (Option 4) - NEW FEATURE
- Searches for playlists with X or fewer tracks (user-specified threshold)
- Displays results with pagination (10 playlists per page)
- Allows bulk selection and deletion of playlists
- Requires explicit confirmation (type 'DELETE') before removing playlists
- Caches search results for 1 hour to improve performance
- Only shows and manages user-created playlists (not followed playlists)

### Cache Key Standardization
- Option 2 uses "all_liked_songs" cache key for consistency
- Eliminates redundant API calls when scripts run in same session

### Cache System Improvements
- Added cache key sanitization to prevent filesystem errors
- Invalid characters (/, :, *, etc.) replaced with underscores in cache filenames
- Long cache keys automatically truncated with hash to prevent path length issues
- Fixes errors like "No such file or directory" for complex track search cache keys

### Playlist Converter Bug Fixes & Improvements
- Fixed undefined 'playlists' variable error when creating new playlists
- Improved error handling in playlist creation workflow
- Enhanced playlist converter match acceptance dialog with consistent "search again" option across all prompts
- Fixed double-prompting issue for non-standard files in reconcile mode
- Improved manual search flow with AI assistance option
- Better handling of file paths, missing artists, and special characters in playlists
- Enhanced featuring artist extraction and matching

## Cross-Computer Continuity
- Always ensure `.env` file is properly set up when moving between computers
- Verify virtual environment can be recreated using `reset.py` and `install_dependencies.py`
- Check that Spotify API credentials and tokens are current and accessible
- Sync local configuration files to ensure consistent setup across different machines

## AI-Assisted Track Matching
- AI help is optional - only appears if API credentials are configured
- Supports Google Gemini (free tier available), OpenAI GPT-4, Anthropic Claude, Perplexity
- AI suggestions include confidence scores and explanatory notes
- Cached for 7 days to avoid redundant API calls
- Offered when regular search fails or user requests help
- Secure credential storage in ~/.spotify-tools/credentials.json

## Architecture

[... rest of the file remains unchanged ...]