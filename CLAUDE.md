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
- `python3 spotify_analytics.py`
- `python3 spotify_backup.py`
- `python3 spotify_playlist_converter.py`
- `python3 spotify_cleanup_artists.py`
- `python3 spotify_remove_christmas.py`
- `python3 spotify_remove_duplicates.py`
- `python3 spotify_identify_skipped.py`
- `python3 spotify_playlist_manager.py`

### Testing
No formal test suite exists. The project relies on manual testing through the interactive menu system.

## Architecture

### Core Components

1. **Main Entry Points**
   - `spotify_run.py`: Bootstrap script that sets up venv and launches main app
   - `spotify_tools.py`: Main menu interface and application controller

2. **Utility Modules**
   - `spotify_utils.py`: Centralized authentication, rate limiting, and shared utilities
   - `constants.py`: Centralized configuration values, cache times, confidence thresholds
   - `cache_utils.py`: Manages local cache files for API responses
   - `tqdm_utils.py`: Progress bar utilities
   - `credentials_manager.py`: Handles API credential storage and retrieval

3. **Feature Scripts**
   - Each major feature is implemented as a standalone script prefixed with `spotify_`
   - Scripts can be run independently or through the main menu

4. **Testing Framework**
   - `tests/test_menu_integration.py`: Menu integration tests
   - `run_tests.py`: Test runner script

### Configuration Management

- User config stored in `~/.spotify-tools/`
- Credentials in `~/.spotify-tools/credentials.json`
- Cache files in `~/.spotify-tools/cache/`
- Environment variables automatically loaded from credentials file

### API Integration

- **Spotify Web API**: Primary integration using spotipy library
- **Last.fm API**: For similar artist discovery
- **MusicBrainz**: For enhanced metadata and geographic information

### Data Flow

1. Main script loads credentials from config directory
2. Individual feature scripts use shared credential and cache utilities
3. API responses cached locally with configurable expiration
4. All shared functionality centralized in spotify_utils.py

### Virtual Environment

The project uses a self-managing virtual environment:
- Auto-created on first run via `spotify_run.py`
- Dependencies from `requirements.txt`
- Includes repair mechanisms for broken venv states

## Key Dependencies

- **spotipy**: Spotify Web API client
- **requests**: HTTP client for external APIs
- **thefuzz**: Fuzzy string matching for playlist conversion
- **matplotlib/pandas**: Data visualization and analysis
- **tqdm**: Progress bars
- **colorama**: Cross-platform colored terminal output
- **beautifulsoup4**: Web scraping for enhanced data

## Development Notes

- No formal build process - Python scripts run directly
- Configuration is environment-based rather than code-based
- Each feature maintains its own error handling and user interaction
- Extensive use of caching to avoid API rate limits
- Graceful degradation when optional APIs are unavailable

## Important Code Patterns

### Authentication
- Always use `spotify_utils.create_spotify_client()` for authentication
- Use appropriate scopes from `constants.SPOTIFY_SCOPES`
- Never hardcode credentials - use credentials_manager.py

### Print Functions
- Use centralized print functions from spotify_utils: `print_success`, `print_error`, `print_warning`, `print_info`, `print_header`
- Never define duplicate print functions in individual scripts

### Configuration
- Use centralized constants from `constants.py`
- Cache expiration times: `CACHE_EXPIRATION`
- Confidence thresholds: `CONFIDENCE_THRESHOLDS`
- Batch sizes: `BATCH_SIZES`
- Spotify scopes: `SPOTIFY_SCOPES`

### Error Handling
- Always include try/catch blocks for API calls
- Use rate limiting with delays between API calls
- Provide clear error messages to users
- Graceful degradation when services are unavailable

## Security Guidelines

- **Never hardcode API keys or secrets**
- **Never commit credentials to git**
- Use `.gitignore` to exclude sensitive files
- Store credentials in `~/.spotify-tools/credentials.json`
- Use environment variables when appropriate

## Git Commit Guidelines

- **Never include AI authorship references** in commit messages
- **Never mention Claude, GPT, or other AI tools** in commits
- Focus on technical changes and feature descriptions
- Use clear, descriptive commit messages
- Include breaking changes and migration notes when applicable

## User Experience Guidelines

- Always provide clear feedback to users
- Use progress bars for long-running operations
- Ask for confirmation before destructive operations
- Provide helpful error messages with suggested solutions
- Cache data to improve performance and avoid API limits

## Menu System

The main menu has 14 options organized into categories:
1. **Playlist Management** (options 1-5)
2. **Artist Management** (options 6-8) 
3. **Analytics & Insights** (options 9-10)
4. **System Management** (options 11-14)

When adding new features:
- Add script path constant to top of spotify_tools.py
- Add menu option in appropriate category
- Update choice numbers for all subsequent options
- Update the input prompt range
- Add the elif case in the correct numerical order

## Testing Strategy

- Test each menu option manually after changes
- Run `python3 -m py_compile` on modified files
- Use the testing framework in `tests/` directory
- Test authentication flows end-to-end
- Verify caching behavior works correctly

## Performance Considerations

- Use appropriate cache expiration times from constants.py
- Implement rate limiting between API calls
- Process items in batches using BATCH_SIZES constants
- Use progress bars for user feedback on long operations
- Implement early exit conditions for high-confidence matches

## Common Issues and Solutions

- **Import errors**: Use the reset environment option (menu 13)
- **Authentication failures**: Re-run credential setup (menu 12)
- **Rate limiting**: Increase delays in constants.py
- **Cache corruption**: Clear caches (menu 11)
- **File not found**: Ensure all new scripts are added to git

## Future Development Guidelines

- Maintain backward compatibility when possible
- Use the existing utility functions instead of recreating
- Follow the established naming conventions
- Add comprehensive error handling for new features
- Update this documentation when adding new patterns or requirements

## Recent Architecture Changes

- Centralized all authentication in spotify_utils.py
- Moved configuration to constants.py
- Removed duplicate print functions across files
- Enhanced security with comprehensive auditing
- Improved fuzzy matching efficiency for playlist conversion
- Added comprehensive testing framework
- Enhanced error handling and user feedback throughout

## Remaining Development Tasks

The following tasks remain to be completed. Remove completed items from this list:

### High Priority
- Build comprehensive tests for all menu items

### Medium Priority
- Automate environment reset command execution
- Add Christmas playlist filtering option to option 2
- Improve rate limit error messages (remove 'None' retry time)
- Add geographic heat maps of artist origins to analytics
- Expand last.fm, musicbrainz integration and add new APIs
- Add progress indication to option 9 analytics long operations

### Low Priority
- Simplify main menu cache management (190 lines)