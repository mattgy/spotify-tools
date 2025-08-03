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
- **MANDATORY**: Use virtual environment: `./venv/bin/python run_tests.py` (never use system python3)
- Tests cover imports, syntax, functions, and core functionality
- Run tests in virtual environment for full coverage
- **CRITICAL**: Always run your test suite after making ANY changes, even small ones
- **MANDATORY**: Fix ALL test failures before proceeding with additional changes
- When making changes, look for opportunities to improve testing e.g. add unit tests, expand the test suite
- Test Mode: Set `SPOTIFY_TOOLS_TEST_MODE=1` to avoid credential prompts during testing
- Core test modules: cache_utils, credentials_manager, playlist_size_manager, spotify_playlist_converter

## Development Workflow
- **TEST FIRST**: Run tests before and after every change using `./venv/bin/python run_tests.py` (always use virtual environment)
- **MANDATORY**: All tests must pass before committing any changes
- **IMPORTANT**: Always ASK the user if they want to commit changes after major modifications - never commit automatically
- Check for sensitive information before any commit (API keys, personal data, etc.)
- Update CLAUDE.md with important workflow/architecture changes after major modifications
- Never claim tests are passing without actually running them and verifying the results

## Code Quality & Safety Guidelines
- **DEFENSIVE PROGRAMMING**: Always validate inputs and handle edge cases gracefully
- **ERROR HANDLING**: Use try-catch blocks for API calls and file operations
- **CACHE CORRUPTION**: Use the auto-recreation system - corrupted data should be detected and handled automatically
- **CENTRALIZED FUNCTIONS**: Always use existing utility functions (spotify_utils, cache_utils, tqdm_utils) instead of duplicating code
- **PROGRESS BARS**: Use tqdm_utils.py - never import tqdm directly
- **PRINT STATEMENTS**: Use spotify_utils print functions (print_info, print_success, print_warning, print_error)
- **API RATE LIMITING**: Add delays between API calls (time.sleep) to avoid hitting limits

## Session Efficiency Tips
- **CONTEXT PRESERVATION**: Always read relevant files before making changes to understand existing patterns
- **BATCH OPERATIONS**: Group related changes together to minimize context switching  
- **EXISTING PATTERNS**: Follow established code conventions found in the codebase
- **INCREMENTAL TESTING**: Test small changes frequently rather than big batch changes
- **DOCUMENTATION**: Update CLAUDE.md immediately when architectural changes are made

## Common Pitfalls to Avoid
- **DON'T**: Import system modules directly when centralized utilities exist
- **DON'T**: Assume libraries are available without checking imports in similar files
- **DON'T**: Use `python3` command - always use `./venv/bin/python`
- **DON'T**: Duplicate progress bar or print logic - use centralized functions
- **DON'T**: Ignore cache corruption - the auto-recreation system handles it
- **DON'T**: Make assumptions about data structure - validate before accessing dict keys
- **DON'T**: Commit without explicit user approval

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


### Cache Corruption Fixes & Auto-Recreation
- Added defensive programming across multiple scripts for artist data corruption
- Scripts now handle both proper artist objects and string IDs/names gracefully
- Common pattern: type checking with isinstance() before accessing dict methods
- Artist cleanup tool (option 7) now auto-detects and repairs corrupted cache
- **NEW**: Automatic cache recreation - corrupted cache files are automatically detected and removed
- **NEW**: Cache corruption events are logged to corruption_log.txt for monitoring
- **NEW**: Comprehensive test suite covers all cache corruption scenarios and auto-recreation
- When corruption detected, cache is automatically removed and will be recreated on next access

### Menu Structure Changes - MAJOR UPDATE
- **LATEST**: Removed section headers ("PLAYLIST MANAGEMENT:", "ARTIST MANAGEMENT:", "SYSTEM MANAGEMENT:")
- Menu now presents a clean, organized list without visual section dividers
- Items are grouped logically: playlist tools (1-4), artist tools (5-7), system tools (8-12)
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

### Key Design Principles
- **CENTRALIZATION**: Common functionality is centralized in utility modules to avoid duplication
- **CACHE-FIRST**: All expensive operations (API calls) use caching with automatic corruption handling
- **DEFENSIVE**: Input validation and graceful error handling throughout
- **PROGRESS FEEDBACK**: User-friendly progress indicators for long-running operations
- **SESSION STATE**: Some features maintain session-level state (e.g., deleted playlists) without persisting to cache
- **MODULAR**: Each script can run independently while sharing common utilities
- **TESTABLE**: Comprehensive test coverage with mocking for external dependencies

### Data Flow Patterns
- **API → Cache → User**: Expensive API calls are cached and filtered before presentation
- **User Input → Validation → Processing**: All user inputs are validated before processing
- **Error → Log → Graceful Degradation**: Errors are logged and handled without crashing
- **State Changes → Session Memory**: Important state (like deletions) is tracked during sessions

### Core Modules
- `spotify_utils.py`: Shared utilities for Spotify API interactions, authentication, and common operations
- `cache_utils.py`: Caching system with automatic corruption detection and cleanup
- `credentials_manager.py`: Secure credential storage and retrieval
- `constants.py`: Application constants, cache keys, and configuration values
- `tqdm_utils.py`: Centralized progress bar utilities for consistent UX

[... rest of the file remains unchanged ...]