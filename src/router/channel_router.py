# src/router/channel_router.py
# Maps theme → correct channel, handles queue target_channel override

import json
import logging
from datetime import datetime

from .topic_classifier import classify_video, CHANNEL_MAP
from ..utils.file_lock import read_json, write_json, append_to_json_list

logger = logging.getLogger("clipper.router.channel_router")

THEME_LABELS = {
    "psychology_self_improvement": "Psychology & Self-Improvement",
    "finance_business": "Finance & Business",
    "health_science": "Health & Science",
    "tech_ai": "Tech & AI",
    "philosophy_wisdom": "Philosophy & Wisdom"
}

UNCLASSIFIED_PATH = "database/unclassified.json"


def route_video(video_metadata, queue_entry=None):
    """
    Determine target channel for a video.
    
    Priority:
    1. If queue_entry has explicit target_channel → use it (operator override)
    2. If auto-discovered → classify via Gemini → route
    3. If manual queue with target_channel=null → classify via Gemini → route
    
    Returns:
        {
            "channel": "psyched",
            "theme": "psychology_self_improvement",
            "confidence": 92,
            "routing_method": "gemini_auto" | "operator_override",
            "action": "proceed" | "flag_review" | "hold"
        }
    """
    # Priority 1: Operator override in queue
    if queue_entry and queue_entry.get("target_channel"):
        channel = queue_entry["target_channel"]
        logger.info(f"Routing via operator override → {channel}")
        return {
            "channel": channel,
            "theme": None,
            "confidence": 100,
            "routing_method": "operator_override",
            "action": "proceed"
        }
    
    # Priority 2: Gemini classification
    title = video_metadata.get("title", "")
    description = video_metadata.get("description", "")
    transcript = video_metadata.get("transcript", "")
    
    classification = classify_video(
        title=title,
        description=description,
        transcript_excerpt=transcript[:2000]
    )
    
    confidence = classification.get("confidence", 0)
    primary_theme = classification.get("primary_theme", "")
    channel = CHANNEL_MAP.get(primary_theme, "sage")
    
    # Determine action based on confidence
    if confidence >= 80:
        action = "proceed"
    elif confidence >= 60:
        action = "flag_review"  # Post but log for operator check
        logger.warning(
            f"Low-confidence routing ({confidence}%): '{title[:50]}' → {channel}. "
            f"Flagged for review."
        )
    else:
        action = "hold"  # Don't post, wait for operator decision
        logger.warning(
            f"Very low confidence ({confidence}%): '{title[:50]}'. "
            f"Holding for operator review."
        )
        # Save to unclassified queue
        _hold_video(video_metadata, classification)
    
    result = {
        "channel": channel,
        "theme": primary_theme,
        "confidence": confidence,
        "secondary_theme": classification.get("secondary_theme"),
        "routing_method": "gemini_auto",
        "action": action,
        "reasoning": classification.get("reasoning", "")
    }
    
    logger.info(
        f"Routed: '{title[:50]}' → {channel} "
        f"(confidence: {confidence}%, action: {action})"
    )
    
    return result


def _hold_video(video_metadata, classification):
    """Save a low-confidence video to the unclassified queue for operator review."""
    held_entry = {
        "source_url": video_metadata.get("url", ""),
        "title": video_metadata.get("title", ""),
        "held_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classification_result": {
            "primary_theme": classification.get("primary_theme"),
            "confidence": classification.get("confidence", 0),
            "secondary_theme": classification.get("secondary_theme"),
            "reasoning": classification.get("reasoning", "")
        },
        "operator_decision": None,
        "target_channel_override": None
    }
    
    unclassified = read_json(UNCLASSIFIED_PATH, default={"held_videos": []})
    unclassified["held_videos"].append(held_entry)
    write_json(UNCLASSIFIED_PATH, unclassified)
    logger.info(f"Video held for review: {video_metadata.get('title', 'Unknown')}")


def process_unclassified_overrides():
    """
    Check unclassified queue for videos that operator has assigned
    a target_channel_override. Remove processed entries.
    
    Returns list of videos ready to process.
    """
    unclassified = read_json(UNCLASSIFIED_PATH, default={"held_videos": []})
    
    ready = []
    remaining = []
    
    for entry in unclassified.get("held_videos", []):
        if entry.get("target_channel_override"):
            ready.append({
                "url": entry["source_url"],
                "title": entry.get("title", ""),
                "target_channel": entry["target_channel_override"],
                "routing_method": "operator_override_from_hold"
            })
            logger.info(f"Unclassified video resolved: {entry.get('title', 'Unknown')} → {entry['target_channel_override']}")
        else:
            remaining.append(entry)
    
    if ready:
        unclassified["held_videos"] = remaining
        write_json(UNCLASSIFIED_PATH, unclassified)
    
    return ready
