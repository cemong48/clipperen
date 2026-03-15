# src/main.py
# Main pipeline orchestrator — ties all modules together
# Runs daily via GitHub Actions (daily_pipeline.yml)

import os
import sys
import json
import logging
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.logger import setup_logger, get_logger
from src.utils.file_lock import read_json, write_json, append_to_json_list
from src.utils.dry_run import is_dry_run
from src.utils.gemini_client import set_active_channel

from src.discovery.whitelist_manager import get_active_channels, get_whitelist_entry
from src.discovery.channel_scanner import get_latest_videos, get_video_details

from src.content.video_fetcher import download_segment, cleanup_temp
from src.content.transcript_extractor import get_transcript, check_video_playability
from src.content.clip_detector import detect_clips_for_video
from src.content.format_classifier import classify_source_format, parse_iso_duration

from src.router.channel_router import route_video, process_unclassified_overrides
from src.scheduler.slot_manager import calculate_all_channel_slots, ALL_CHANNELS
from src.scheduler.random_offset import generate_daily_schedule, assign_videos_to_slots

from src.safety.safety_gate import run_safety_checks, final_safety_scan
from src.safety.duplicate_checker import is_video_already_processed

from src.processing.clip_processor import cut_clip, convert_to_shorts_format
from src.processing.subtitle_generator import generate_bilingual_subtitles
from src.processing.visual_enhancer import enhance_long_clip, enhance_shorts_clip, add_watermark_text
from src.processing.thumbnail_generator import generate_thumbnail
from src.processing.audio_mixer import mix_background_music

from src.upload.youtube_uploader import upload_video, upload_subtitles, post_pinned_comment
from src.upload.metadata_generator import generate_metadata, resolve_affiliate_requirements

logger = get_logger("main")

# Paths
SETTINGS_PATH = "config/settings.json"
WHITELIST_PATH = "config/whitelist.json"
SEEDS_PATH = "config/seeds.json"
POSTED_PATH = "database/posted.json"
CANDIDATES_PATH = "database/candidates.json"
MANUAL_QUEUE_PATH = "manual_queue/queue.json"
TEMP_DIR = "temp"


def load_manual_queue():
    """Load and process manual queue entries."""
    queue = read_json(MANUAL_QUEUE_PATH, default={"entries": []})
    entries = queue.get("entries", [])
    if entries:
        logger.info(f"Manual queue: {len(entries)} entry(s) found")
    return entries


def clear_manual_queue():
    """Clear processed manual queue entries."""
    write_json(MANUAL_QUEUE_PATH, {"entries": []})
    logger.info("Manual queue cleared.")


def route_manual_videos(manual_entries):
    """Route all manual queue entries to their target channels."""
    routed = []
    for entry in manual_entries:
        video_meta = {
            "url": entry.get("url", ""),
            "title": entry.get("notes", "Manual entry"),
            "description": "",
            "transcript": ""
        }
        
        routing = route_video(video_meta, queue_entry=entry)
        
        if routing["action"] != "hold":
            routed.append({
                **entry,
                "target_channel": routing["channel"],
                "routing_method": routing["routing_method"]
            })
        else:
            logger.warning(f"Manual entry held: {entry.get('url', 'Unknown')}")
    
    return routed


def discover_candidates_for_channel(channel_entry, settings, target_channel=None):
    """
    Discover clip candidates from a whitelisted channel.
    Pulls latest videos, extracts transcripts, runs Gemini clip detection.
    
    Args:
        target_channel: Our channel name (psyched/minted/etc) for API key selection
    """
    channel_id = channel_entry.get("channel_id", "")
    channel_name = channel_entry.get("channel_name", "Unknown")
    restrictions = channel_entry.get("restrictions", [])
    
    scan_days = settings.get("content", {}).get("scan_videos_last_days", 7)
    
    logger.info(f"Scanning channel: {channel_name}")
    
    videos = get_latest_videos(channel_id, max_results=5, days_back=scan_days, channel_name=target_channel)
    candidates = []
    
    for video_item in videos:
        video_id = video_item.get("id", {}).get("videoId", "")
        if not video_id:
            continue
        
        # Skip already processed
        existing = is_video_already_processed(video_id, POSTED_PATH)
        if existing:
            logger.info(f"  Skipping {video_id} — already processed")
            continue
        
        # Get video details
        details = get_video_details(video_id, channel_name=target_channel)
        if not details:
            continue
        
        snippet = details.get("snippet", {})
        content = details.get("contentDetails", {})
        status = details.get("status", {})
        
        # Skip restricted videos
        if status.get("privacyStatus") != "public":
            continue
        if content.get("contentRating", {}).get("ytRating") == "ytAgeRestricted":
            continue
        
        # Get duration and classify format
        duration_iso = content.get("duration", "PT0S")
        duration_sec = parse_iso_duration(duration_iso)
        duration_min = duration_sec / 60.0
        
        format_class = classify_source_format(duration_min)
        if format_class["skip"]:
            logger.info(f"  Skipping {video_id} — {format_class['reason']}")
            continue
        
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Check playability BEFORE trying transcript (skip unavailable videos early)
        if not check_video_playability(video_id):
            logger.info(f"  Skipping {video_id} — video not playable/unavailable")
            continue
        
        # Get transcript
        transcript_data = get_transcript(video_url)
        transcript_text = transcript_data.get("text", "")
        
        if not transcript_text or len(transcript_text) < 100:
            logger.info(f"  Skipping {video_id} — insufficient transcript")
            continue
        
        candidates.append({
            "video_id": video_id,
            "video_url": video_url,
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "channel_id": channel_id,
            "channel_name": channel_name,
            "duration_minutes": duration_min,
            "transcript": transcript_text,
            "can_long": format_class["can_long"],
            "can_short": format_class["can_short"],
            "restrictions": restrictions,
            "whitelist_entry": channel_entry
        })
        
        # Rate limit
        time.sleep(1)
    
    logger.info(f"  Found {len(candidates)} candidate(s) from {channel_name}")
    return candidates


