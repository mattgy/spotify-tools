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

## Development Best Practices
- **ASK BEFORE COMMIT**: Ask if you want to commit to Git after any major changes.

## Recent Changes & Important Notes

[... rest of the file remains unchanged ...]