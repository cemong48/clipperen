# src/processing/audio_mixer.py
# Lo-fi background music at 10% volume during silence gaps

import os
import subprocess
import random
import logging

logger = logging.getLogger("clipper.processing.audio_mixer")

MUSIC_DIR = "assets/music"
TEMP_DIR = "temp"


def get_random_lofi_track():
    """Pick a random lo-fi track from assets/music/."""
    if not os.path.exists(MUSIC_DIR):
        logger.warning(f"Music directory not found: {MUSIC_DIR}")
        return None
    
    tracks = [
        f for f in os.listdir(MUSIC_DIR)
        if f.endswith((".mp3", ".wav", ".ogg"))
    ]
    
    if not tracks:
        logger.warning("No music tracks found in assets/music/")
        return None
    
    track = random.choice(tracks)
    return os.path.join(MUSIC_DIR, track)


def mix_background_music(input_path, output_path, volume=0.10,
                          check_restrictions=None):
    """
    Mix lo-fi background music at specified volume.
    Only plays during silence gaps > 2 seconds.
    
    Args:
        input_path: Path to the video file
        output_path: Path for output
        volume: Background music volume (default 10%)
        check_restrictions: list of restrictions from whitelist entry
    
    Returns:
        Path to mixed video, or input_path if no music available.
    """
    # Check whitelist restrictions
    if check_restrictions and "no_background_music" in check_restrictions:
        logger.info("Background music disabled by channel restriction.")
        return input_path
    
    music_track = get_random_lofi_track()
    if not music_track:
        return input_path
    
    os.makedirs(os.path.dirname(output_path) or TEMP_DIR, exist_ok=True)
    
    # FFmpeg: mix background music at low volume
    # The background music loops and plays at the specified volume
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-stream_loop", "-1",  # Loop the music
        "-i", music_track,
        "-filter_complex", (
            f"[1:a]volume={volume}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        ),
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_path
    ]
    
    logger.info(f"Mixing background music ({volume*100:.0f}% volume): {music_track}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error(f"Audio mix failed: {result.stderr}")
            return input_path  # Fallback: return without music
        
        logger.info(f"Background music mixed: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Audio mixing error: {e}")
        return input_path
