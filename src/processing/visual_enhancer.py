# src/processing/visual_enhancer.py
# FFmpeg visual layers: hook text, progress bar, watermark, subtitles

import os
import subprocess
import logging

logger = logging.getLogger("clipper.processing.visual_enhancer")

TEMP_DIR = "temp"


def enhance_long_clip(input_path, output_path, source_channel_name,
                       subtitle_path=None, channel_logo_path=None):
    """
    Apply visual enhancements for Long Clips (16:9).
    
    Layers (bottom to top):
    1. Original video (full width, 1920x1080 or original resolution)
    2. Progress bar (2px height, white, bottom of frame)
    3. English subtitle (bold, white, black outline, bottom center)
    4. Source watermark (top right, 30% opacity): "📺 Source: @ChannelName"
    5. Channel logo (bottom left, small) — optional
    """
    os.makedirs(os.path.dirname(output_path) or TEMP_DIR, exist_ok=True)
    
    # Build filter chain
    filters = []
    
    # Progress bar (white, 2px, bottom)
    filters.append(
        "drawbox=x=0:y=ih-2:w=iw*t/duration:h=2:color=white:t=fill"
    )
    
    # Source watermark (top right, 30% opacity)
    safe_name = source_channel_name.replace("'", "\\'")
    filters.append(
        f"drawtext=text='Source\\: @{safe_name}':"
        f"fontsize=20:fontcolor=white@0.3:"
        f"x=w-tw-20:y=20"
    )
    
    filter_str = ",".join(filters)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "copy",
        output_path
    ]
    
    # Add subtitle burn-in if available
    if subtitle_path and os.path.exists(subtitle_path):
        # Replace filter to include subtitles
        sub_filter = (
            f"subtitles={subtitle_path}:force_style='"
            f"FontName=Arial,FontSize=22,PrimaryColour=&HFFFFFF,"
            f"OutlineColour=&H000000,Outline=2,Bold=1'"
        )
        filter_str = f"{filter_str},{sub_filter}"
        cmd[cmd.index("-vf") + 1] = filter_str
    
    logger.info(f"Enhancing long clip: {output_path}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    
    if result.returncode != 0:
        logger.error(f"Long clip enhancement failed: {result.stderr}")
        raise RuntimeError(f"Enhancement failed: {result.stderr}")
    
    return output_path


def enhance_shorts_clip(input_path, output_path, hook_text,
                         source_channel_name, subtitle_path=None):
    """
    Apply visual enhancements for Shorts (9:16).
    
    Layers (bottom to top):
    1. Original video (cropped/padded to 9:16, 1080x1920)
    2. Progress bar (3px, bottom)
    3. Hook text overlay (0-3 seconds only)
    4. Word-by-word subtitle (bottom third)
    5. Source credit (top, small)
    """
    os.makedirs(os.path.dirname(output_path) or TEMP_DIR, exist_ok=True)
    
    # Build filter chain
    filters = []
    
    # Progress bar (3px, bottom)
    filters.append(
        "drawbox=x=0:y=ih-3:w=iw*t/duration:h=3:color=white:t=fill"
    )
    
    # Hook text (0-3 seconds, centered, semi-transparent bg)
    if hook_text:
        safe_hook = hook_text.replace("'", "\\'")
        filters.append(
            f"drawtext=text='{safe_hook}':"
            f"fontsize=48:fontcolor=white:"
            f"x=(w-tw)/2:y=(h-th)/2:"
            f"enable='between(t,0,3)':"
            f"box=1:boxcolor=black@0.5:boxborderw=15"
        )
    
    # Source credit (top center, small)
    safe_name = source_channel_name.replace("'", "\\'")
    filters.append(
        f"drawtext=text='Source\\: @{safe_name}':"
        f"fontsize=16:fontcolor=white@0.5:"
        f"x=(w-tw)/2:y=30"
    )
    
    filter_str = ",".join(filters)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "copy",
        output_path
    ]
    
    # Add subtitle burn-in if available
    if subtitle_path and os.path.exists(subtitle_path):
        sub_filter = (
            f"subtitles={subtitle_path}:force_style='"
            f"FontName=Arial,FontSize=24,PrimaryColour=&HFFFFFF,"
            f"OutlineColour=&H000000,Outline=2,Bold=1,"
            f"MarginV=80'"
        )
        filter_str = f"{filter_str},{sub_filter}"
        cmd[cmd.index("-vf") + 1] = filter_str
    
    logger.info(f"Enhancing shorts clip: {output_path}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    
    if result.returncode != 0:
        logger.error(f"Shorts enhancement failed: {result.stderr}")
        raise RuntimeError(f"Enhancement failed: {result.stderr}")
    
    return output_path


def add_watermark_text(input_path, output_path, watermark_text):
    """
    Burn watermark text into video frame (bottom-left).
    Used for affiliate/Whop requirements.
    """
    if not watermark_text:
        return input_path
    
    safe_text = watermark_text.replace("'", "\\'")
    
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", (
            f"drawtext=text='{safe_text}':"
            f"fontsize=28:fontcolor=white@0.6:"
            f"x=20:y=h-th-20:"
            f"box=1:boxcolor=black@0.3:boxborderw=6"
        ),
        "-codec:a", "copy",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        logger.error(f"Watermark failed: {result.stderr}")
        raise RuntimeError(f"Watermark failed: {result.stderr}")
    
    logger.info(f"Watermark added: {output_path}")
    return output_path
