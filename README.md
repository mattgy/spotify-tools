# Matt Y's Spotify Tools

A comprehensive collection of Python utilities for managing your Spotify account, discovering music, and analyzing listening habits. Features a menu-driven interface with advanced automation, analytics, and music discovery capabilities.

## 🚀 How to Run

**Simple 3-step setup:**

1. **Clone and enter the directory**:
   ```bash
   git clone https://github.com/mattgy/spotify-tools.git
   cd spotify-tools
   ```

2. **Run the program** (auto-installs everything):
   ```bash
   ./spotify_run.py
   ```

3. **Set up Spotify credentials** (one-time):
   - Create a free Spotify app at [developer.spotify.com](https://developer.spotify.com/dashboard/)
   - Set redirect URI to: `http://127.0.0.1:8888/callback`
   - Use menu option 12 to enter your Client ID and Client Secret
   - (Optional) Add AI service API keys for enhanced track matching

**That's it!** The program handles Python virtual environment setup, dependency installation, and provides a user-friendly menu.

## 🎵 Core Features

### Playlist Management
- **Convert Local Playlists**: Transform M3U, M3U8, PLS, and text files into Spotify playlists
  - Advanced fuzzy matching with artist/title swap detection
  - AI-assisted matching for difficult-to-find tracks (optional)
  - Intelligent featuring artist handling (Ft., Feat., featuring variations)
  - Session memory - remembers your decisions between runs
  - Incremental sync and parallel processing for efficiency
- **Add Songs to Liked Songs**: Automatically like all songs from your created playlists (with optional Christmas filtering)
- **Remove Christmas Songs**: Intelligent detection and removal of holiday music from your library
- **Remove Duplicate Songs**: Find and remove duplicate tracks from your Liked Songs with smart matching
- **Scan for Playlist Duplicates**: Find duplicate tracks within your playlists

### Artist Management
- **Follow Playlist Artists**: Automatically follow all artists from your playlists
- **Smart Artist Discovery**: Find new artists you'll probably like using multi-source recommendations
- **Artist Cleanup**: Remove followed artists you don't listen to with bulk filtering options
- **Auto-Follow Feature**: Automatically follow artists when you like multiple songs from them

### Analytics & Insights
- **Enhanced Music Analytics**: Comprehensive analysis of your music taste and listening patterns
- **Geographic Heat Maps**: Visualize artist origins and discover music from different regions
- **Skip Pattern Analysis**: Understand which songs and artists you tend to skip
- **Music Personality Profiling**: Audio feature analysis to understand your preferences

### Backup & Migration
- **Complete Library Backup**: Export only your created playlists, followed artists, and liked songs
- **Multiple Export Formats**: JSON, CSV, Apple Music, and YouTube Music compatible formats  
- **Metadata Preservation**: Include ISRC codes, Spotify URLs, and detailed track information
- **Smart Filtering**: Only backs up user-created content, not collaborative or followed playlists

## 📋 Requirements

- **Python 3.6+** (auto-detected and managed)
- **Spotify Developer Account** (free at [developer.spotify.com](https://developer.spotify.com/dashboard/))
- **Last.fm API Key** (optional, for enhanced recommendations)

## 📱 Menu Overview

```
PLAYLIST MANAGEMENT:
1. Convert local playlists to Spotify playlists
2. Add all songs from your created playlists to Liked Songs (with Christmas filtering)
3. Remove Christmas songs from Liked Songs
4. Remove duplicate songs from Liked Songs
5. Identify frequently skipped songs in your library

ARTIST MANAGEMENT:
6. Follow all artists in your created playlists
7. Find Artists to Follow That You Probably Like
8. Remove followed artists that you probably don't like

ANALYTICS & INSIGHTS:
9. Enhanced analytics & music insights (with comprehensive progress tracking)
10. Backup & export your music library (user-created content only)

SYSTEM MANAGEMENT:
11. Manage caches (with deprecated cache cleanup)
12. Manage API credentials
13. Reset environment (automated with real-time feedback)
14. Exit
```

## 🔧 Advanced Features

### Intelligent Playlist Conversion
- **Multiple format support**: M3U, M3U8, PLS playlist files
- **Advanced fuzzy matching**: Smart track identification across different metadata formats
- **Batch processing**: Efficiently handle dozens of playlists simultaneously
- **Interactive confirmation**: Review matches before adding to avoid false positives
- **Rate limiting**: Respects Spotify API limits for reliable operation

### Smart Artist Following
- **Low-follower detection**: Prompts before following artists with ≤10 followers
- **Bulk operations**: Process hundreds of artists efficiently
- **Auto-follow suggestions**: Automatically suggest artists based on liked songs frequency
- **Manual review options**: Full control over which artists to follow

### Music Analytics Dashboard
- **Audio feature analysis**: Danceability, energy, valence, acousticness profiling
- **Genre distribution**: Comprehensive breakdown of your music preferences
- **Geographic diversity**: Artist origin mapping and regional music discovery
- **Temporal analysis**: Track how your taste evolves over time
- **Listening pattern insights**: Understand your music consumption habits

### Enhanced Discovery Engine
- **Multi-source recommendations**: Combines Spotify, Last.fm, and MusicBrainz data
- **Intelligent scoring**: Weighted recommendations based on your listening history
- **Geographic exploration**: Discover artists from underrepresented regions
- **Genre diversification**: Expand beyond your current preferences

## ⚙️ Configuration

### Environment Variables
```bash
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
export SPOTIFY_REDIRECT_URI="http://127.0.0.1:8888/callback"
export LASTFM_API_KEY="your_lastfm_key"
```

### Configuration Directory
User settings and cache stored in: `~/.spotify-tools/`
- `credentials.json`: API credentials
- `cache/`: Cached API responses
- `backups/`: Library backups

## 🎯 Individual Scripts

Each feature can be run independently:

- `spotify_follow_artists.py`: Follow playlist artists
- `spotify_like_songs.py`: Like playlist songs (with auto-follow)
- `spotify_similar_artists.py`: Enhanced artist discovery
- `spotify_analytics.py`: Music analytics and insights
- `spotify_backup.py`: Library backup and export
- `spotify_playlist_converter.py`: Convert local playlists
- `spotify_cleanup_artists.py`: Artist cleanup with bulk filtering
- `spotify_remove_christmas.py`: Remove Christmas songs
- `spotify_remove_duplicates.py`: Remove duplicate songs
- `spotify_identify_skipped.py`: Identify frequently skipped songs
- `spotify_playlist_manager.py`: Advanced playlist management

## 🧪 Testing

Run the comprehensive test suite:
```bash
python3 run_tests.py
```

Individual test files are available in the `tests/` directory.

## 🔒 Security Features

- **Secure credential storage**: No hardcoded API keys
- **Comprehensive .gitignore**: Prevents accidental credential commits
- **Safe subprocess usage**: Only for legitimate environment management
- **Input validation**: Protection against injection attacks
- **Rate limiting**: Prevents API abuse

## 🐛 Troubleshooting

### Authentication Issues
- Verify redirect URI matches exactly: `http://127.0.0.1:8888/callback`
- Use menu option 12 to re-enter credentials
- Check that your Spotify app has the correct scopes

### Performance Issues
- Use menu option 11 to manage caches if experiencing stale data
- Adjust batch sizes in `constants.py` for different network conditions
- The system includes intelligent rate limiting to prevent API errors

### Environment Issues
- Use menu option 13 to reset the Python environment
- Ensure Python 3.6+ is installed
- Check that all dependencies are properly installed

### Common Error Solutions
- **Module not found**: Run environment reset (option 13)
- **API rate limits**: Wait a few minutes and retry
- **Authentication expired**: Re-run credential setup (option 12)
- **Cache corruption**: Clear caches (option 11)

## 📊 Analytics Insights

The analytics system provides deep insights into your music taste:

- **Music Personality Classification**: Energy levels, mood preferences, style analysis
- **Diversity Metrics**: Geographic and genre distribution statistics
- **Listening Behavior**: Peak listening times, session patterns, skip analysis
- **Recommendation Quality**: Track success rate of followed artists and liked songs
- **Library Evolution**: How your taste changes over time

## 🔄 Data Export Options

Multiple export formats for different use cases:

- **JSON**: Complete structured data for developers
- **CSV**: Spreadsheet-compatible for analysis
- **Apple Music**: Text format for playlist transfer
- **YouTube Music**: CSV format for Google services
- **M3U8**: Standard playlist format for media players

## 🌟 Recent Updates

### Major Enhancements
- **Caching System Overhaul**: Standardized cache keys across all scripts for better performance and data consistency
- **Analytics Improvements**: Fixed progress bars, eliminated duplicate messages, enhanced rate limiting in music analytics
- **Backup System Redesign**: Modified to only backup user-created content with progress bars and cached data usage
- **Christmas Filtering**: Added optional Christmas song filtering to playlist liking functionality
- **Environment Reset Automation**: Enhanced reset with real-time output and improved error handling
- **Cache Management**: Added cleanup for deprecated cache files and better cache organization
- **Comprehensive Testing**: Full test suite covering imports, syntax validation, and core functionality

### Performance & Stability
- Enhanced fuzzy matching for playlist conversion
- Added auto-follow functionality based on liked songs
- Improved security with comprehensive auditing
- Centralized configuration management
- Enhanced error handling and user feedback
- Better rate limiting across all API operations

## 📝 Development

This project uses a modular architecture with:

- **Centralized utilities**: Shared functions in `spotify_utils.py`
- **Configuration management**: Settings in `constants.py`
- **Caching system**: Intelligent API response caching with consistent naming
- **Error handling**: Comprehensive error recovery
- **Testing framework**: Unit and integration tests (`python3 run_tests.py`)
- **Documentation**: Comprehensive guides in `CLAUDE.md` for development

### Running Tests
```bash
source venv/bin/activate
python3 run_tests.py
```

### Architecture Highlights
- Consistent cache key naming across all scripts
- Progress bars for all long-running operations  
- Rate limiting with exponential backoff
- User-created content filtering in backup operations
- Comprehensive error messages and user feedback

## 🤝 Contributing

Contributions are welcome! The codebase follows these principles:

- **Security first**: No hardcoded credentials or unsafe operations
- **User-friendly**: Clear feedback and confirmation prompts
- **Robust error handling**: Graceful degradation and recovery
- **Comprehensive testing**: Verify all functionality
- **Documentation**: Clear code comments and user guides

## 📄 License

This project is licensed under the MIT License. See the LICENSE file for details.

---

*Matt Y's Spotify Tools - Comprehensive music library management and discovery*