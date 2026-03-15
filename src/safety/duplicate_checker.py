# src/safety/duplicate_checker.py
# Cross-channel segment overlap detection — Layer 2
# Checks ALL channels to ensure no duplicate clips anywhere

import json
import logging

from ..utils.file_lock import read_json

logger = logging.getLogger("clipper.safety.duplicate_checker")


def time_to_sec(t):
    """
    Convert time string (MM:SS or HH:MM:SS) to seconds.
    """
    if not t:
        return 0

    parts = str(t).split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(t)


def is_duplicate(source_video_id, start_sec, end_sec, posted_path="database/posted.json"):
    """
    Check if this exact segment (or 50%+ overlap) has already been posted
    on ANY channel. This prevents the same clip from appearing on multiple channels.

    Args:
        source_video_id: YouTube video ID of the source
        start_sec: Start time in seconds
        end_sec: End time in seconds
        posted_path: Path to posted.json

    Returns:
        True if duplicate (>= 50% overlap on ANY channel), False otherwise.
    """
    posted = read_json(posted_path, default=[])

    for entry in posted:
        if entry.get("source_video_id") != source_video_id:
            continue

        prev_start = time_to_sec(entry.get("start_time", "0:00"))
        prev_end = time_to_sec(entry.get("end_time", "0:00"))

        # Calculate overlap
        overlap = min(end_sec, prev_end) - max(start_sec, prev_start)
        duration = min(end_sec - start_sec, prev_end - prev_start)

        if duration > 0 and (overlap / duration) >= 0.5:
            existing_channel = entry.get("target_channel", "unknown")
            existing_title = entry.get("title", "Unknown")
            logger.warning(
                f"CROSS-CHANNEL DUPLICATE: {source_video_id} "
                f"[{start_sec:.0f}-{end_sec:.0f}] overlaps with "
                f"[{prev_start:.0f}-{prev_end:.0f}] ({overlap/duration*100:.0f}%) "
                f"already posted on channel '{existing_channel}' "
                f"as '{existing_title}'"
            )
            return True

    return False


def is_duplicate_across_channels(source_video_id, start_sec, end_sec,
                                  target_channel, posted_path="database/posted.json"):
    """
    Enhanced duplicate check that also warns if same source video
    is being used too many times across channels.

    Args:
        source_video_id: YouTube video ID of the source
        start_sec: Start time in seconds
        end_sec: End time in seconds
        target_channel: The channel this clip is intended for
        posted_path: Path to posted.json

    Returns:
        dict with:
            is_duplicate: bool - True if segment overlap >= 50%
            same_source_count: int - how many clips from this source exist
            channels_used: list - which channels already have clips from this source
    """
    posted = read_json(posted_path, default=[])

    same_source = [e for e in posted if e.get("source_video_id") == source_video_id]
    channels_used = list(set(e.get("target_channel", "unknown") for e in same_source))

    # Check segment overlap
    has_overlap = False
    for entry in same_source:
        prev_start = time_to_sec(entry.get("start_time", "0:00"))
        prev_end = time_to_sec(entry.get("end_time", "0:00"))

        overlap = min(end_sec, prev_end) - max(start_sec, prev_start)
        duration = min(end_sec - start_sec, prev_end - prev_start)

        if duration > 0 and (overlap / duration) >= 0.5:
            has_overlap = True
            break

    if len(same_source) > 0:
        logger.info(
            f"Source {source_video_id}: {len(same_source)} existing clip(s) "
            f"on channels: {channels_used}"
        )

    return {
        "is_duplicate": has_overlap,
        "same_source_count": len(same_source),
        "channels_used": channels_used
    }


def is_video_already_processed(source_video_id, posted_path="database/posted.json"):
    """
    Check if any clip from this source video has already been posted
    on ANY channel.
    Returns list of existing entries for this video across all channels.
    """
    posted = read_json(posted_path, default=[])
    existing = [e for e in posted if e.get("source_video_id") == source_video_id]

    if existing:
        channels = set(e.get("target_channel", "?") for e in existing)
        logger.info(
            f"Source {source_video_id} already has {len(existing)} clip(s) "
            f"posted on: {list(channels)}"
        )

    return existing
