# src/content/video_fetcher.py
# yt-dlp wrapper for downloading video segments

import os
import subprocess
import logging
import shutil

logger = logging.getLogger("clipper.content.fetcher")

TEMP_DIR = "temp"


def ensure_temp_dir():
    """Create temp directory if it doesn't exist."""
    os.makedirs(TEMP_DIR, exist_ok=True)


def download_segment(video_url, start_time, end_time, output_name="raw_clip"):
    """
    Download a specific segment of a YouTube video using yt-dlp.
    
    Args:
        video_url: Full YouTube video URL
        start_time: Start timestamp in MM:SS or HH:MM:SS format
        end_time: End timestamp in MM:SS or HH:MM:SS format
        output_name: Base name for the output file
    
    Returns:
        Path to downloaded clip, or None if failed.
    """
    ensure_temp_dir()
    output_path = os.path.join(TEMP_DIR, f"{output_name}.mp4")
    
    cmd = [
        "yt-dlp",
        "--download-sections", f"*{start_time}-{end_time}",
        "--format", "bestvideo[height<=1080]+bestaudio/best",
        "--merge-output-format", "mp4",
        "--no-check-certificates",
        "--socket-timeout", "30",
        "--retries", "3",
        "-o", output_path,
        video_url
    ]
    
    logger.info(f"Downloading segment: {video_url} [{start_time} - {end_time}]")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error(f"yt-dlp failed: {result.stderr}")
            return None
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"Downloaded: {output_path} ({file_size / 1024 / 1024:.1f} MB)")
            return output_path
        else:
            logger.error(f"Download completed but file not found: {output_path}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error(f"Download timed out for {video_url}")
        return None
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None


def download_full_video(video_url, output_name="full_video"):
    """
    Download full video (used when transcript extraction needs it).
    """
    ensure_temp_dir()
    output_path = os.path.join(TEMP_DIR, f"{output_name}.mp4")
    
    cmd = [
        "yt-dlp",
        "--format", "bestvideo[height<=720]+bestaudio/best",
        "--merge-output-format", "mp4",
        "--no-check-certificates",
        "--socket-timeout", "30",
        "--retries", "3",
        "-o", output_path,
        video_url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
    except Exception as e:
        logger.error(f"Full video download error: {e}")
    return None


def get_video_duration(video_url):
    """Get video duration in seconds using yt-dlp."""
    cmd = [
        "yt-dlp",
        "--print", "duration",
        "--no-check-certificates",
        video_url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Duration check error: {e}")
    return None


def cleanup_temp():
    """Remove all temporary files after processing."""
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        logger.info("Temp directory cleaned up.")
    ensure_temp_dir()