def process_single_video(candidate, clip_info, format_type, channel_name):
    """
    Full processing pipeline for a single video clip.
    Download → Safety → Process → Upload
    """
    video_id = candidate["video_id"]
    video_url = candidate["video_url"]
    creator_name = candidate["channel_name"]
    whitelist_entry = candidate.get("whitelist_entry", {})
    restrictions = candidate.get("restrictions", [])
    
    start_time = clip_info.get("start_time", "0:00")
    end_time = clip_info.get("end_time", "0:00")
    music_risk = clip_info.get("music_risk", "none")
    
    unique_id = f"{video_id}_{format_type}_{int(time.time())}"
    
    # Step 1: Download segment
    logger.info(f"Step 1: Downloading [{start_time} - {end_time}]")
    clip_path = download_segment(video_url, start_time, end_time, output_name=unique_id)
    if not clip_path:
        return None
    
    # Step 2: Safety checks (Layers 1-3)
    logger.info("Step 2: Running safety checks")
    safety_result = run_safety_checks(clip_path, video_id, start_time, end_time, music_risk)
    if not safety_result["passed"]:
        logger.warning(f"Safety check failed: {safety_result['reason']}")
        return None
    
    clip_path = safety_result.get("final_path", clip_path)
    
    # Step 3: Format conversion (Shorts → 9:16)
    if format_type == "short":
        logger.info("Step 3: Converting to Shorts format (9:16)")
        clip_path = convert_to_shorts_format(clip_path, output_name=unique_id)
    
    # Step 4: Generate subtitles
    logger.info("Step 4: Generating bilingual subtitles")
    from src.content.transcript_extractor import extract_audio
    audio_path = extract_audio(clip_path)
    subtitles = {"english_srt": None, "indonesian_srt": None}
    if audio_path:
        subtitles = generate_bilingual_subtitles(audio_path, output_dir=TEMP_DIR)
    
    # Step 5: Visual enhancement
    logger.info("Step 5: Applying visual enhancements")
    enhanced_path = os.path.join(TEMP_DIR, f"{unique_id}_enhanced.mp4")
    
    if format_type == "long":
        enhance_long_clip(
            clip_path, enhanced_path, creator_name,
            subtitle_path=subtitles.get("english_srt")
        )
    else:
        hook_text = clip_info.get("hook_text", "")
        enhance_shorts_clip(
            clip_path, enhanced_path, hook_text, creator_name,
            subtitle_path=subtitles.get("english_srt")
        )
    
    # Step 5b: Add watermark if required
    affiliate_reqs = resolve_affiliate_requirements(whitelist_entry)
    watermark = affiliate_reqs.get("watermark_text")
    if watermark:
        watermarked_path = os.path.join(TEMP_DIR, f"{unique_id}_watermark.mp4")
        enhanced_path = add_watermark_text(enhanced_path, watermarked_path, watermark)
    
    # Step 6: Audio mixing (lo-fi background)
    logger.info("Step 6: Mixing background music")
    final_path = os.path.join(TEMP_DIR, f"{unique_id}_final.mp4")
    final_path = mix_background_music(
        enhanced_path, final_path,
        check_restrictions=restrictions
    )
    
    # Step 7: Final safety scan (Layer 4)
    logger.info("Step 7: Final safety scan")
    if not final_safety_scan(final_path):
        logger.error("Final safety scan FAILED — not uploading")
        return None
    
    # Step 8: Generate thumbnail
    logger.info("Step 8: Generating thumbnail")
    thumb_path = os.path.join(TEMP_DIR, f"{unique_id}_thumb.jpg")
    generate_thumbnail(clip_path, clip_info.get("title", "Clip"), thumb_path)
    
    # Step 9: Generate metadata
    logger.info("Step 9: Generating metadata")
    metadata = generate_metadata(
        clip_info=clip_info,
        creator_name=creator_name,
        original_url=video_url,
        format_type=format_type,
        whitelist_entry=whitelist_entry
    )
    
    # Step 10: Upload
    logger.info("Step 10: Uploading to YouTube")
    upload_result = upload_video(final_path, metadata, channel_name)
    
    yt_video_id = upload_result.get("video_id", "")
    
    # Step 11: Upload subtitles
    if yt_video_id and subtitles.get("english_srt"):
        upload_subtitles(yt_video_id, subtitles["english_srt"], "en", "English", channel_name)
    if yt_video_id and subtitles.get("indonesian_srt"):
        upload_subtitles(yt_video_id, subtitles["indonesian_srt"], "id", "Indonesian", channel_name)
    
    # Step 12: Post pinned comment if required
    pinned_comment = metadata.get("pinned_comment")
    if yt_video_id and pinned_comment:
        post_pinned_comment(yt_video_id, pinned_comment, channel_name)
    
    # Step 13: Record in posted.json
    posted_entry = {
        "video_id": yt_video_id,
        "source_channel_id": candidate["channel_id"],
        "source_video_id": video_id,
        "start_time": start_time,
        "end_time": end_time,
        "format": format_type,
        "posted_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "system": "auto",
        "whop_program_id": whitelist_entry.get("whop_program_id"),
        "title": metadata.get("title", ""),
        "target_channel": channel_name,
        "safety_checks": safety_result.get("safety_checks", {}),
        "auto_update_count": 0,
        "initial_metrics": {}
    }
    
    append_to_json_list(POSTED_PATH, posted_entry)
    logger.info(f"✅ Posted: {metadata.get('title', 'Unknown')} → {channel_name}")
    
    return posted_entry


