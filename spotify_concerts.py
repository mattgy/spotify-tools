#!/usr/bin/env python3
"""
Find upcoming concerts for all followed Spotify artists.

Queries Bandsintown and Ticketmaster in parallel (20 workers), caches
per-artist results for 7 days so reruns are instant, and ranks shows by
Last.fm play count so the most-listened-to artists appear first.

Usage (interactive):
  python3 spotify_concerts.py

Usage (scheduled digest):
  python3 spotify_concerts.py --location "New York" --days 90 --output /tmp/digest.html
"""

import os
import sys
import datetime
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape
from urllib.parse import quote

import requests
import colorama
from colorama import Fore, Style

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from credentials_manager import get_credentials
from cache_utils import save_to_cache, load_from_cache
from print_utils import (
    print_success, print_error, print_warning, print_info,
    print_box_header,
)
from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar
from constants import MENU_ICONS, STANDARD_CACHE_KEYS

colorama.init(autoreset=True)

# ---------------------------------------------------------------------------
# Location config
# Each entry: display_key -> (metro_city_substrings, ticketmaster_city, state_code)
# ---------------------------------------------------------------------------

METRO_AREAS = {
    "new york city": (
        ["new york", "brooklyn", "queens", "bronx", "manhattan",
         "jersey city", "hoboken", "newark", "astoria"],
        "New York", "NY",
    ),
    "new york": (
        ["new york", "brooklyn", "queens", "bronx", "manhattan",
         "jersey city", "hoboken", "newark", "astoria"],
        "New York", "NY",
    ),
    "nyc": (
        ["new york", "brooklyn", "queens", "bronx", "manhattan",
         "jersey city", "hoboken", "newark", "astoria"],
        "New York", "NY",
    ),
    "los angeles": (
        ["los angeles", "hollywood", "santa monica", "long beach",
         "anaheim", "burbank", "glendale"],
        "Los Angeles", "CA",
    ),
    "la": (
        ["los angeles", "hollywood", "santa monica", "long beach",
         "anaheim", "burbank", "glendale"],
        "Los Angeles", "CA",
    ),
    "chicago":       (["chicago", "evanston"],                            "Chicago",       "IL"),
    "san francisco": (["san francisco", "oakland", "berkeley", "sf"],     "San Francisco", "CA"),
    "sf":            (["san francisco", "oakland", "berkeley", "sf"],     "San Francisco", "CA"),
    "boston":        (["boston", "cambridge", "somerville"],              "Boston",        "MA"),
    "philadelphia":  (["philadelphia", "philly"],                         "Philadelphia",  "PA"),
    "washington dc": (["washington", "arlington", "alexandria"],          "Washington",    "DC"),
    "seattle":       (["seattle", "bellevue", "tacoma"],                  "Seattle",       "WA"),
    "miami":         (["miami", "miami beach", "fort lauderdale"],        "Miami",         "FL"),
    "austin":        (["austin"],                                         "Austin",        "TX"),
    "nashville":     (["nashville"],                                      "Nashville",     "TN"),
    "denver":        (["denver", "boulder"],                              "Denver",        "CO"),
    "atlanta":       (["atlanta", "decatur"],                             "Atlanta",       "GA"),
    "toronto":       (["toronto", "north york", "scarborough"],           "Toronto",       "ON"),
    "london":        (["london", "hackney", "brixton", "camden",
                       "shoreditch", "islington"],                        "London",        ""),
    "berlin":        (["berlin"],                                         "Berlin",        ""),
}

DEFAULT_DAYS = 90

CONCERT_CACHE_TTL  = 7 * 24 * 60 * 60   # 7 days — show listings don't change often
LASTFM_CACHE_TTL   = 24 * 60 * 60        # 24 hours
FOLLOWED_CACHE_TTL = 7 * 24 * 60 * 60   # 7 days — after a refresh it stays fresh all week
MAX_WORKERS        = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ck(s):
    """12-char stable hash — used to build filesystem-safe cache keys."""
    return hashlib.md5(s.lower().encode()).hexdigest()[:12]


