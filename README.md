# Matt Y's Spotify Tools

A comprehensive collection of utilities for managing your Spotify account, discovering new music, and analyzing your listening habits with advanced features and integrations.

## Features

- **Follow Artists**: Follow all artists from your playlists
- **Like Songs**: Add all songs from your playlists to your Liked Songs  
- **Advanced Music Discovery**: Enhanced recommendation engine using MusicBrainz and Last.fm APIs
- **Find Concerts**: Find upcoming concerts for artists you follow
- **Enhanced Analytics**: Comprehensive music taste analysis and listening pattern insights
- **Playlist Converter**: Convert local playlist files to Spotify playlists
- **Artist Cleanup**: Remove followed artists you probably don't like
- **Backup & Export**: Complete library backup for migration and archival

## New Features

### 🎵 Advanced Music Discovery
- **Multi-source recommendations** combining Spotify, Last.fm, and MusicBrainz data
- **Enhanced metadata** with artist origins, relationships, and detailed tags
- **Intelligent scoring** based on your listening patterns and preferences
- **Genre and geographic diversity analysis**

### 📊 Enhanced Analytics  
- **Comprehensive music taste profiling** with audio feature analysis
- **Listening pattern tracking** over different time periods
- **Music personality classification** (energy levels, mood preferences, etc.)
- **Geographic and temporal diversity insights**
- **Visual charts and reports** with exportable data

### 💾 Backup & Migration Tools
- **Complete library backup** including playlists, followed artists, and liked songs
- **Portable data formats** (JSON, CSV) for cross-platform compatibility  
- **Metadata preservation** with ISRC codes and Spotify URLs
- **Human-readable reports** with detailed statistics

### ⚙️ Configuration Management
- **Flexible configuration system** with environment variable support
- **Configurable rate limiting** and batch processing
- **Advanced caching** with automatic cleanup and management
- **Comprehensive test suite** for reliability

## Setup

### Prerequisites

- Python 3.6 or higher
- Spotify Developer Account
- Last.fm API Key (optional, for enhanced recommendations)
- MusicBrainz integration (automatic, no API key required)

### Installation

1. Clone or download this repository
2. Run the main script:
   ```
   ./spotify_run.py
   ```
3. The script will set up a virtual environment and install all required dependencies

### Spotify API Setup

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Create a new application
3. Set the redirect URI to `http://127.0.0.1:8888/callback`
4. Note your Client ID and Client Secret

### API Keys

- **Last.fm API Key**: Get one from [Last.fm API](https://www.last.fm/api/account/create) (optional)
- **MusicBrainz**: No API key required - automatic integration

## Usage

Run the main script and select an option from the menu:

```
./spotify_run.py
```

### Menu Options

1. **Follow Artists** - Follow all artists from your created playlists
2. **Like Songs** - Add all songs from your created playlists to Liked Songs
3. **Advanced Music Discovery** - Enhanced recommendations using multiple data sources
4. **Find Concerts** - Find upcoming concerts for artists you follow
5. **Enhanced Analytics** - Comprehensive music insights and visualizations
6. **Convert Playlists** - Convert local playlist files to Spotify playlists
7. **Artist Cleanup** - Remove followed artists you probably don't like
8. **Backup & Export** - Create complete library backups
9. **Manage Caches** - Clear and manage cached data
10. **Manage Credentials** - Set up and update API credentials
11. **Reset Environment** - Reinstall dependencies

### Credential Management

The application includes intelligent credential management:

1. **Manage API Credentials**: Choose option 10 from the main menu to save or update your API credentials
2. **Environment Variables**: Credentials can be set via environment variables
3. **Secure Storage**: Credentials are stored in `~/.spotify-tools/` and automatically loaded

### Testing

Run the comprehensive test suite:

```
python3 run_tests.py
```

## Enhanced Analytics Dashboard

The analytics system provides detailed insights into your music taste:

1. **Music Personality Analysis**: Understand your preferences for energy, mood, and style
2. **Genre Distribution**: See your most listened-to genres with visual charts
3. **Geographic Diversity**: Discover artists from different countries and regions
4. **Temporal Analysis**: Track how your taste evolves over time
5. **Audio Feature Profiling**: Detailed analysis of danceability, acousticness, valence, etc.

## Advanced Configuration

### Environment Variables

```bash
export SPOTIFY_TOOLS_CACHE_DAYS=7
export SPOTIFY_TOOLS_API_DELAY=0.1
export SPOTIFY_TOOLS_BATCH_SIZE=50
export SPOTIFY_TOOLS_PROGRESS_BAR=true
```

### Configuration File

Create `~/.spotify-tools/config.json` for advanced settings:

```json
{
  "cache_expiration_days": 7,
  "api_delay_seconds": 0.1,
  "batch_size_artists": 50,
  "confidence_threshold": 0.8,
  "similar_artist_limit": 20
}
```

## Individual Scripts

You can also run each script independently:

- `spotify_follow_artists.py`: Follow all artists from your playlists
- `spotify_like_songs.py`: Add all songs from your playlists to your Liked Songs
- `spotify_similar_artists.py`: Find and follow similar artists with enhanced discovery
- `spotify_find_concerts.py`: Find upcoming concerts
- `spotify_analytics.py`: Generate comprehensive analytics and insights
- `spotify_backup.py`: Create complete library backups
- `spotify_playlist_converter.py`: Convert local playlists to Spotify playlists
- `spotify_cleanup_artists.py`: Remove followed artists that you probably don't like

## Troubleshooting

- **Authentication Issues**: Make sure your redirect URI in the Spotify Developer Dashboard matches exactly: `http://127.0.0.1:8888/callback`
- **API Rate Limits**: The scripts include intelligent delays to avoid hitting rate limits, but you may need to wait if you encounter limit errors
- **Missing Dependencies**: Use the "Reset environment" option in the main menu if you encounter module import errors
- **Credential Problems**: If you're having authentication issues, try using option 10 to re-enter your credentials
- **Cache Issues**: If you're getting stale data, use option 9 to manage and clear caches

## Features

This project provides a comprehensive set of tools for managing and analyzing your Spotify music library, with robust error handling, caching, and user-friendly interfaces.