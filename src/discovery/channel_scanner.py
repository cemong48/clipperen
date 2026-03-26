# src/discovery/channel_scanner.py
# YouTube API channel search + expansion beyond 25 seeds
# Uses per-channel API keys to avoid rate limits

import os
import json
import time
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests

from ..utils.file_lock import read_json, write_json
from ..utils.channel_credentials import get_api_key, CHANNEL_INDEX

logger = logging.getLogger("clipper.discovery.scanner")

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Niche keywords for discovering new channels via video search
NICHE_KEYWORDS = {
    "Psychology & Self-Improvement": [
        "psychology explained", "self improvement", "mental health tips",
        "behavior science", "personal development"
    ],
    "Finance & Business": [
        "personal finance", "business mindset", "investing basics",
        "entrepreneurship", "financial freedom"
    ],
    "Health & Science": [
        "health science", "longevity research", "nutrition science",
        "fitness research", "medical explained"
    ],
    "Tech & AI": [
        "artificial intelligence explained", "machine learning",
        "tech news", "AI tools", "future technology"
    ],
    "Philosophy & Stoicism": [
        "philosophy explained", "stoicism", "critical thinking",
        "life philosophy", "wisdom"
    ]
}


def _get_api_key_for_context(channel_name=None):
    """Get the API key for a specific channel. NO cross-channel fallback."""
    if channel_name:
        try:
            return get_api_key(channel_name)
        except ValueError:
            logger.error(f"No YouTube API key found for channel '{channel_name}' — skipping")
            return ""
    
    logger.error("No channel_name provided to _get_api_key_for_context — cannot determine API key")
    return ""


def youtube_search_videos(keyword, max_results=10, published_after=None, channel_name=None):
    """Search YouTube for videos matching a keyword."""
    api_key = _get_api_key_for_context(channel_name)
    
    url = f"{YOUTUBE_API_BASE}/search"
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "viewCount",
        "maxResults": max_results,
        "key": api_key
    }
    if published_after:
        params["publishedAfter"] = published_after

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as e:
        logger.error(f"YouTube search failed for '{keyword}': {e}")
        return []


