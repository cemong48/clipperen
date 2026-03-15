# src/safety/duplicate_checker.py
# Internal segment overlap detection — Layer 3

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
    Check if this exact segment (or 50%+ overlap) has already been posted.
    
    Args:
        source_video_id: YouTube video ID of the source
        start_sec: Start time in seconds
        end_sec: End time in seconds
        posted_path: Path to posted.json
    
    Returns:
        True if duplicate (>= 50% overlap), False otherwise.
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
            logger.warning(
                f"Duplicate detected: {source_video_id} "
                f"[{start_sec:.0f}-{end_sec:.0f}] overlaps with "
                f"[{prev_start:.0f}-{prev_end:.0f}] ({overlap/duration*100:.0f}%)"
            )
            return True
    
    return False


def is_video_already_processed(source_video_id, posted_path="database/posted.json"):
    """
    Check if any clip from this source video has already been posted.
    Returns list of existing entries for this video.
    """
    posted = read_json(posted_path, default=[])
    return [e for e in posted if e.get("source_video_id") == source_video_id]
