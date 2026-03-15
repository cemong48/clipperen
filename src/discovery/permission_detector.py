# src/discovery/permission_detector.py
# Multi-source permission signal detection for clipping

import os
import re
import logging
import requests

logger = logging.getLogger("clipper.discovery.permission")

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Permission keywords — positive signals
PERMISSION_KEYWORDS = [
    "feel free to clip",
    "clipping allowed",
    "clips welcome",
    "clip my content",
    "you can clip",
    "free to clip",
    "clippers welcome",
    "clip friendly",
    "clip program",
    "clip my videos",
    "repost allowed",
    "share clips",
    "anyone can clip"
]

# Revocation keywords — negative signals
REVOCATION_KEYWORDS = [
    "do not clip",
    "no clipping",
    "no clips",
    "all rights reserved",
    "no reupload",
    "no re-upload",
    "exclusive content",
    "do not repost",
    "clips not allowed"
]

# Confidence scores by source
SOURCE_SCORES = {
    "whop_listing": 95,
    "channel_description": 85,
    "pinned_comment": 80,
    "community_post": 75,
    "video_description": 70
}


def check_text_for_signals(text):
    """
    Check a text block for permission and revocation signals.
    Returns dict with found signals and their types.
    """
    text_lower = text.lower()
    
    found_permissions = []
    found_revocations = []
    
    for keyword in PERMISSION_KEYWORDS:
        if keyword in text_lower:
            found_permissions.append(keyword)
    
    for keyword in REVOCATION_KEYWORDS:
        if keyword in text_lower:
            found_revocations.append(keyword)
    
    return {
        "permissions": found_permissions,
        "revocations": found_revocations,
        "has_permission": len(found_permissions) > 0 and len(found_revocations) == 0,
        "has_revocation": len(found_revocations) > 0
    }


def get_channel_description(channel_id):
    """Fetch channel description from YouTube API."""
    url = f"{YOUTUBE_API_BASE}/channels"
    params = {
        "part": "snippet,brandingSettings",
        "id": channel_id,
        "key": YOUTUBE_API_KEY
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            return items[0].get("snippet", {}).get("description", "")
    except Exception as e:
        logger.error(f"Failed to fetch channel description for {channel_id}: {e}")
    return ""


def get_channel_community_posts(channel_id):
    """
    Attempt to find community posts with permission mentions.
    Note: YouTube Data API v3 has limited community post support.
    Falls back to channel description if unavailable.
    """
    # YouTube API doesn't directly support community posts well
    # This would need web scraping or a different approach in production
    # For now, return empty — channel description is the primary source
    return []


def get_recent_video_descriptions(channel_id, count=5):
    """Get descriptions from the channel's most recent videos."""
    url = f"{YOUTUBE_API_BASE}/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "maxResults": count,
        "key": YOUTUBE_API_KEY
    }
    
    descriptions = []
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        
        for item in items:
            video_id = item.get("id", {}).get("videoId", "")
            if video_id:
                # Get full video description
                vid_url = f"{YOUTUBE_API_BASE}/videos"
                vid_params = {
                    "part": "snippet",
                    "id": video_id,
                    "key": YOUTUBE_API_KEY
                }
                vid_resp = requests.get(vid_url, params=vid_params, timeout=10)
                vid_items = vid_resp.json().get("items", [])
                if vid_items:
                    desc = vid_items[0].get("snippet", {}).get("description", "")
                    descriptions.append({"video_id": video_id, "description": desc})
    except Exception as e:
        logger.error(f"Failed to fetch video descriptions for {channel_id}: {e}")
    
    return descriptions


def get_pinned_comments(channel_id, video_count=3):
    """Check pinned comments on recent videos for permission signals."""
    url = f"{YOUTUBE_API_BASE}/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "maxResults": video_count,
        "key": YOUTUBE_API_KEY
    }
    
    pinned_comments = []
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        
        for item in items:
            video_id = item.get("id", {}).get("videoId", "")
            if not video_id:
                continue
            
            # Get comment threads for this video
            comment_url = f"{YOUTUBE_API_BASE}/commentThreads"
            comment_params = {
                "part": "snippet",
                "videoId": video_id,
                "order": "relevance",
                "maxResults": 5,
                "key": YOUTUBE_API_KEY
            }
            
            comment_resp = requests.get(comment_url, params=comment_params, timeout=10)
            comment_items = comment_resp.json().get("items", [])
            
            for ci in comment_items:
                snippet = ci.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                # Check if comment is from the channel owner
                if snippet.get("authorChannelId", {}).get("value", "") == channel_id:
                    pinned_comments.append({
                        "video_id": video_id,
                        "text": snippet.get("textDisplay", "")
                    })
    except Exception as e:
        logger.error(f"Failed to fetch pinned comments for {channel_id}: {e}")
    
    return pinned_comments


