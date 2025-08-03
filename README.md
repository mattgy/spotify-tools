# Matt Y's Spotify Tools

A comprehensive collection of Python utilities for managing your Spotify account, discovering music, and analyzing listening habits. Features a clean menu-driven interface with advanced automation and music discovery capabilities.

## 🚀 Quick Start

**3 simple steps:**

1. **Clone and run**:
   ```bash
   git clone https://github.com/mattgy/spotify-tools.git
   cd spotify-tools
   ./spotify_run.py
   ```

2. **Set up Spotify credentials** (one-time):
   - Create a free app at [developer.spotify.com](https://developer.spotify.com/dashboard/)  
   - Set redirect URI to: `http://127.0.0.1:8888/callback`
   - Use menu option 10 to enter your Client ID and Client Secret

3. **Start using the tools!** Everything else is automated.

## 🎵 What It Does

### Playlist Tools
- **Convert local playlists** (M3U, text files) to Spotify with AI-powered matching
- **Mass-like songs** from your playlists with optional Christmas filtering  
- **Remove Christmas songs** from your library automatically
- **Manage small playlists** - find and delete playlists with few tracks

### Artist Tools  
- **Auto-follow artists** from your playlists with smart filtering
- **Discover new artists** using multi-source recommendations
- **Clean up followed artists** you don't actually listen to

### Backup & Export
- **Complete library backup** in multiple formats (JSON, CSV, M3U8)
- **Smart filtering** - only backs up your created content, not followed playlists

## 📋 Requirements

- **Python 3.6+** (auto-managed)
- **Free Spotify Developer Account** ([get one here](https://developer.spotify.com/dashboard/))
- **Optional**: Last.fm API key for enhanced recommendations

## ⚙️ Configuration

All settings stored in `~/.spotify-tools/`:
- `credentials.json` - API keys (managed via menu option 10)
- `cache/` - Cached data for faster performance
- `backups/` - Your exported library data

Environment variables (optional):
```bash
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret" 
export LASTFM_API_KEY="your_lastfm_key"
```

## 🔧 Advanced Features

- **AI-assisted track matching** using Gemini, ChatGPT, Claude, or Perplexity
- **Session memory** - remembers your decisions between runs
- **Smart caching** with automatic corruption detection and recovery
- **Bulk operations** with progress tracking
- **Rate limiting** to respect API limits
- **Comprehensive error handling** with graceful recovery

## 🧪 Testing

Run the test suite:
```bash
./venv/bin/python run_tests.py
```

## 🛠️ Individual Scripts

Each tool can run independently:
- `spotify_playlist_converter.py` - Convert local playlists
- `spotify_like_songs.py` - Mass-like songs from playlists
- `spotify_follow_artists.py` - Follow playlist artists
- `spotify_similar_artists.py` - Discover new artists
- `spotify_backup.py` - Export your library
- `spotify_remove_christmas.py` - Remove holiday music
- `spotify_playlist_size_manager.py` - Manage small playlists
- `spotify_cleanup_artists.py` - Clean up followed artists

## 🐛 Troubleshooting

**Authentication issues?**
- Check redirect URI: `http://127.0.0.1:8888/callback` (exact match)
- Re-enter credentials via menu option 10

**Performance issues?**
- Clear caches via menu option 9
- Reset environment via menu option 11

**Import errors?** 
- Run `./spotify_run.py` (handles all dependencies automatically)

## 🔒 Security

- No hardcoded API keys
- Secure credential storage  
- Comprehensive input validation
- Safe API rate limiting
- Protected against common vulnerabilities

## 📄 License

MIT License - see LICENSE file for details.

---

*Comprehensive Spotify library management and music discovery tools*