def get_channel_info(channel_id, channel_name=None):
    """Get channel snippet info via YouTube Data API."""
    api_key = _get_api_key_for_context(channel_name)
    
    url = f"{YOUTUBE_API_BASE}/channels"
    params = {
        "part": "snippet,statistics",
        "id": channel_id,
        "key": api_key
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return items[0] if items else None
    except Exception as e:
        logger.error(f"Channel info fetch failed for {channel_id}: {e}")
        return None


def discover_new_channels(whitelist_path="config/whitelist.json",
                          seeds_path="config/seeds.json",
                          settings_path="config/settings.json"):
    """
    Discover new channels beyond the 25 seeds using niche keyword search.
    Runs weekly. For each keyword per theme, searches recent popular videos
    and extracts unique channel IDs not already in the whitelist.
    
    Returns list of newly discovered channel dicts ready for permission scanning.
    """
    # Load existing whitelist and seeds to skip known channels
    whitelist = read_json(whitelist_path, default={"channels": []})
    seeds = read_json(seeds_path, default={"seeds": []})
    settings = read_json(settings_path, default={})
    
    max_channels = settings.get("discovery", {}).get("max_channels_per_scan", 50)
    
    known_ids = set()
    for ch in whitelist.get("channels", []):
        known_ids.add(ch.get("channel_id", ""))
    for theme_group in seeds.get("seeds", []):
        for ch in theme_group.get("channels", []):
            known_ids.add(ch.get("channel_id", ""))
    
    # Search for videos from last 30 days
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
    
    discovered = []
    seen_ids = set()
    
    for theme, keywords in NICHE_KEYWORDS.items():
        for keyword in keywords:
            if len(discovered) >= max_channels:
                break
                
            logger.info(f"Scanning keyword: '{keyword}' (theme: {theme})")
            results = youtube_search_videos(keyword, max_results=10, published_after=thirty_days_ago)
            
            for item in results:
                channel_id = item.get("snippet", {}).get("channelId", "")
                channel_name = item.get("snippet", {}).get("channelTitle", "")
                
                if not channel_id or channel_id in known_ids or channel_id in seen_ids:
                    continue
                
                seen_ids.add(channel_id)
                
                discovered.append({
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "theme": theme,
                    "discovered_via": keyword,
                    "discovered_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                })
                
                logger.info(f"  NEW: {channel_name} ({channel_id})")
            
            # Rate limit: 1 request per second
            time.sleep(1.1)
    
    logger.info(f"Discovery complete. Found {len(discovered)} new channel(s).")
    return discovered


def get_latest_videos(channel_id, max_results=10, days_back=7, channel_name=None):
    """
    Get latest videos from a channel (last N days).
    Uses YouTube Data API with automatic RSS fallback on 403.
    """
    api_key = _get_api_key_for_context(channel_name)
    published_after = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    
    url = f"{YOUTUBE_API_BASE}/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "maxResults": max_results,
        "publishedAfter": published_after,
        "key": api_key
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code == 403:
            # Log the specific reason from the API response
            try:
                error_data = resp.json()
                error_reason = error_data.get("error", {}).get("errors", [{}])[0].get("reason", "unknown")
                error_message = error_data.get("error", {}).get("message", "unknown")
                logger.warning(
                    f"YouTube API 403 for {channel_id} (key index for {channel_name}): "
                    f"reason={error_reason}, message={error_message}. "
                    f"Falling back to RSS."
                )
            except Exception:
                logger.warning(f"YouTube API 403 for {channel_id}. Falling back to RSS.")
            
            # Fallback to RSS
            return get_latest_videos_rss(channel_id, max_results=max_results, days_back=days_back)
        
        resp.raise_for_status()
        return resp.json().get("items", [])
    except requests.exceptions.HTTPError as e:
        logger.error(f"Failed to get latest videos for {channel_id}: {e}")
        # Try RSS fallback for any HTTP error
        return get_latest_videos_rss(channel_id, max_results=max_results, days_back=days_back)
    except Exception as e:
        logger.error(f"Failed to get latest videos for {channel_id}: {e}")
        return get_latest_videos_rss(channel_id, max_results=max_results, days_back=days_back)


def get_latest_videos_rss(channel_id, max_results=10, days_back=7):
    """
    Fallback: Get latest videos via YouTube's public RSS feed.
    No API key required. Returns items in the same format as the API.
    """
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    
    try:
        resp = requests.get(rss_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; RSS reader)"
        })
        if resp.status_code != 200:
            logger.debug(f"RSS feed failed ({resp.status_code}) for {channel_id}")
            return []
        
        # Parse Atom XML
        root = ET.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        items = []
        
        for entry in root.findall("atom:entry", ns):
            if len(items) >= max_results:
                break
            
            video_id = entry.find("yt:videoId", ns)
            title = entry.find("atom:title", ns)
            published = entry.find("atom:published", ns)
            
            if video_id is None:
                continue
            
            vid = video_id.text
            
            # Filter by date
            if published is not None:
                try:
                    pub_date = datetime.strptime(published.text[:19], "%Y-%m-%dT%H:%M:%S")
                    if pub_date < cutoff:
                        continue
                except Exception:
                    pass
            
            # Format to match YouTube API response structure
            items.append({
                "id": {"videoId": vid},
                "snippet": {
                    "title": title.text if title is not None else "",
                    "channelId": channel_id,
                    "publishedAt": published.text if published is not None else ""
                }
            })
        
        logger.info(f"RSS fallback: found {len(items)} video(s) for {channel_id}")
        return items
        
    except Exception as e:
        logger.error(f"RSS fallback failed for {channel_id}: {e}")
        return []


def get_video_details(video_id, channel_name=None):
    """Get detailed info about a specific video."""
    api_key = _get_api_key_for_context(channel_name)
    
    url = f"{YOUTUBE_API_BASE}/videos"
    params = {
        "part": "snippet,contentDetails,status",
        "id": video_id,
        "key": api_key
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        
        if resp.status_code == 403:
            try:
                error_data = resp.json()
                error_reason = error_data.get("error", {}).get("errors", [{}])[0].get("reason", "unknown")
                logger.error(f"YouTube API 403 for video {video_id}: reason={error_reason}")
            except Exception:
                logger.error(f"YouTube API 403 for video {video_id}")
            return None
        
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return items[0] if items else None
    except Exception as e:
        logger.error(f"Failed to get video details for {video_id}: {e}")
        return None


def get_channel_uploads(channel_id, max_pages=3, channel_name=None):
    """
    Get videos from a channel's uploads playlist using playlistItems.list.
    Much cheaper than search API: 1 quota/call (vs 100 for search).
    Returns up to max_pages * 50 video items from the channel's full catalog.
    
    Args:
        channel_id: YouTube channel ID (UCxxxxx)
        max_pages: Max number of pages to fetch (50 videos/page)
        channel_name: Channel name for API key selection
    
    Returns:
        List of video items in the same format as get_latest_videos()
    """
    api_key = _get_api_key_for_context(channel_name)
    if not api_key:
        logger.warning(f"No API key for channel '{channel_name}' — skipping uploads scan")
        return []
    
    logger.info(f"Channel uploads scan: {channel_id} (key len={len(api_key)}, channel={channel_name})")
    
    # Step 1: Get the actual uploads playlist ID via channels API (1 quota)
    uploads_playlist_id = None
    try:
        ch_url = f"{YOUTUBE_API_BASE}/channels"
        ch_params = {
            "part": "contentDetails",
            "id": channel_id,
            "key": api_key
        }
        ch_resp = requests.get(ch_url, params=ch_params, timeout=10)
        logger.info(f"  channels.list HTTP {ch_resp.status_code} for {channel_id}")
        if ch_resp.status_code == 200:
            ch_data = ch_resp.json()
            ch_items = ch_data.get("items", [])
            logger.info(f"  channels.list items: {len(ch_items)}")
            if ch_items:
                uploads_playlist_id = (
                    ch_items[0]
                    .get("contentDetails", {})
                    .get("relatedPlaylists", {})
                    .get("uploads", "")
                )
                if uploads_playlist_id:
                    logger.info(f"Uploads playlist for {channel_id}: {uploads_playlist_id}")
        elif ch_resp.status_code == 403:
            try:
                err_body = ch_resp.json()
                err_reason = err_body.get("error", {}).get("errors", [{}])[0].get("reason", "unknown")
                err_msg = err_body.get("error", {}).get("message", "")[:100]
                logger.warning(f"Channels API 403 for {channel_id}: {err_reason} — {err_msg}")
            except Exception:
                logger.warning(f"Channels API 403 for {channel_id}")
        else:
            # Log unexpected status codes
            try:
                err_body = ch_resp.text[:200]
            except Exception:
                err_body = "?"
            logger.warning(f"Channels API HTTP {ch_resp.status_code} for {channel_id}: {err_body}")
    except Exception as e:
        logger.warning(f"Channels API failed for {channel_id}: {e}")
    
    # Fallback: UC → UU conversion
    if not uploads_playlist_id:
        if channel_id.startswith("UC"):
            uploads_playlist_id = "UU" + channel_id[2:]
            logger.info(f"Using UC→UU fallback: {uploads_playlist_id}")
        else:
            logger.warning(f"Cannot determine uploads playlist for {channel_id}")
            return []
    
    all_items = []
    next_page_token = None
    
    for page in range(max_pages):
        url = f"{YOUTUBE_API_BASE}/playlistItems"
        params = {
            "part": "snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": 50,
            "key": api_key
        }
        if next_page_token:
            params["pageToken"] = next_page_token
        
        try:
            resp = requests.get(url, params=params, timeout=15)
            
            if resp.status_code == 403:
                try:
                    error_data = resp.json()
                    error_reason = error_data.get("error", {}).get("errors", [{}])[0].get("reason", "unknown")
                    error_msg = error_data.get("error", {}).get("message", "")[:100]
                    logger.warning(f"YouTube API 403 for uploads playlist: {error_reason} — {error_msg}")
                except Exception:
                    logger.warning(f"YouTube API 403 for uploads playlist")
                break
            
            if resp.status_code == 404:
                try:
                    error_data = resp.json()
                    error_reason = error_data.get("error", {}).get("errors", [{}])[0].get("reason", "unknown")
                    error_msg = error_data.get("error", {}).get("message", "")[:100]
                    logger.warning(f"Uploads playlist not found: {uploads_playlist_id} — {error_reason}: {error_msg}")
                except Exception:
                    logger.warning(f"Uploads playlist not found: {uploads_playlist_id}")
                break
            
            resp.raise_for_status()
            data = resp.json()
            
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                video_id = snippet.get("resourceId", {}).get("videoId", "")
                
                if not video_id:
                    continue
                
                # Format to match get_latest_videos() response structure
                all_items.append({
                    "id": {"videoId": video_id},
                    "snippet": {
                        "title": snippet.get("title", ""),
                        "channelId": channel_id,
                        "channelTitle": snippet.get("channelTitle", ""),
                        "publishedAt": snippet.get("publishedAt", ""),
                        "description": snippet.get("description", "")
                    }
                })
            
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break  # No more pages
                
        except Exception as e:
            logger.error(f"Failed to get uploads for {channel_id} (page {page + 1}): {e}")
            break
    
    logger.info(f"Channel uploads: found {len(all_items)} video(s) from {channel_id}")
    return all_items