def calculate_confidence(signals):
    """
    Calculate overall permission confidence from all detected signals.
    Returns highest confidence signal found.
    
    Threshold for auto-whitelist: >= 85
    Threshold for flagged review: 70-84
    Below 70: skip entirely
    """
    if not signals:
        return 0
    
    max_confidence = 0
    for signal in signals:
        score = SOURCE_SCORES.get(signal["source"], 50)
        if score > max_confidence:
            max_confidence = score
    
    return max_confidence


def scan_channel_permissions(channel_id, channel_name):
    """
    Full permission scan across all available sources.
    Returns permission result dict.
    """
    logger.info(f"Scanning permissions for: {channel_name} ({channel_id})")
    
    signals = []
    proof_urls = []
    
    # 1. Check channel description
    description = get_channel_description(channel_id)
    if description:
        result = check_text_for_signals(description)
        if result["has_revocation"]:
            logger.warning(f"  REVOCATION found in channel description for {channel_name}")
            return {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "has_permission": False,
                "confidence": 0,
                "source": "revocation_detected",
                "revocation_keywords": result["revocations"],
                "proof_url": f"https://youtube.com/channel/{channel_id}/about"
            }
        if result["has_permission"]:
            signals.append({
                "source": "channel_description",
                "keywords": result["permissions"]
            })
            proof_urls.append(f"https://youtube.com/channel/{channel_id}/about")
            logger.info(f"  ✅ Permission found in channel description")
    
    # 2. Check pinned comments (if no channel desc signal yet)
    if not signals:
        pinned = get_pinned_comments(channel_id)
        for pc in pinned:
            result = check_text_for_signals(pc["text"])
            if result["has_revocation"]:
                return {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "has_permission": False,
                    "confidence": 0,
                    "source": "revocation_detected",
                    "revocation_keywords": result["revocations"],
                    "proof_url": f"https://youtube.com/watch?v={pc['video_id']}"
                }
            if result["has_permission"]:
                signals.append({
                    "source": "pinned_comment",
                    "keywords": result["permissions"],
                    "video_id": pc["video_id"]
                })
                proof_urls.append(f"https://youtube.com/watch?v={pc['video_id']}")
                logger.info(f"  ✅ Permission found in pinned comment")
    
    # 3. Check recent video descriptions
    video_descs = get_recent_video_descriptions(channel_id, count=3)
    for vd in video_descs:
        result = check_text_for_signals(vd["description"])
        if result["has_revocation"]:
            return {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "has_permission": False,
                "confidence": 0,
                "source": "revocation_detected",
                "revocation_keywords": result["revocations"],
                "proof_url": f"https://youtube.com/watch?v={vd['video_id']}"
            }
        if result["has_permission"]:
            signals.append({
                "source": "video_description",
                "keywords": result["permissions"],
                "video_id": vd["video_id"]
            })
            proof_urls.append(f"https://youtube.com/watch?v={vd['video_id']}")
    
    confidence = calculate_confidence(signals)
    best_source = signals[0]["source"] if signals else None
    
    return {
        "channel_id": channel_id,
        "channel_name": channel_name,
        "has_permission": confidence >= 70,
        "confidence": confidence,
        "source": f"auto_{best_source}" if best_source else "no_signal",
        "signals": signals,
        "proof_urls": proof_urls,
        "permission_proof_url": proof_urls[0] if proof_urls else None
    }


def check_for_revocation(channel_id, channel_name):
    """
    Re-check a channel for revocation signals.
    Used during weekly re-validation of whitelist.
    """
    description = get_channel_description(channel_id)
    if description:
        result = check_text_for_signals(description)
        if result["has_revocation"]:
            return True, result["revocations"]
    
    video_descs = get_recent_video_descriptions(channel_id, count=3)
    for vd in video_descs:
        result = check_text_for_signals(vd["description"])
        if result["has_revocation"]:
            return True, result["revocations"]
    
    return False, []