def resolve_location(location_str):
    """Return (metro_city_list, ticketmaster_city, state_code) for a location."""
    key = location_str.lower().strip()
    if key in METRO_AREAS:
        cities, tm_city, state = METRO_AREAS[key]
        return cities, tm_city, state
    return [key], location_str, ""


def _city_matches(event_city, metro_cities):
    c = event_city.lower()
    return any(m in c or c in m for m in metro_cities)


def _fmt_date(d):
    """Format date as 'Wednesday, June 18' (no leading zero on day)."""
    return d.strftime("%A, %B %-d") if d != datetime.date.max else "Date TBD"


# ---------------------------------------------------------------------------
# Spotify: refresh then fetch followed artists
# ---------------------------------------------------------------------------

def _follow_silently(sp, artist_dicts, already_followed_ids):
    """Follow a list of artist dicts without any confirmation prompts.

    Returns (count, newly_followed_ids) so callers can update their in-memory
    set instead of re-fetching from the API.
    """
    from exclusion_manager import is_excluded
    from tqdm_utils import create_progress_bar, update_progress_bar, close_progress_bar

    to_follow = [
        a for a in artist_dicts
        if a.get("id") and a["id"] not in already_followed_ids
        and not is_excluded(a["id"], "artist")
    ]
    if not to_follow:
        return 0, set()

    pbar        = create_progress_bar(total=len(to_follow), desc="Following artists", unit="artist")
    count       = 0
    new_ids     = set()
    for i in range(0, len(to_follow), 50):
        batch = to_follow[i:i + 50]
        ids   = [a["id"] for a in batch]
        try:
            sp.user_follow_artists(ids)
            count   += len(ids)
            new_ids |= set(ids)
        except Exception as e:
            print_warning(f"  Batch follow error: {e}")
        update_progress_bar(pbar, len(ids))
    close_progress_bar(pbar)
    return count, new_ids


def refresh_followed_artists(sp):
    """Follow artists from playlists + Liked Songs, then expire the cache.

    Called as a prerequisite before every concert search so the followed-artist
    list is always current. All data calls are cached, so reruns are fast.
    """
    print_info("Refreshing followed artists (prerequisite step)...")

    followed_ids  = set()  # built up in-memory across both steps
    total_new     = 0

    # --- Step 1: playlists ---
    print_info("  Step 1/2: Artists from your created playlists...")
    try:
        import spotify_follow_artists as sfa
        from spotify_utils import fetch_followed_artists
        playlists        = sfa.get_user_playlists(sp)
        playlist_artists = sfa.get_artists_from_playlists(sp, playlists)

        print_info("  Fetching current followed list...")
        followed = fetch_followed_artists(sp, show_progress=True,
                                          cache_key=STANDARD_CACHE_KEYS["followed_artists"],
                                          cache_expiration=FOLLOWED_CACHE_TTL)
        followed_ids = {a["id"] for a in followed if isinstance(a, dict) and "id" in a}
        n, new_ids = _follow_silently(sp, playlist_artists, followed_ids)
        followed_ids |= new_ids
        total_new    += n
        if n:
            print_success(f"  Followed {n} new artists from playlists.")
        else:
            print_info("  No new playlist artists to follow.")
    except Exception as e:
        print_warning(f"  Playlist artist refresh failed: {e}")

    # --- Step 2: Liked Songs ---
    print_info("  Step 2/2: Artists from your Liked Songs...")
    try:
        import spotify_follow_artists_from_liked as sfal
        liked_artists = sfal.get_artists_from_liked_songs(sp)

        n, new_ids = _follow_silently(sp, liked_artists, followed_ids)
        followed_ids |= new_ids
        total_new    += n
        if n:
            print_success(f"  Followed {n} new artists from Liked Songs.")
        else:
            print_info("  No new Liked Songs artists to follow.")
    except Exception as e:
        print_warning(f"  Liked Songs artist refresh failed: {e}")

    # Only expire the followed-artists cache when we actually followed someone new.
    # If nothing changed the cache is still valid and get_followed_artists() can reuse it.
    if total_new:
        save_to_cache(None, STANDARD_CACHE_KEYS["followed_artists"], force_expire=True)
        print_success(f"Followed-artist list refreshed (+{total_new} new).")
    else:
        print_success("Followed-artist list is up to date (cache retained).")


