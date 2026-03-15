# src/scheduler/slot_manager.py
# Manage 4 daily slots per channel — always 2 Shorts + 2 Long Clips

import logging

logger = logging.getLogger("clipper.scheduler.slot_manager")


def calculate_slots_per_channel(channel_name, routed_manual_videos):
    """
    Calculate slot allocation for a single channel.
    
    Critical concept: Slot allocation is per channel independently.
    Each channel ALWAYS posts exactly 4 videos/day.
    Format ratio ALWAYS = 2 Shorts + 2 Long Clips per channel.
    
    Args:
        channel_name: Target channel name (e.g., 'psyched', 'minted')
        routed_manual_videos: List of manual videos already routed to 
                              this channel today (via auto-router)
    
    Returns:
        dict with slot allocation for this channel.
    """
    # Filter manual videos routed to this specific channel
    manual = [v for v in routed_manual_videos
              if v.get("target_channel") == channel_name]
    
    # Cap manual at 2 per channel per day
    overflow = []
    if len(manual) > 2:
        overflow = manual[2:]   # carry over to tomorrow
        manual = manual[:2]
    
    manual_count = len(manual)
    auto_count = 4 - manual_count
    
    # Detect formats of manual videos
    manual_shorts = [v for v in manual if v.get("format") == "short"]
    manual_longs = [v for v in manual if v.get("format") == "long"]
    
    # Auto fills to maintain 2 Shorts + 2 Long always
    auto_shorts_needed = max(0, 2 - len(manual_shorts))
    auto_longs_needed = max(0, 2 - len(manual_longs))
    
    result = {
        "channel": channel_name,
        "manual_videos": manual,
        "manual_count": manual_count,
        "auto_shorts_needed": auto_shorts_needed,
        "auto_longs_needed": auto_longs_needed,
        "auto_total": auto_count,
        "overflow_to_tomorrow": overflow,
        "total_posts": 4
    }
    
    logger.info(
        f"Slots for {channel_name}: "
        f"manual={manual_count} (S:{len(manual_shorts)}/L:{len(manual_longs)}) | "
        f"auto={auto_count} (S:{auto_shorts_needed}/L:{auto_longs_needed}) | "
        f"overflow={len(overflow)}"
    )
    
    return result


def calculate_all_channel_slots(channels, manual_queue_entries):
    """
    Calculate slot allocations for ALL channels.
    
    Args:
        channels: List of channel names (e.g., ['psyched', 'minted', ...])
        manual_queue_entries: All manual queue entries for today
    
    Returns:
        dict mapping channel_name → slot allocation
    """
    all_slots = {}
    
    for channel_name in channels:
        slots = calculate_slots_per_channel(channel_name, manual_queue_entries)
        all_slots[channel_name] = slots
    
    total_posts = sum(s["total_posts"] for s in all_slots.values())
    total_overflow = sum(len(s["overflow_to_tomorrow"]) for s in all_slots.values())
    
    logger.info(f"Total posts today: {total_posts} across {len(channels)} channels")
    if total_overflow > 0:
        logger.info(f"Overflow to tomorrow: {total_overflow} video(s)")
    
    return all_slots


# Channel names — must match channel_router CHANNEL_MAP values
ALL_CHANNELS = ["psyched", "minted", "vitals", "wired", "sage"]
