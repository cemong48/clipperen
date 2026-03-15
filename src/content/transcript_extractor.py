# src/content/transcript_extractor.py
# Pull transcript via youtube-transcript-api (primary) or yt-dlp (fallback)

import os
import subprocess
import logging
import json
import re

logger = logging.getLogger("clipper.content.transcript")

TEMP_DIR = "temp"


def extract_transcript_api(video_id):
    """
    Primary method: Use youtube-transcript-api to fetch transcript.
    This is lightweight, works in CI/GitHub Actions without cookies.
    
    Tries in order:
    1. Manual English subtitles
    2. Auto-generated English subtitles
    3. Any available language (then note for later translation)
    
    Returns transcript text string, or None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Try to get English transcript (manual first, then auto-generated)
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Priority 1: Manual English
            try:
                transcript = transcript_list.find_manually_created_transcript(['en'])
                entries = transcript.fetch()
                text = " ".join([entry.text for entry in entries])
                logger.info(f"Got manual English transcript for {video_id}")
                return text
            except Exception:
                pass
            
            # Priority 2: Auto-generated English
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
                entries = transcript.fetch()
                text = " ".join([entry.text for entry in entries])
                logger.info(f"Got auto-generated English transcript for {video_id}")
                return text
            except Exception:
                pass
            
            # Priority 3: Any language, translate to English
            try:
                for transcript in transcript_list:
                    try:
                        translated = transcript.translate('en')
                        entries = translated.fetch()
                        text = " ".join([entry.text for entry in entries])
                        logger.info(f"Got translated transcript for {video_id} (from {transcript.language_code})")
                        return text
                    except Exception:
                        continue
            except Exception:
                pass
                
        except Exception as e:
            logger.debug(f"transcript_list failed for {video_id}: {e}")
        
        # Simpler fallback: just try get_transcript directly
        try:
            entries = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            text = " ".join([entry.text for entry in entries])
            logger.info(f"Got transcript via get_transcript for {video_id}")
            return text
        except Exception:
            pass
        
        # Try auto-generated
        try:
            entries = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            text = " ".join([entry.text for entry in entries])
            return text
        except Exception:
            pass
            
        logger.info(f"No transcript available via API for {video_id}")
        return None
        
    except ImportError:
        logger.warning("youtube-transcript-api not installed. Install with: pip install youtube-transcript-api")
        return None
    except Exception as e:
        logger.error(f"Transcript API error for {video_id}: {e}")
        return None


def extract_transcript_ytdlp(video_url, output_name="transcript"):
    """
    Fallback method: Pull subtitles via yt-dlp.
    May fail in CI/GitHub Actions due to bot detection.
    
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
        "--no-warnings",
        "--quiet",
        "-o", subtitle_path,
        video_url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Look for generated subtitle files
        for ext in [".en.json3", ".en.vtt", ".en.srt"]:
            sub_file = subtitle_path + ext
            if os.path.exists(sub_file):
                text = parse_subtitle_file(sub_file)
                # Clean up the subtitle file
                try:
                    os.remove(sub_file)
                except Exception:
                    pass
                return text
        
        logger.info(f"No YouTube subtitles found via yt-dlp for {video_url}")
        return None
        
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp subtitle extraction timed out for {video_url}")
        return None
    except FileNotFoundError:
        logger.warning("yt-dlp not found in PATH")
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
    Last resort: Transcribe audio using OpenAI Whisper (base model).
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


def _extract_video_id(video_url):
    """Extract video ID from various YouTube URL formats."""
    if not video_url:
        return None
    
    # Direct video ID (no URL)
    if len(video_url) == 11 and not video_url.startswith("http"):
        return video_url
    
    # Standard URL patterns
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, video_url)
        if match:
            return match.group(1)
    
    return None


def get_transcript(video_url, video_path=None):
    """
    Main entry point: get transcript for a video.
    
    Priority order:
    1. youtube-transcript-api (fast, works in CI)
    2. yt-dlp subtitles (fallback)
    3. Whisper local transcription (last resort, needs audio file)
    
    Returns:
        dict with 'text' (full text), 'source', and optionally 'segments'
    """
    video_id = _extract_video_id(video_url)
    
    # Method 1: youtube-transcript-api (primary — works in GitHub Actions)
    if video_id:
        text = extract_transcript_api(video_id)
        if text and len(text) >= 50:
            logger.info(f"Got transcript from youtube-transcript-api ({len(text)} chars)")
            return {"text": text, "source": "youtube_transcript_api", "segments": None}
    
    # Method 2: yt-dlp subtitles (fallback)
    text = extract_transcript_ytdlp(video_url)
    if text and len(text) >= 50:
        logger.info(f"Got transcript from yt-dlp ({len(text)} chars)")
        return {"text": text, "source": "youtube_subs", "segments": None}
    
    # Method 3: Whisper (last resort — needs downloaded audio)
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