def get_followed_artists(sp):
    """Fetch all followed artists, delegating to the shared utility."""
    from spotify_utils import fetch_followed_artists
    return fetch_followed_artists(
        sp,
        show_progress=True,
        cache_key=STANDARD_CACHE_KEYS["followed_artists"],
        cache_expiration=FOLLOWED_CACHE_TTL,
    )


# ---------------------------------------------------------------------------
# Last.fm: play-count rankings (used to sort within each date)
# ---------------------------------------------------------------------------

def get_lastfm_rankings(api_key, username):
    cache_key = f"lastfm_top_{_ck(username)}"
    cached    = load_from_cache(cache_key, LASTFM_CACHE_TTL)
    if cached is not None:
        return cached

    rankings = {}
    try:
        r = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method":  "user.gettopartists",
                "user":    username,
                "api_key": api_key,
                "format":  "json",
                "limit":   1000,
                "period":  "6month",
            },
            timeout=15,
        )
        if r.status_code == 200:
            for a in r.json().get("topartists", {}).get("artist", []):
                name  = a.get("name", "").lower()
                count = int(a.get("playcount", 0))
                rankings[name] = count
    except Exception as e:
        print_warning(f"Last.fm unavailable: {e}")

    save_to_cache(rankings, cache_key)
    return rankings


# ---------------------------------------------------------------------------
# Bandsintown
# ---------------------------------------------------------------------------

def _fetch_bandsintown(artist_name, app_id, start_date, end_date):
    cache_key = f"bit_{_ck(artist_name)}_{start_date}_{end_date}"
    cached    = load_from_cache(cache_key, CONCERT_CACHE_TTL)
    if cached is not None:
        return cached

    try:
        r = requests.get(
            f"https://rest.bandsintown.com/artists/{quote(artist_name)}/events",
            params={"app_id": app_id, "date": f"{start_date},{end_date}"},
            timeout=10,
        )
        data = r.json() if r.status_code == 200 else []
        if not isinstance(data, list):
            data = []
        save_to_cache(data, cache_key)
        return data
    except Exception:
        save_to_cache([], cache_key)
        return []


def _norm_bandsintown(raw, artist_name):
    venue  = raw.get("venue", {})
    dt_str = raw.get("datetime", "")
    try:
        dt = datetime.datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        dt = None

    offers     = raw.get("offers", [])
    ticket_url = offers[0].get("url", "") if offers else raw.get("url", "")

    return {
        "artist":     artist_name,
        "date":       dt,
        "venue_name": venue.get("name", ""),
        "city":       venue.get("city", ""),
        "region":     venue.get("region", ""),
        "country":    venue.get("country", ""),
        "ticket_url": ticket_url,
        "source":     "Bandsintown",
        "dedup_key":  f"{artist_name.lower()}|{venue.get('name','').lower()}|{dt_str[:10]}",
    }


# ---------------------------------------------------------------------------
# Ticketmaster — city-wide sweep (one paginated query, not per-artist)
# Free tier: 5 req/s, 5000 req/day.  A full city sweep uses ~10-50 pages.
# ---------------------------------------------------------------------------

import time as _time

def _fetch_ticketmaster_citywide(api_key, tm_city, state_code, start_date, end_date):
    """Fetch all music events in a city for the date range, paginated."""
    cache_key = f"tm_city_{_ck(tm_city)}_{start_date}_{end_date}"
    cached    = load_from_cache(cache_key, CONCERT_CACHE_TTL)
    if cached is not None:
        return cached

    all_events = []
    page       = 0
    try:
        while True:
            params = {
                "apikey":             api_key,
                "city":               tm_city,
                "classificationName": "Music",
                "startDateTime":      f"{start_date}T00:00:00Z",
                "endDateTime":        f"{end_date}T23:59:59Z",
                "size":               200,
                "page":               page,
                "sort":               "date,asc",
            }
            if state_code:
                params["stateCode"] = state_code

            r = requests.get(
                "https://app.ticketmaster.com/discovery/v2/events.json",
                params=params, timeout=15,
            )

            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 5))
                if retry_after > 60:
                    print_warning("Ticketmaster daily quota exceeded — try again tomorrow.")
                    break
                _time.sleep(retry_after)
                continue

            if r.status_code != 200:
                break

            data  = r.json()
            fault = data.get("fault", {})
            if fault:
                msg = fault.get("faultstring", "")
                if "QuotaViolation" in msg or "quota" in msg.lower():
                    print_warning("Ticketmaster daily quota exceeded — try again tomorrow.")
                else:
                    print_warning(f"Ticketmaster error: {msg}")
                break

            page_events = data.get("_embedded", {}).get("events", [])
            all_events.extend(page_events)

            page_info   = data.get("page", {})
            total_pages = page_info.get("totalPages", 1)
            if page >= total_pages - 1 or not page_events:
                break
            page += 1
            _time.sleep(0.25)  # stay under 5 req/s

    except Exception as e:
        print_warning(f"Ticketmaster fetch error: {e}")

    save_to_cache(all_events, cache_key)
    return all_events


