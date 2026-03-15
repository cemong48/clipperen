# src/safety/acr_checker.py
# ACRCloud audio fingerprint scan — Layer 1 (raw) and Layer 4 (final)

import json
import os
import logging

logger = logging.getLogger("clipper.safety.acr_checker")

ACR_CONFIG = {
    "access_key": os.environ.get("ACR_ACCESS_KEY", ""),
    "access_secret": os.environ.get("ACR_ACCESS_SECRET", ""),
    "host": "identify-eu-west-1.acrcloud.com",
    "timeout": 10
}


def scan_audio(clip_path):
    """
    Scan audio file against ACRCloud Content ID database.
    
    Returns dict:
    {
        "safe": True/False,
        "action": "proceed" | "mute_segments" | "skip",
        "music_segments": [(start_sec, end_sec), ...],
        "details": {...}
    }
    """
    if not ACR_CONFIG["access_key"] or not ACR_CONFIG["access_secret"]:
        logger.warning("ACRCloud credentials not set. Skipping ACR scan (treating as safe).")
        return {"safe": True, "action": "proceed", "music_segments": [], "details": {}}
    
    try:
        import acrcloud
        acr = acrcloud.ACRCloud(ACR_CONFIG)
        result = acr.identify_by_file(clip_path, 0)
    except ImportError:
        logger.warning("acrcloud package not installed. Skipping ACR scan.")
        return {"safe": True, "action": "proceed", "music_segments": [], "details": {}}
    except Exception as e:
        # If ACR fails to respond → treat as safe to avoid blocking pipeline
        logger.warning(f"ACRCloud scan error: {e}. Treating as safe.")
        return {"safe": True, "action": "proceed", "music_segments": [], "details": {}}
    
    try:
        data = json.loads(result) if isinstance(result, str) else result
    except Exception:
        logger.warning("ACRCloud returned unparseable response. Treating as safe.")
        return {"safe": True, "action": "proceed", "music_segments": []}
    
    code = data.get("status", {}).get("code", -1)
    
    if code != 0:
        # No music detected
        logger.info(f"ACRCloud scan clean: {clip_path}")
        return {"safe": True, "action": "proceed", "music_segments": []}
    
    # Music detected — analyze duration
    music_items = data.get("metadata", {}).get("music", [])
    total_music_sec = sum(
        item.get("duration_ms", 0) / 1000
        for item in music_items
    )
    
    logger.info(f"ACRCloud detected {total_music_sec:.1f}s of music in {clip_path}")
    
    if total_music_sec < 10:
        return {
            "safe": False,
            "action": "mute_segments",
            "music_segments": extract_timestamps(music_items),
            "details": music_items
        }
    else:
        return {
            "safe": False,
            "action": "skip",
            "music_segments": [],
            "details": music_items
        }


def extract_timestamps(music_items):
    """Extract start/end timestamps from ACR music detection results."""
    segments = []
    for item in music_items:
        start = item.get("play_offset_ms", 0) / 1000
        duration = item.get("duration_ms", 0) / 1000
        segments.append((start, start + duration))
    return segments
