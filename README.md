# Matt Y's Spotify Tools

A collection of utilities for managing your Spotify account, finding similar artists, discovering concerts, and analyzing your listening habits.

> **Note:** This project was created entirely with Amazon Q CLI, an AI assistant for developers.

## Features

- **Follow Artists**: Follow all artists from your playlists
- **Like Songs**: Add all songs from your playlists to your Liked Songs
- **Find Similar Artists**: Discover and follow artists similar to those you already follow
- **Find Concerts**: Find upcoming concerts for artists you follow
- **Listening Statistics**: Analyze your listening habits and music preferences
- **Music Dashboard**: Interactive web dashboard to visualize your music taste
- **Playlist Converter**: Convert local playlist files to Spotify playlists

## Setup

### Prerequisites

- Python 3.6 or higher
- Spotify Developer Account
- Last.fm API Key (for similar artists feature)
- Songkick API Key (for concert feature)

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

- **Last.fm API Key**: Get one from [Last.fm API](https://www.last.fm/api/account/create)
- **Songkick API Key**: Request one from [Songkick API](https://www.songkick.com/api_key_requests/new)

## Usage

Run the main script and select an option from the menu:

```
./spotify_run.py
```

### Credential Management

The main script includes credential management:

1. **Manage API Credentials**: Choose option 10 from the main menu to save or update your API credentials
2. **Reset Environment**: Choose option 11 to reinstall dependencies

Credentials are stored in `~/.spotify-tools/` and automatically loaded when you run the scripts.

## Music Dashboard

The music dashboard provides visualizations of your listening habits:

1. **View Dashboard & Statistics**: Choose option 5 from the main menu to generate statistics and view the dashboard
2. **Deploy to AWS**: Choose option 6 to prepare the dashboard for AWS S3/CloudFront deployment

### AWS Deployment

To deploy the dashboard to AWS:

1. Create an S3 bucket (e.g., 'my-spotify-dashboard')
2. Enable static website hosting on the bucket
3. Upload the contents of the deploy directory to your S3 bucket:
   ```
   aws s3 sync deploy/ s3://my-spotify-dashboard --acl public-read
   ```
4. (Optional) Set up CloudFront for faster delivery:
   - Create a CloudFront distribution pointing to your S3 bucket
   - Use the CloudFront domain to access your dashboard

## Individual Scripts

You can also run each script individually:

- `spotify_follow_artists.py`: Follow all artists from your playlists
- `spotify_like_songs.py`: Add all songs from your playlists to your Liked Songs
- `spotify_similar_artists.py`: Find and follow similar artists
- `spotify_find_concerts.py`: Find upcoming concerts
- `spotify_stats.py`: Generate listening statistics
- `spotify_dashboard.py`: Launch the music dashboard
- `spotify_playlist_converter.py`: Convert local playlists to Spotify playlists
- `spotify_cleanup_artists.py`: Remove followed artists that you probably don't like

## Troubleshooting

- **Authentication Issues**: Make sure your redirect URI in the Spotify Developer Dashboard matches exactly: `http://127.0.0.1:8888/callback`
- **API Rate Limits**: The scripts include delays to avoid hitting rate limits, but you may need to wait if you encounter limit errors
- **Missing Dependencies**: Use the "Reset environment" option in the main menu if you encounter module import errors
- **Credential Problems**: If you're having authentication issues, try using option 10 to re-enter your credentials
- **Cache Issues**: If you're getting stale data, use option 9 to manage and clear caches

## Created with Amazon Q CLI

This project was developed entirely using Amazon Q CLI, an AI assistant for developers. Amazon Q CLI helped with:

- Writing and structuring the Python code
- Implementing the Spotify API integration
- Creating the user interface and menu system
- Designing the dashboard visualization
- Troubleshooting and debugging issues
- Optimizing the code for performance and reliability

Amazon Q CLI provided guidance on best practices, helped implement complex features, and ensured the code was well-documented and maintainable.