def _norm_ticketmaster(raw, artist_name):
    venues  = raw.get("_embedded", {}).get("venues", [{}])
    venue   = venues[0] if venues else {}
    city    = venue.get("city",    {}).get("name",       "")
    region  = venue.get("state",   {}).get("stateCode",  "")
    country = venue.get("country", {}).get("countryCode", "")

    start  = raw.get("dates", {}).get("start", {})
    dt_str = start.get("dateTime", "") or start.get("localDate", "")
    try:
        dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        dt = None

    return {
        "artist":     artist_name,
        "date":       dt,
        "venue_name": venue.get("name", ""),
        "city":       city,
        "region":     region,
        "country":    country,
        "ticket_url": raw.get("url", ""),
        "source":     "Ticketmaster",
        "dedup_key":  f"{artist_name.lower()}|{venue.get('name','').lower()}|{dt_str[:10]}",
    }


def _tm_attraction_names(raw):
    """Return lowercase attraction/performer names from a TM event."""
    return {
        a.get("name", "").lower()
        for a in raw.get("_embedded", {}).get("attractions", [])
        if a.get("name")
    }


# ---------------------------------------------------------------------------
# Parallel concert fetch
# ---------------------------------------------------------------------------

def fetch_all_concerts(artists, location, start_date, end_date, credentials):
    tm_key  = credentials.get("TICKETMASTER_CONSUMER_KEY", "")
    metro_cities, tm_city, state_code = resolve_location(location)

    seen   = set()
    events = []

    if not tm_key:
        print_warning("No TICKETMASTER_CONSUMER_KEY configured — no events to fetch.")
        return events

    # One city-wide Ticketmaster sweep (~10-50 paginated calls) then match
    # against followed artists by attraction name — exact lowercase match only,
    # no keyword fuzzy search that caused false positives.
    print_info(f"Fetching all Ticketmaster music events in {tm_city} ({start_date} → {end_date})...")
    followed_lower = {a["name"].lower(): a["name"] for a in artists}  # lower → proper case
    tm_events = _fetch_ticketmaster_citywide(
        tm_key, tm_city, state_code, start_date, end_date
    )
    print_info(f"  {len(tm_events)} events found; matching to your {len(artists)} followed artists...")

    for raw in tm_events:
        attraction_names = _tm_attraction_names(raw)
        matched = attraction_names & followed_lower.keys()
        if not matched:
            continue
        for artist_lower in matched:
            norm = _norm_ticketmaster(raw, followed_lower[artist_lower])
            if norm["dedup_key"] not in seen:
                seen.add(norm["dedup_key"])
                events.append(norm)

    return events


def _sort_key(ev, rankings):
    d = ev["date"].date() if ev["date"] else datetime.date.max
    return (d, -rankings.get(ev["artist"].lower(), 0))


# ---------------------------------------------------------------------------
# Terminal display
# ---------------------------------------------------------------------------

