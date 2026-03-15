# src/content/format_classifier.py
# Classify SOURCE video as Short/Long candidate based on duration

import logging

logger = logging.getLogger("clipper.content.format_classifier")


def classify_source_format(duration_minutes):
    """
    Classify what clip formats can be extracted from a source video
    based on its duration.
    
    Rules (from instructions):
        source >= 20min  → attempt both Long + Short
        source 3-19min   → Long only
        source < 3min    → skip entirely
    
    Args:
        duration_minutes: Source video duration in minutes.
    
    Returns:
        dict with:
            - 'can_long': bool — whether a Long Clip can be attempted
            - 'can_short': bool — whether a Short can be attempted
            - 'skip': bool — whether to skip this video entirely
            - 'reason': str — explanation
    """
    if duration_minutes < 3:
        logger.info(f"Source video too short ({duration_minutes:.1f}min < 3min) — SKIP")
        return {
            "can_long": False,
            "can_short": False,
            "skip": True,
            "reason": f"Source too short ({duration_minutes:.1f}min). Minimum 3 minutes required."
        }
    
    if duration_minutes < 20:
        logger.info(f"Source video {duration_minutes:.1f}min — Long Clip only")
        return {
            "can_long": True,
            "can_short": False,
            "skip": False,
            "reason": f"Source {duration_minutes:.1f}min (3-19min range). Long Clip only."
        }
    
    logger.info(f"Source video {duration_minutes:.1f}min — both Long + Short eligible")
    return {
        "can_long": True,
        "can_short": True,
        "skip": False,
        "reason": f"Source {duration_minutes:.1f}min (>= 20min). Both Long + Short eligible."
    }


def duration_seconds_to_minutes(seconds):
    """Convert seconds to minutes."""
    return seconds / 60.0


def parse_iso_duration(iso_duration):
    """
    Parse ISO 8601 duration (e.g. 'PT1H23M45S') to seconds.
    YouTube API returns durations in this format.
    """
    import re
    
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, iso_duration)
    
    if not match:
        return 0
    
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    
    return hours * 3600 + minutes * 60 + seconds