def run_daily_pipeline():
    """
    Main daily pipeline. Runs once per day per channel.
    
    Flow:
    1. Load settings & manual queue
    2. Route manual videos to channels
    3. For each of 5 channels:
       a. Calculate slot allocation
       b. Discover candidates from whitelisted sources
       c. Run Gemini clip detection
       d. Process & upload (safety → render → upload)
    4. Clean up temp files
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info(f"DAILY PIPELINE START — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    logger.info(f"DRY_RUN: {is_dry_run()}")
    logger.info("=" * 60)
    
    # Log credential status for diagnostics
    for idx in range(1, 6):
        yt_key = "✅" if os.environ.get(f"YOUTUBE_API_KEY_{idx}") else "❌"
        gemini = "✅" if os.environ.get(f"GEMINI_API_KEY_{idx}") else "❌"
        client = "✅" if os.environ.get(f"YOUTUBE_CLIENT_SECRET_{idx}") else "❌"
        token = "✅" if os.environ.get(f"YOUTUBE_REFRESH_TOKEN_{idx}") else "❌"
        logger.info(f"Credentials #{idx}: YT_KEY={yt_key} GEMINI={gemini} CLIENT={client} TOKEN={token}")
    
    settings = read_json(SETTINGS_PATH, default={})
    
    # Check seed verification
    verification_report = "logs/seed_verification_report.json"
    if not os.path.exists(verification_report):
        logger.warning("Seeds not verified. Run scripts/verify_seeds.py first.")
    
    # Step 1: Load manual queue
    manual_entries = load_manual_queue()
    
    # Step 2: Route manual entries
    routed_manual = route_manual_videos(manual_entries)
    
    # Step 3: Process any unclassified overrides from previous runs
    resolved = process_unclassified_overrides()
    
    # Step 4: Calculate slots for all channels
    all_slots = calculate_all_channel_slots(ALL_CHANNELS, routed_manual)
    
    total_posted = 0
    total_failed = 0
    
    # Step 5: Process each channel
    for channel_name in ALL_CHANNELS:
        logger.info(f"\n{'='*40}")
        logger.info(f"CHANNEL: {channel_name}")
        logger.info(f"{'='*40}")
        
        # Switch Gemini API key to this channel's key
        set_active_channel(channel_name)
        
        slots = all_slots.get(channel_name, {})
        shorts_needed = slots.get("auto_shorts_needed", 2)
        longs_needed = slots.get("auto_longs_needed", 2)
        
        # Process manual videos for this channel first
        manual_for_channel = slots.get("manual_videos", [])
        for mv in manual_for_channel:
            logger.info(f"Processing manual video: {mv.get('url', 'Unknown')}")
            try:
                # Manual videos come with pre-defined timestamps
                candidate = {
                    "video_id": mv.get("url", "").split("v=")[-1].split("&")[0],
                    "video_url": mv.get("url", ""),
                    "title": mv.get("notes", "Manual clip"),
                    "description": "",
                    "channel_id": "",
                    "channel_name": "Manual",
                    "transcript": "",
                    "restrictions": [],
                    "whitelist_entry": {}
                }
                
                clip_info = {
                    "start_time": mv.get("start_time", "0:00"),
                    "end_time": mv.get("end_time", "1:00"),
                    "title": mv.get("title_override") or mv.get("notes", "Clip"),
                    "music_risk": "none",
                    "hook_text": "",
                    "format": mv.get("format", "long")
                }
                
                result = process_single_video(
                    candidate, clip_info,
                    mv.get("format", "long"), channel_name
                )
                if result:
                    total_posted += 1
                else:
                    total_failed += 1
            except Exception as e:
                logger.error(f"Manual video failed: {e}")
                total_failed += 1
        
        # Discover auto candidates — only scan whitelist channels for THIS target channel
        active_channels = get_active_channels(WHITELIST_PATH)
        
        # Filter to only channels assigned to this target channel
        my_channels = [
            ch for ch in active_channels
            if ch.get("target_channel") == channel_name
        ]
        logger.info(f"Scanning {len(my_channels)} source(s) for {channel_name}")
        
        all_candidates = []
        for wl_channel in my_channels:
            candidates = discover_candidates_for_channel(wl_channel, settings, target_channel=channel_name)
            all_candidates.extend(candidates)
        
        # Process auto shorts
        shorts_posted = 0
        for candidate in all_candidates:
            if shorts_posted >= shorts_needed:
                break
            if not candidate.get("can_short"):
                continue
            
            try:
                clip_info = detect_clips_for_video(
                    candidate["transcript"],
                    candidate["duration_minutes"],
                    needs_long=False, needs_short=True
                )
                
                if clip_info.get("short"):
                    # Route the video
                    routing = route_video({
                        "title": candidate["title"],
                        "description": candidate["description"],
                        "transcript": candidate["transcript"]
                    })
                    
                    if routing["channel"] == channel_name and routing["action"] != "hold":
                        result = process_single_video(
                            candidate, clip_info["short"],
                            "short", channel_name
                        )
                        if result:
                            shorts_posted += 1
                            total_posted += 1
                        else:
                            total_failed += 1
            except Exception as e:
                logger.error(f"Auto short processing failed: {e}")
                total_failed += 1
        
        # Process auto longs
        longs_posted = 0
        for candidate in all_candidates:
            if longs_posted >= longs_needed:
                break
            if not candidate.get("can_long"):
                continue
            
            try:
                clip_info = detect_clips_for_video(
                    candidate["transcript"],
                    candidate["duration_minutes"],
                    needs_long=True, needs_short=False
                )
                
                if clip_info.get("long"):
                    routing = route_video({
                        "title": candidate["title"],
                        "description": candidate["description"],
                        "transcript": candidate["transcript"]
                    })
                    
                    if routing["channel"] == channel_name and routing["action"] != "hold":
                        result = process_single_video(
                            candidate, clip_info["long"],
                            "long", channel_name
                        )
                        if result:
                            longs_posted += 1
                            total_posted += 1
                        else:
                            total_failed += 1
            except Exception as e:
                logger.error(f"Auto long processing failed: {e}")
                total_failed += 1
        
        logger.info(
            f"Channel {channel_name} done: "
            f"shorts={shorts_posted}/{shorts_needed}, "
            f"longs={longs_posted}/{longs_needed}"
        )
    
    # Step 6: Clear manual queue after processing
    if manual_entries:
        clear_manual_queue()
    
    # Step 7: Handle overflow (save to tomorrow's queue)
    for channel_name in ALL_CHANNELS:
        overflow = all_slots.get(channel_name, {}).get("overflow_to_tomorrow", [])
        if overflow:
            logger.info(f"Saving {len(overflow)} overflow video(s) for {channel_name}")
            queue = read_json(MANUAL_QUEUE_PATH, default={"entries": []})
            queue["entries"].extend(overflow)
            write_json(MANUAL_QUEUE_PATH, queue)
    
    # Step 8: Clean up
    cleanup_temp()
    
    elapsed = time.time() - start_time
    logger.info(f"\n{'='*60}")
    logger.info(f"DAILY PIPELINE COMPLETE")
    logger.info(f"  Posted: {total_posted}")
    logger.info(f"  Failed: {total_failed}")
    logger.info(f"  Duration: {elapsed/60:.1f} minutes")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    run_daily_pipeline()