def display_concerts(events, location, date_label, rankings):
    if not events:
        print_warning(f"No upcoming concerts found in {location} for {date_label}.")
        return

    print_box_header(f"UPCOMING CONCERTS — {location.upper()}", icon=MENU_ICONS["music"])
    print_info(f"{date_label}  ·  {len(events)} shows\n")

    prev = None
    for ev in sorted(events, key=lambda e: _sort_key(e, rankings)):
        d = ev["date"].date() if ev["date"] else datetime.date.max
        if d != prev:
            print(f"\n{Fore.YELLOW}{'─' * 55}")
            print(f"{Fore.YELLOW}  {_fmt_date(d)}")
            print(f"{Fore.YELLOW}{'─' * 55}")
            prev = d

        artist   = ev["artist"]
        venue    = ev["venue_name"]
        dt       = ev["date"]
        url      = ev.get("ticket_url", "")
        source   = ev["source"]
        plays    = rankings.get(artist.lower(), 0)

        time_str = dt.strftime("%-I:%M %p") if dt and dt.hour else ""
        play_tag = f" {Fore.CYAN}[{plays:,} plays]{Style.RESET_ALL}" if plays else ""
        time_tag = f"  {Fore.WHITE}{time_str}" if time_str else ""

        print(f"  {Fore.GREEN}{artist}{play_tag}")
        print(f"    {Fore.WHITE}{venue}{time_tag}  {Fore.BLUE}({source}){Style.RESET_ALL}")
        if url:
            print(f"    {Fore.CYAN}{url}")


# ---------------------------------------------------------------------------
# HTML digest (for --output / scheduled task)
# ---------------------------------------------------------------------------

def _safe_url(url):
    """Return url only if it's a safe http(s) link, else empty string."""
    if url and url.lower().startswith(("http://", "https://")):
        return url
    return ""


def build_html_digest(events, location, date_label, rankings):
    rows = ""
    prev = None

    for ev in sorted(events, key=lambda e: _sort_key(e, rankings)):
        d = ev["date"].date() if ev["date"] else datetime.date.max
        if d != prev:
            rows += (
                f'<tr><td colspan="3" style="background:#1a1a2e;color:#e0a800;'
                f'padding:10px 16px;font-weight:bold;font-size:14px;'
                f'border-top:2px solid #e0a800;letter-spacing:.4px">'
                f'{escape(_fmt_date(d))}</td></tr>\n'
            )
            prev = d

        artist   = escape(ev["artist"])
        venue    = escape(ev["venue_name"])
        url      = _safe_url(ev.get("ticket_url", ""))
        safe_url = escape(url, quote=True)
        dt       = ev["date"]
        time_str = escape(dt.strftime("%-I:%M %p")) if dt and dt.hour else ""
        plays    = rankings.get(ev["artist"].lower(), 0)

        play_tag  = (f"<span style='color:#6ec6f5;font-size:11px'> · {plays:,} plays</span>"
                     if plays else "")
        artist_td = (
            f'<a href="{safe_url}" style="color:#1db954;font-weight:bold;text-decoration:none">'
            f'{artist}</a>{play_tag}' if url
            else f'<strong style="color:#1db954">{artist}</strong>{play_tag}'
        )
        venue_td  = venue + (f" · {time_str}" if time_str else "")
        ticket_td = (
            f'<a href="{safe_url}" style="color:#6ec6f5;font-size:12px">Tickets →</a>'
            if url else ""
        )

        rows += (
            f'<tr style="border-bottom:1px solid #2a2a2a">'
            f'<td style="padding:8px 16px;color:#eee">{artist_td}</td>'
            f'<td style="padding:8px 16px;color:#aaa;font-size:13px">{venue_td}</td>'
            f'<td style="padding:8px 16px">{ticket_td}</td>'
            f'</tr>\n'
        )

    generated = datetime.datetime.now().strftime("%B %-d, %Y")
    sources   = "Ticketmaster" + (" · Ranked by Last.fm" if rankings else "")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Concert Digest</title></head>
