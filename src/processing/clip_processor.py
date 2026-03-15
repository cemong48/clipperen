# src/processing/clip_processor.py
# FFmpeg clip cutting with format-specific handling

import os
import subprocess
import logging

logger = logging.getLogger("clipper.processing.clip_processor")

TEMP_DIR = "temp"


def cut_clip(input_path, start_time, end_time, output_name="clip", format_type="long"):
    """
    Cut a clip from the input video at specified timestamps.
    
    Args:
        input_path: Path to source video
        start_time: Start time (MM:SS or HH:MM:SS)
        end_time: End time
        output_name: Base name for output file
        format_type: 'long' (16:9) or 'short' (9:16)
    
    Returns:
        Path to the cut clip.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    output_path = os.path.join(TEMP_DIR, f"{output_name}_cut.mp4")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ss", start_time,
        "-to", end_time,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path
    ]
    
    logger.info(f"Cutting clip: [{start_time} - {end_time}] → {output_path}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        logger.error(f"FFmpeg cut failed: {result.stderr}")
        raise RuntimeError(f"FFmpeg cut failed: {result.stderr}")
    
    logger.info(f"Clip cut successfully: {output_path}")
    return output_path


def convert_to_shorts_format(input_path, output_name="shorts"):
    """
    Convert a 16:9 clip to 9:16 (Shorts) format.
    Center-crops or letterboxes the video.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    output_path = os.path.join(TEMP_DIR, f"{output_name}_9x16.mp4")
    
    # Detect face for smart cropping, or center crop
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        ),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path
    ]
    
    logger.info(f"Converting to 9:16 format: {output_path}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        logger.error(f"Shorts conversion failed: {result.stderr}")
        raise RuntimeError(f"Shorts conversion failed: {result.stderr}")
    
    return output_path


def get_video_info(video_path):
    """Get video resolution, duration, and codec info via ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path
    ]
    
    import json
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        logger.error(f"ffprobe failed: {e}")
    return None
