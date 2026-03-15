# src/content/transcript_extractor.py
# Pull transcript via yt-dlp subtitles or Whisper fallback

import os
import subprocess
import logging
import json
import re

logger = logging.getLogger("clipper.content.transcript")

TEMP_DIR = "temp"


def extract_transcript_ytdlp(video_url, output_name="transcript"):
    """
    Attempt to pull existing subtitles/captions from YouTube via yt-dlp.
    Prefers manual English subs, falls back to auto-generated.
    
    Returns transcript text string, or None if unavailable.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    subtitle_path = os.path.join(TEMP_DIR, output_name)
    
    cmd = [
        "yt-dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-lang", "en",
        "--sub-format", "json3",
        "--skip-download",
        "--no-check-certificates",
        "-o", subtitle_path,
        video_url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Look for generated subtitle files
        for ext in [".en.json3", ".en.vtt", ".en.srt"]:
            sub_file = subtitle_path + ext
            if os.path.exists(sub_file):
                return parse_subtitle_file(sub_file)
        
        logger.info(f"No YouTube subtitles found for {video_url}")
        return None
        
    except Exception as e:
        logger.error(f"yt-dlp subtitle extraction failed: {e}")
        return None


def parse_subtitle_file(path):
    """Parse a subtitle file and extract plain text transcript."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if path.endswith(".json3"):
            return parse_json3_subtitles(content)
        elif path.endswith(".vtt") or path.endswith(".srt"):
            return parse_srt_vtt(content)
        
        return content
    except Exception as e:
        logger.error(f"Failed to parse subtitle file {path}: {e}")
        return None


def parse_json3_subtitles(content):
    """Parse YouTube JSON3 subtitle format."""
    try:
        data = json.loads(content)
        segments = []
        
        for event in data.get("events", []):
            text_parts = []
            for seg in event.get("segs", []):
                text = seg.get("utf8", "").strip()
                if text and text != "\n":
                    text_parts.append(text)
            if text_parts:
                start_ms = event.get("tStartMs", 0)
                segments.append({
                    "start": start_ms / 1000.0,
                    "text": " ".join(text_parts)
                })
        
        full_text = " ".join([s["text"] for s in segments])
        return full_text
    except Exception as e:
        logger.error(f"JSON3 parse error: {e}")
        return None


def parse_srt_vtt(content):
    """Parse SRT or VTT subtitle format to plain text."""
    # Remove timestamps and formatting
    lines = content.split("\n")
    text_lines = []
    
    for line in lines:
        line = line.strip()
        # Skip empty lines, numbers, timestamps
        if not line:
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        # Remove HTML tags
        line = re.sub(r'<[^>]+>', '', line)
        if line:
            text_lines.append(line)
    
    return " ".join(text_lines)


def extract_transcript_whisper(audio_path):
    """
    Transcribe audio using OpenAI Whisper (base model).
    Returns transcript with word-level timestamps.
    
    This runs locally — no API calls needed.
    """
    try:
        import whisper
        
        logger.info(f"Running Whisper transcription on: {audio_path}")
        model = whisper.load_model("base")
        result = model.transcribe(
            audio_path,
            word_timestamps=True,
            language="en"
        )
        
        return result
        
    except ImportError:
        logger.error("Whisper not installed. Install with: pip install openai-whisper")
        return None
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        return None


def extract_audio(video_path, output_path=None):
    """Extract audio track from video file using FFmpeg."""
    if output_path is None:
        output_path = video_path.rsplit(".", 1)[0] + ".wav"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
    except Exception as e:
        logger.error(f"Audio extraction failed: {e}")
    return None


def get_transcript(video_url, video_path=None):
    """
    Main entry point: get transcript for a video.
    Tries yt-dlp subtitles first, falls back to Whisper.
    
    Returns:
        dict with 'text' (full text) and optionally 'segments' (timestamped)
    """
    # Try YouTube subtitles first (free, fast)
    text = extract_transcript_ytdlp(video_url)
    if text:
        logger.info("Got transcript from YouTube subtitles")
        return {"text": text, "source": "youtube_subs", "segments": None}
    
    # Fall back to Whisper (local, slower)
    if video_path and os.path.exists(video_path):
        audio_path = extract_audio(video_path)
        if audio_path:
            whisper_result = extract_transcript_whisper(audio_path)
            if whisper_result:
                logger.info("Got transcript from Whisper")
                return {
                    "text": whisper_result.get("text", ""),
                    "source": "whisper",
                    "segments": whisper_result.get("segments", [])
                }
    
    logger.warning(f"Could not get transcript for {video_url}")
    return {"text": "", "source": "none", "segments": None}