<body style="background:#0d0d0d;font-family:system-ui,sans-serif;margin:0;padding:24px">
  <div style="max-width:720px;margin:0 auto">
    <h1 style="color:#1db954;font-size:22px;margin-bottom:4px">
      🎵 Upcoming Concerts in {location}
    </h1>
    <p style="color:#888;font-size:13px;margin-top:0">
      {date_label} &nbsp;·&nbsp; Generated {generated} &nbsp;·&nbsp; {len(events)} shows
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;background:#111;border-radius:8px;overflow:hidden">
      <thead>
        <tr style="background:#1a1a1a">
          <th style="padding:10px 16px;color:#888;text-align:left;font-size:11px;
                     text-transform:uppercase;letter-spacing:.8px">Artist</th>
          <th style="padding:10px 16px;color:#888;text-align:left;font-size:11px;
                     text-transform:uppercase;letter-spacing:.8px">Venue</th>
          <th style="padding:10px 16px;color:#888;text-align:left;font-size:11px;
                     text-transform:uppercase;letter-spacing:.8px">Tickets</th>
        </tr>
      </thead>
      <tbody>
{rows}
      </tbody>
    </table>
    <p style="color:#444;font-size:11px;margin-top:16px">{sources}</p>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Spotify auth
# ---------------------------------------------------------------------------

def setup_spotify_client():
    from spotify_utils import create_spotify_client
    return create_spotify_client([
        "user-follow-read",
        "user-follow-modify",
        "user-library-read",
        "playlist-read-private",
    ], "concerts")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Find upcoming concerts for your followed Spotify artists"
    )
    p.add_argument("--location", help="City name (default: New York City)")
    p.add_argument("--days",     type=int, help="Days to look ahead")
    p.add_argument("--output",   help="Write HTML digest to this path instead of printing")
    p.add_argument("--no-lastfm", action="store_true", help="Skip Last.fm play-count ranking")
    return p.parse_args()


def _prompt_location():
    v = input(
        f"{Fore.CYAN}  Location {Fore.WHITE}[New York City]{Fore.CYAN}: {Style.RESET_ALL}"
    ).strip()
    return v or "New York City"


def _prompt_days():
    v = input(
        f"{Fore.CYAN}  Days to look ahead {Fore.WHITE}[{DEFAULT_DAYS}]{Fore.CYAN}: {Style.RESET_ALL}"
    ).strip()
    try:
        days = int(v) if v else DEFAULT_DAYS
    except ValueError:
        days = DEFAULT_DAYS
    return f"Next {days} days", days


def main():
    args  = parse_args()
    creds = get_credentials()

    # Resolve location + date range ----------------------------------------
    if args.location and args.days:
        location   = args.location
        days       = args.days
        date_label = f"Next {days} days"
    else:
        print_box_header("CONCERT FINDER", icon=MENU_ICONS["music"])
        location = args.location or _prompt_location()
        if args.days:
            days, date_label = args.days, f"Next {args.days} days"
        else:
            date_label, days = _prompt_days()

    today      = datetime.date.today()
    start_date = today.strftime("%Y-%m-%d")
    end_date   = (today + datetime.timedelta(days=days)).strftime("%Y-%m-%d")

    # Spotify auth, refresh, then fetch followed artists ------------------
    sp = setup_spotify_client()
    refresh_followed_artists(sp)
    print_info("Fetching final followed-artist list...")
    artists = get_followed_artists(sp)
    if not artists:
        print_error("No followed artists found. Run 'Follow all artists' options first.")
        return

    # Last.fm rankings (optional) -----------------------------------------
    rankings = {}
    if not args.no_lastfm:
        lfm_key  = creds.get("LASTFM_API_KEY", "")
        lfm_user = creds.get("LASTFM_USERNAME") or os.environ.get("LASTFM_USERNAME", "")
        if lfm_key and lfm_user:
            rankings = get_lastfm_rankings(lfm_key, lfm_user)
        elif lfm_key and not lfm_user:
            print_warning("Add LASTFM_USERNAME to ~/.secrets to enable Last.fm ranking.")

    # Fetch + deduplicate -------------------------------------------------
    events = fetch_all_concerts(artists, location, start_date, end_date, creds)

    if not events:
        print_warning(f"No concerts found in {location} for {date_label}.")
        return

    print_success(f"Found {len(events)} shows in {location} for {date_label}.")

    # Output --------------------------------------------------------------
    if args.output:
        html = build_html_digest(events, location, date_label, rankings)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
        print_success(f"HTML digest written to {args.output}")
    else:
        display_concerts(events, location, date_label, rankings)


if __name__ == "__main__":
    main()
