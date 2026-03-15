# src/scheduler/random_offset.py
# Random ±45 min offset per slot for natural posting pattern

import random
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("clipper.scheduler.random_offset")

# Base time slots in WIB (UTC+7)
BASE_SLOTS = {
    "07:00": "short",   # Slot 1: Short
    "11:00": "long",    # Slot 2: Long Clip
    "16:00": "short",   # Slot 3: Short
    "20:00": "long"     # Slot 4: Long Clip
}

RANDOM_OFFSET_MINUTES = 45


def calculate_post_time(base_time_str, offset_range=RANDOM_OFFSET_MINUTES):
    """
    Apply random ±offset to a base time slot.
    
    Args:
        base_time_str: Time in HH:MM format (e.g., "07:00")
        offset_range: Maximum offset in minutes (default ±45)
    
    Returns:
        datetime.time object with the randomized posting time
    """
    hours, minutes = map(int, base_time_str.split(":"))
    base = datetime(2000, 1, 1, hours, minutes)
    
    offset = random.randint(-offset_range, offset_range)
    actual = base + timedelta(minutes=offset)
    
    # Clamp to valid day hours (don't post before 6AM or after 11PM)
    if actual.hour < 6:
        actual = actual.replace(hour=6, minute=random.randint(0, 30))
    elif actual.hour >= 23:
        actual = actual.replace(hour=22, minute=random.randint(30, 59))
    
    return actual.time()


def generate_daily_schedule():
    """
    Generate today's posting schedule with randomized times.
    
    Returns:
        List of dicts, each with:
            - time: HH:MM string
            - base_slot: original slot time
            - format: 'short' or 'long'
            - slot_index: 0-3
    """
    schedule = []
    
    for idx, (base_time, format_type) in enumerate(BASE_SLOTS.items()):
        actual_time = calculate_post_time(base_time)
        
        schedule.append({
            "time": actual_time.strftime("%H:%M"),
            "base_slot": base_time,
            "format": format_type,
            "slot_index": idx
        })
    
    # Sort by actual post time
    schedule.sort(key=lambda x: x["time"])
    
    logger.info("Daily schedule generated:")
    for s in schedule:
        logger.info(f"  Slot {s['slot_index']+1}: {s['time']} ({s['format']}) [base: {s['base_slot']}]")
    
    return schedule


def assign_videos_to_slots(schedule, manual_videos, auto_videos):
    """
    Assign videos to time slots.
    Manual videos get first pick of their format slot.
    Auto fills remaining.
    
    Args:
        schedule: From generate_daily_schedule()
        manual_videos: List of manual queue videos
        auto_videos: List of auto-discovered videos
    
    Returns:
        List of slot assignments with video + time info
    """
    assignments = []
    used_manual = set()
    used_auto = set()
    
    for slot in schedule:
        assigned = False
        
        # Try manual videos first (matching format)
        for i, mv in enumerate(manual_videos):
            if i in used_manual:
                continue
            if mv.get("format") == slot["format"]:
                assignments.append({
                    **slot,
                    "video": mv,
                    "source": "manual"
                })
                used_manual.add(i)
                assigned = True
                break
        
        if assigned:
            continue
        
        # Fill with auto video (matching format)
        for i, av in enumerate(auto_videos):
            if i in used_auto:
                continue
            if av.get("format") == slot["format"]:
                assignments.append({
                    **slot,
                    "video": av,
                    "source": "auto"
                })
                used_auto.add(i)
                assigned = True
                break
        
        if not assigned:
            logger.warning(f"No video available for slot: {slot['time']} ({slot['format']})")
            assignments.append({
                **slot,
                "video": None,
                "source": "empty"
            })
    
    return assignments
