# src/safety/safety_gate.py
# Orchestrates all 4 safety layers in sequence

from .acr_checker import scan_audio
from .audio_sanitizer import mute_music_segments
from .duplicate_checker import is_duplicate, time_to_sec
import logging

logger = logging.getLogger("clipper.safety.gate")


def run_safety_checks(clip_path, source_video_id, start_time, end_time, gemini_music_risk):
    """
    Runs all 4 safety layers in sequence.
    
    Layer 1: Gemini pre-screen (music_risk from clip_detector)
    Layer 2: Duplicate check (posted.json overlap)
    Layer 3: ACRCloud scan on raw clip
    Layer 4: (called separately after render via final_safety_scan)
    
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
                "duplicate_check": "skipped",
                "acr_scan_raw": "skipped",
                "muted_segments": [],
                "acr_scan_final": "skipped"
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
                "duplicate_check": "failed",
                "acr_scan_raw": "skipped",
                "muted_segments": [],
                "acr_scan_final": "skipped"
            }
        }
    
    # --- LAYER 3: ACRCloud scan on raw clip ---
    acr_result = scan_audio(clip_path)
    
    acr_raw_status = "clean"
    muted_segments = []
    
    if acr_result["action"] == "skip":
        logger.warning(f"SKIP [{source_video_id}] — music detected > 10s, not salvageable")
        return {
            "passed": False,
            "reason": "music_too_extensive",
            "safety_checks": {
                "gemini_music_risk": gemini_music_risk or "none",
                "duplicate_check": "passed",
                "acr_scan_raw": "music_detected_skip",
                "muted_segments": [],
                "acr_scan_final": "skipped"
            }
        }
    
    if acr_result["action"] == "mute_segments":
        logger.info(f"MUTE segments in [{source_video_id}] — {acr_result['music_segments']}")
        sanitized_path = clip_path.replace(".mp4", "_sanitized.mp4")
        clip_path = mute_music_segments(clip_path, sanitized_path, acr_result["music_segments"])
        acr_raw_status = "music_muted"
        muted_segments = acr_result["music_segments"]
    
    # --- LAYER 4: ACRCloud final scan after render ---
    # (called separately in the pipeline after full render + lo-fi mix)
    # See: final_safety_scan()
    
    return {
        "passed": True,
        "final_path": clip_path,
        "safety_checks": {
            "gemini_music_risk": gemini_music_risk or "none",
            "duplicate_check": "passed",
            "acr_scan_raw": acr_raw_status,
            "muted_segments": muted_segments,
            "acr_scan_final": "pending"
        }
    }


def final_safety_scan(final_rendered_path):
    """
    Called after full video render. Last gate before upload.
    Layer 4: ACRCloud scan on the FINAL rendered file.
    
    Returns:
        True if clean (safe to upload)
        False if music still detected
    """
    acr_result = scan_audio(final_rendered_path)
    
    if acr_result["action"] in ("skip", "mute_segments"):
        logger.error(
            f"FINAL SCAN FAILED [{final_rendered_path}] — "
            f"music still detected after render"
        )
        return False
    
    logger.info(f"FINAL SCAN PASSED: {final_rendered_path}")
    return True
