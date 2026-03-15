# src/safety/safety_gate.py
# Orchestrates safety layers in sequence
# Layer 1: Gemini pre-screen (music_risk from clip_detector)
# Layer 2: Duplicate check (posted.json overlap)
# (ACRCloud removed — trial expired)

from .duplicate_checker import is_duplicate, time_to_sec
import logging

logger = logging.getLogger("clipper.safety.gate")


def run_safety_checks(clip_path, source_video_id, start_time, end_time, gemini_music_risk):
    """
    Runs safety layers in sequence.
    
    Layer 1: Gemini pre-screen (music_risk from clip_detector)
    Layer 2: Duplicate check (posted.json overlap)
    
    Returns:
        {"passed": True, "final_path": path_to_safe_clip}
        {"passed": False, "reason": "..."}
    """
    # Convert time strings to seconds
    start_sec = time_to_sec(start_time)
    end_sec = time_to_sec(end_time)
    
    # --- LAYER 1: Gemini pre-screen result ---
    if gemini_music_risk == "high":
        logger.warning(f"SKIP [{source_video_id}] — Gemini flagged music_risk=high")
        return {
            "passed": False,
            "reason": "gemini_music_risk_high",
            "safety_checks": {
                "gemini_music_risk": "high",
                "duplicate_check": "skipped"
            }
        }
    
    # --- LAYER 2: Duplicate check ---
    if is_duplicate(source_video_id, start_sec, end_sec):
        logger.warning(f"SKIP [{source_video_id}] — duplicate segment detected")
        return {
            "passed": False,
            "reason": "duplicate_segment",
            "safety_checks": {
                "gemini_music_risk": gemini_music_risk or "none",
                "duplicate_check": "failed"
            }
        }
    
    return {
        "passed": True,
        "final_path": clip_path,
        "safety_checks": {
            "gemini_music_risk": gemini_music_risk or "none",
            "duplicate_check": "passed"
        }
    }


def final_safety_scan(final_rendered_path):
    """
    Called after full video render. Last gate before upload.
    Without ACRCloud, this just verifies the file exists.
    
    Returns:
        True if file exists (safe to upload)
        False if file missing
    """
    import os
    if not os.path.exists(final_rendered_path):
        logger.error(f"FINAL SCAN FAILED — file not found: {final_rendered_path}")
        return False
    
    logger.info(f"FINAL SCAN PASSED: {final_rendered_path}")
    return True
