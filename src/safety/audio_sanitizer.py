# src/safety/audio_sanitizer.py
# Mute detected music segments via FFmpeg — Layer 2

import subprocess
import logging

logger = logging.getLogger("clipper.safety.audio_sanitizer")


def mute_music_segments(input_path, output_path, segments):
    """
    Mute specific time segments in the audio track.
    segments: list of (start_sec, end_sec)
    Video stream is copied untouched.
    """
    if not segments:
        return input_path
    
    # Build FFmpeg volume filter for each segment
    filters = []
    for start, end in segments:
        filters.append(
            f"volume=enable='between(t,{start:.2f},{end:.2f})':volume=0"
        )
    
    filter_str = ",".join(filters)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-af", filter_str,
        "-c:v", "copy",
        output_path
    ]
    
    logger.info(f"Muting {len(segments)} music segment(s) in {input_path}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error(f"FFmpeg mute failed: {result.stderr}")
        raise RuntimeError(f"FFmpeg mute failed: {result.stderr}")
    
    logger.info(f"Audio sanitized: {output_path}")
    return output_path
