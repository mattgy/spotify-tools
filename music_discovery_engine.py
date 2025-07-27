#!/usr/bin/env python3
"""
Comprehensive music discovery engine combining Spotify, Last.fm, and MusicBrainz.
"""

import os
import sys
import time
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from cache_utils import save_to_cache, load_from_cache
from constants import CACHE_EXPIRATION
from lastfm_integration import lastfm_client
from musicbrainz_integration import mb_client
from spotify_utils import create_spotify_client, fetch_followed_artists
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

class MusicDiscoveryEngine:
    """Comprehensive music discovery engine."""
    
    def __init__(self):
        self.spotify_scopes = [
            "user-follow-read",
            "user-library-read", 
            "user-top-read",
            "playlist-read-private"
        ]
        self.sp = None
        self.cache_expiration = CACHE_EXPIRATION.get('long', 7 * 24 * 60 * 60)
    
    def _setup_spotify(self):
        """Set up Spotify client if not already done."""
        if self.sp is None:
            self.sp = create_spotify_client(self.spotify_scopes, "discovery")
    
    def discover_by_geographic_expansion(self, target_countries: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """
        Discover artists from specific countries to expand geographic diversity.
        
        Args:
            target_countries: List of countries to explore
            limit: Maximum number of artists per country
            
        Returns:
            List of discovered artists with metadata
        """
        discovered_artists = []
        
        print(f"{Fore.CYAN}🌍 Discovering artists from {len(target_countries)} countries...")
        progress_bar = create_progress_bar(len(target_countries), "Exploring countries", "country")
        
        for country in target_countries:
            # Get artists from MusicBrainz
            mb_artists = mb_client.search_by_country(country, limit)
            
            for artist in mb_artists[:limit//2]:  # Take half from MusicBrainz
                discovered_artists.append({
                    'name': artist['name'],
                    'country': country,
                    'source': 'MusicBrainz',
                    'mbid': artist.get('mbid'),
                    'score': artist.get('score', 0),
                    'type': artist.get('type'),
                    'begin_date': artist.get('begin_date')
                })
            
            # Search Last.fm for popular artists from this country
            if lastfm_client.api_key:
                # Use country-specific genres/tags to find artists
                country_queries = [country, f"{country} music", f"{country} artists"]
                
                for query in country_queries:
                    lastfm_artists = lastfm_client.search_artists(query, 10)
                    
                    for artist in lastfm_artists[:5]:
                        if not any(d['name'].lower() == artist['name'].lower() for d in discovered_artists):
                            discovered_artists.append({
                                'name': artist['name'],
                                'country': country,
                                'source': 'Last.fm',
                                'mbid': artist.get('mbid'),
                                'listeners': artist.get('listeners', 0),
                                'lastfm_url': artist.get('url'),
                                'image': artist.get('image')
                            })
                    
                    time.sleep(0.3)  # Rate limiting
            
            update_progress_bar(progress_bar, 1)
        
        close_progress_bar(progress_bar)
        
        # Sort by relevance/popularity
        discovered_artists.sort(key=lambda x: x.get('listeners', x.get('score', 0)), reverse=True)
        
        return discovered_artists[:limit]
    
    def discover_by_genre_expansion(self, known_genres: List[str], limit: int = 100) -> List[Dict[str, Any]]:
        """
        Discover new genres and artists based on user's existing preferences.
        
        Args:
            known_genres: List of genres the user already likes
            limit: Maximum number of artists to discover
            
        Returns:
            List of discovered artists from related genres
        """
        discovered_artists = []
        
        print(f"{Fore.CYAN}🎭 Discovering artists from {len(known_genres)} related genres...")
        
        # Get related genres from Last.fm
        if lastfm_client.api_key:
            new_genres = lastfm_client.discover_new_genres(known_genres, 20)
            
            progress_bar = create_progress_bar(len(new_genres), "Exploring genres", "genre")
            
            for genre in new_genres:
                # Get top artists for this genre from Last.fm
                genre_artists = lastfm_client.get_top_artists_by_tag(genre, 10)
                
                for artist in genre_artists:
                    if not any(d['name'].lower() == artist['name'].lower() for d in discovered_artists):
                        discovered_artists.append({
                            'name': artist['name'],
                            'genre': genre,
                            'source': 'Last.fm Genre',
                            'mbid': artist.get('mbid'),
                            'listeners': artist.get('listeners', 0),
                            'playcount': artist.get('playcount', 0),
                            'rank': artist.get('rank', 999),
                            'lastfm_url': artist.get('url'),
                            'image': artist.get('image')
                        })
                        
                        if len(discovered_artists) >= limit:
                            break
                
                update_progress_bar(progress_bar, 1)
                
                if len(discovered_artists) >= limit:
                    break
            
            close_progress_bar(progress_bar)
        
        # Sort by rank and listeners
        discovered_artists.sort(key=lambda x: (x.get('rank', 999), -x.get('listeners', 0)))
        
        return discovered_artists[:limit]
    
    def discover_by_similarity_chains(self, seed_artists: List[str], depth: int = 3, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Discover artists through similarity chains (artist -> similar -> similar to similar).
        
        Args:
            seed_artists: List of artist names to start from
            depth: How many similarity levels to explore
            limit: Maximum number of artists to discover
            
        Returns:
            List of discovered artists through similarity chains
        """
        discovered = {}
        explored = set(a.lower() for a in seed_artists)
        
        print(f"{Fore.CYAN}🔗 Following similarity chains from {len(seed_artists)} artists (depth: {depth})...")
        
        current_level = seed_artists.copy()
        
        for level in range(depth):
            next_level = []
            
            progress_bar = create_progress_bar(len(current_level), f"Level {level + 1}", "artist")
            
            for artist in current_level:
                if artist.lower() in explored:
                    update_progress_bar(progress_bar, 1)
                    continue
                
                explored.add(artist.lower())
                
                # Get similar artists from Last.fm
                if lastfm_client.api_key:
                    similar_lastfm = lastfm_client.get_similar_artists(artist, 10)
                    
                    for similar in similar_lastfm:
                        similar_name = similar['name']
                        if similar_name.lower() not in explored:
                            if similar_name not in discovered:
                                discovered[similar_name] = {
                                    'name': similar_name,
                                    'source_chain': f"{artist} (Last.fm)",
                                    'similarity_level': level + 1,
                                    'match_score': similar.get('match', 0),
                                    'mbid': similar.get('mbid'),
                                    'lastfm_url': similar.get('url'),
                                    'image': similar.get('image')
                                }
                            
                            if level < depth - 1:  # Add to next level if not at max depth
                                next_level.append(similar_name)
                
                # Get similar artists from MusicBrainz
                mb_similar = mb_client.get_similar_artists(artist)
                
                for similar in mb_similar:
                    similar_name = similar['name']
                    if similar_name.lower() not in explored:
                        if similar_name not in discovered:
                            discovered[similar_name] = {
                                'name': similar_name,
                                'source_chain': f"{artist} (MusicBrainz)",
                                'similarity_level': level + 1,
                                'confidence': similar.get('confidence', 0),
                                'relationship': similar.get('source', ''),
                                'mbid': similar.get('mbid')
                            }
                        
                        if level < depth - 1:
                            next_level.append(similar_name)
                
                update_progress_bar(progress_bar, 1)
                time.sleep(0.2)  # Rate limiting
            
            close_progress_bar(progress_bar)
            
            current_level = list(set(next_level[:20]))  # Limit and deduplicate for next level
            
            if not current_level:
                break
        
        # Convert to list and sort by relevance
        result = list(discovered.values())
        result.sort(key=lambda x: (
            x.get('similarity_level', 0),
            -x.get('match_score', x.get('confidence', 0))
        ))
        
        return result[:limit]
    
    def discover_underrepresented_regions(self, current_countries: List[str], limit: int = 30) -> List[Dict[str, Any]]:
        """
        Discover artists from countries not well represented in user's library.
        
        Args:
            current_countries: Countries already represented in user's music
            limit: Maximum number of artists to discover
            
        Returns:
            List of artists from underrepresented regions
        """
        # List of interesting countries for music discovery
        diverse_countries = [
            'Iceland', 'Estonia', 'Latvia', 'Lithuania', 'Slovenia', 'Croatia',
            'Serbia', 'Bulgaria', 'Romania', 'Hungary', 'Czech Republic',
            'Mali', 'Senegal', 'Nigeria', 'Ghana', 'South Africa', 'Kenya',
            'Mongolia', 'Kazakhstan', 'Georgia', 'Armenia', 'Azerbaijan',
            'Lebanon', 'Jordan', 'Israel', 'Iran', 'Turkey', 'Greece',
            'Portugal', 'Belgium', 'Luxembourg', 'Austria', 'Switzerland',
            'Uruguay', 'Paraguay', 'Bolivia', 'Ecuador', 'Peru', 'Colombia',
            'Venezuela', 'Cuba', 'Jamaica', 'Trinidad and Tobago',
            'Indonesia', 'Malaysia', 'Philippines', 'Vietnam', 'Thailand',
            'Myanmar', 'Cambodia', 'Laos', 'Nepal', 'Bangladesh', 'Sri Lanka'
        ]
        
        # Filter out countries already well represented
        current_set = set(c.lower() for c in current_countries)
        underrepresented = [c for c in diverse_countries if c.lower() not in current_set]
        
        return self.discover_by_geographic_expansion(underrepresented[:10], limit)
    
    def analyze_user_music_profile(self) -> Dict[str, Any]:
        """
        Analyze user's current music profile to inform discovery.
        
        Returns:
            Dictionary with user's music profile analysis
        """
        self._setup_spotify()
        
        print(f"{Fore.CYAN}📊 Analyzing your music profile...")
        
        # Get user's followed artists
        followed_artists = fetch_followed_artists(
            self.sp,
            show_progress=True,
            cache_key="followed_artists",
            cache_expiration=self.cache_expiration
        )
        
        if not followed_artists:
            return {'error': 'No followed artists found'}
        
        # Analyze genres
        all_genres = []
        countries = []
        
        print("🔍 Enriching artist data...")
        sample_size = min(50, len(followed_artists))
        progress_bar = create_progress_bar(sample_size, "Analyzing artists", "artist")
        
        for artist in followed_artists[:sample_size]:
            # Extract Spotify genres
            all_genres.extend(artist.get('genres', []))
            
            # Get country information from MusicBrainz
            enriched = mb_client.enrich_artist_data(artist)
            mb_data = enriched.get('musicbrainz', {})
            if mb_data.get('country'):
                countries.append(mb_data['country'])
            
            update_progress_bar(progress_bar, 1)
        
        close_progress_bar(progress_bar)
        
        # Analyze patterns
        genre_counts = Counter(all_genres)
        country_counts = Counter(countries)
        
        profile = {
            'total_artists': len(followed_artists),
            'analyzed_artists': sample_size,
            'top_genres': dict(genre_counts.most_common(20)),
            'genre_diversity': len(genre_counts),
            'top_countries': dict(country_counts.most_common(10)),
            'geographic_diversity': len(country_counts),
            'underrepresented_regions': len(set(countries)) < 10,
            'genre_concentration': genre_counts.most_common(1)[0][1] / len(all_genres) if all_genres else 0
        }
        
        return profile
    
    def generate_discovery_recommendations(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate comprehensive discovery recommendations based on user profile.
        
        Args:
            profile: User's music profile analysis
            
        Returns:
            Dictionary with various types of recommendations
        """
        recommendations = {
            'geographic_expansion': [],
            'genre_exploration': [],
            'similarity_chains': [],
            'summary': {}
        }
        
        if 'error' in profile:
            return recommendations
        
        print(f"{Fore.CYAN}🎯 Generating personalized recommendations...")
        
        # Geographic expansion recommendations
        if profile.get('underrepresented_regions', True):
            current_countries = list(profile.get('top_countries', {}).keys())
            geographic_recs = self.discover_underrepresented_regions(current_countries, 20)
            recommendations['geographic_expansion'] = geographic_recs
        
        # Genre exploration recommendations
        current_genres = list(profile.get('top_genres', {}).keys())
        if current_genres:
            genre_recs = self.discover_by_genre_expansion(current_genres, 30)
            recommendations['genre_exploration'] = genre_recs
        
        # Similarity chain recommendations
        top_artist_names = [artist['name'] for artist in 
                           fetch_followed_artists(self.sp, show_progress=False)[:10]]
        if top_artist_names:
            similarity_recs = self.discover_by_similarity_chains(top_artist_names, depth=2, limit=25)
            recommendations['similarity_chains'] = similarity_recs
        
        # Generate summary
        recommendations['summary'] = {
            'total_recommendations': (
                len(recommendations['geographic_expansion']) +
                len(recommendations['genre_exploration']) +
                len(recommendations['similarity_chains'])
            ),
            'geographic_countries': len(set(
                r.get('country', '') for r in recommendations['geographic_expansion']
            )),
            'new_genres': len(set(
                r.get('genre', '') for r in recommendations['genre_exploration']
            )),
            'discovery_chains': len(recommendations['similarity_chains']),
            'profile_diversity_score': profile.get('geographic_diversity', 0) * 10 + profile.get('genre_diversity', 0)
        }
        
        return recommendations
    
    def export_recommendations(self, recommendations: Dict[str, Any], output_file: str = None) -> str:
        """
        Export recommendations to a file.
        
        Args:
            recommendations: Generated recommendations
            output_file: Output file path (optional)
            
        Returns:
            Path to the exported file
        """
        if not output_file:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(script_dir, f"music_discovery_recommendations_{timestamp}.json")
        
        import json
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(recommendations, f, indent=2, ensure_ascii=False)
        
        return output_file

def main():
    """Main function for music discovery engine."""
    print(f"{Fore.CYAN}{Style.BRIGHT}🎵 Comprehensive Music Discovery Engine")
    print("=" * 60)
    
    engine = MusicDiscoveryEngine()
    
    while True:
        print(f"\n{Fore.WHITE}Discovery Options:")
        print("1. Full discovery analysis & recommendations")
        print("2. Geographic exploration (specific countries)")
        print("3. Genre expansion discovery")
        print("4. Similarity chain discovery")
        print("5. Analyze music profile only")
        print("6. Exit")
        
        choice = input(f"\n{Fore.CYAN}Enter your choice (1-6): ").strip()
        
        if choice == "1":
            print(f"\n{Fore.YELLOW}🔍 Running comprehensive discovery analysis...")
            profile = engine.analyze_user_music_profile()
            
            if 'error' not in profile:
                print(f"\n{Fore.GREEN}✅ Profile Analysis Complete!")
                print(f"📊 {profile['total_artists']} total artists")
                print(f"🎭 {profile['genre_diversity']} unique genres")
                print(f"🌍 {profile['geographic_diversity']} countries represented")
                
                recommendations = engine.generate_discovery_recommendations(profile)
                
                summary = recommendations['summary']
                print(f"\n{Fore.GREEN}🎯 Discovery Recommendations Generated!")
                print(f"📈 {summary['total_recommendations']} total recommendations")
                print(f"🌍 {summary['geographic_countries']} new countries to explore")
                print(f"🎭 {summary['new_genres']} new genres discovered")
                print(f"🔗 {summary['discovery_chains']} similarity-based recommendations")
                
                # Export recommendations
                export_file = engine.export_recommendations(recommendations)
                print(f"\n{Fore.BLUE}💾 Recommendations saved to: {export_file}")
            else:
                print(f"{Fore.RED}❌ Error analyzing profile: {profile['error']}")
        
        elif choice == "2":
            countries = input("Enter countries to explore (comma-separated): ").strip()
            if countries:
                country_list = [c.strip() for c in countries.split(',')]
                artists = engine.discover_by_geographic_expansion(country_list, 20)
                
                print(f"\n{Fore.GREEN}🌍 Found {len(artists)} artists from specified countries:")
                for artist in artists[:10]:
                    print(f"  • {artist['name']} ({artist['country']}) - {artist['source']}")
        
        elif choice == "3":
            genres = input("Enter genres you like (comma-separated): ").strip()
            if genres:
                genre_list = [g.strip() for g in genres.split(',')]
                artists = engine.discover_by_genre_expansion(genre_list, 30)
                
                print(f"\n{Fore.GREEN}🎭 Found {len(artists)} artists from related genres:")
                for artist in artists[:10]:
                    print(f"  • {artist['name']} ({artist['genre']}) - {artist.get('listeners', 0):,} listeners")
        
        elif choice == "4":
            artists = input("Enter seed artists (comma-separated): ").strip()
            if artists:
                artist_list = [a.strip() for a in artists.split(',')]
                discovered = engine.discover_by_similarity_chains(artist_list, depth=2, limit=20)
                
                print(f"\n{Fore.GREEN}🔗 Found {len(discovered)} artists through similarity chains:")
                for artist in discovered[:10]:
                    print(f"  • {artist['name']} via {artist['source_chain']}")
        
        elif choice == "5":
            profile = engine.analyze_user_music_profile()
            
            if 'error' not in profile:
                print(f"\n{Fore.GREEN}📊 Your Music Profile:")
                print(f"Total Artists: {profile['total_artists']}")
                print(f"Genre Diversity: {profile['genre_diversity']} unique genres")
                print(f"Geographic Diversity: {profile['geographic_diversity']} countries")
                print(f"Genre Concentration: {profile['genre_concentration']:.1%}")
                
                print(f"\nTop Genres:")
                for genre, count in list(profile['top_genres'].items())[:10]:
                    print(f"  • {genre}: {count} artists")
                
                print(f"\nTop Countries:")
                for country, count in list(profile['top_countries'].items())[:10]:
                    print(f"  • {country}: {count} artists")
            else:
                print(f"{Fore.RED}❌ Error: {profile['error']}")
        
        elif choice == "6":
            print(f"{Fore.GREEN}🎵 Happy discovering!")
            break
        
        else:
            print(f"{Fore.RED}Invalid choice. Please try again.")

if __name__ == "__main__":
    main()