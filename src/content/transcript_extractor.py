# src/content/transcript_extractor.py
# Pull transcript via YouTube Data API captions / youtube-transcript-api / yt-dlp
# Designed to work reliably in GitHub Actions CI environment

import os
import subprocess
import logging
import json
import re
import requests
from http.cookiejar import MozillaCookieJar

logger = logging.getLogger("clipper.content.transcript")

TEMP_DIR = "temp"

# Global cookies path — set by pipeline based on current channel index
_current_cookies_path = None


def set_cookies_for_channel(channel_index):
    """Set the cookies file path for the current channel (1-5)."""
    global _current_cookies_path
    path = os.path.join(TEMP_DIR, f"cookies_{channel_index}.txt")
    if os.path.exists(path):
        _current_cookies_path = path
        logger.info(f"Cookies set for channel #{channel_index}: {path}")
    else:
        _current_cookies_path = None
        logger.info(f"No cookies file for channel #{channel_index}")


def _get_cookies_path():
    """Get current cookies path, or try any available."""
    global _current_cookies_path
    if _current_cookies_path and os.path.exists(_current_cookies_path):
        return _current_cookies_path
    # Try any available cookies file
    for i in range(1, 6):
        path = os.path.join(TEMP_DIR, f"cookies_{i}.txt")
        if os.path.exists(path):
            return path
    return None


def _load_cookies_for_requests():
    """Load cookies from Netscape cookies.txt file for use with requests library."""
    cookies_path = _get_cookies_path()
    if not cookies_path:
        return {}
    try:
        jar = MozillaCookieJar(cookies_path)
        jar.load(ignore_discard=True, ignore_expires=True)
        return {cookie.name: cookie.value for cookie in jar if '.youtube.com' in cookie.domain}
    except Exception as e:
        logger.debug(f"Could not load cookies from {cookies_path}: {e}")
        return {}


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


def check_video_playability(video_id):
    """
    Quick check if a video is actually playable.
    
    Uses YouTube Data API v3 (videos.list) instead of innertube,
    because innertube returns LOGIN_REQUIRED from CI environments.
    Falls back to assuming playable if API check fails.
    """
    # Method 1: YouTube Data API (works reliably from CI)
    api_key = _get_api_key()
    if api_key:
        try:
            url = "https://www.googleapis.com/youtube/v3/videos"
            params = {
                "part": "status",
                "id": video_id,
                "key": api_key
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if not items:
                    logger.info(f"Video {video_id} not found via API — likely deleted/private")
                    return False
                status = items[0].get("status", {})
                privacy = status.get("privacyStatus", "")
                if privacy == "public":
                    return True
                logger.info(f"Video {video_id} not playable: privacyStatus={privacy}")
                return False
            else:
                logger.debug(f"API playability check returned {resp.status_code} for {video_id}")
        except Exception as e:
            logger.debug(f"API playability check failed for {video_id}: {e}")
    
    # Method 2: Innertube with ANDROID client (less bot detection)
    try:
        url = "https://www.youtube.com/youtubei/v1/player"
        payload = {
            "context": {
                "client": {
                    "clientName": "ANDROID",
                    "clientVersion": "19.09.37",
                    "androidSdkVersion": 30,
                    "hl": "en",
                    "gl": "US"
                }
            },
            "videoId": video_id
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip"
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code != 200:
            return True  # Assume playable if check fails
        data = resp.json()
        status = data.get("playabilityStatus", {}).get("status", "")
        if status == "OK":
            return True
        reason = data.get("playabilityStatus", {}).get("reason", "unknown")
        logger.info(f"Video {video_id} not playable: {status} — {reason}")
        return False
    except Exception as e:
        logger.debug(f"Playability check failed for {video_id}: {e}")
        return True  # Assume playable if check fails


def _get_api_key():
    """Get any available YouTube API key."""
    for i in range(1, 6):
        key = os.environ.get(f"YOUTUBE_API_KEY_{i}", "")
        if key:
            return key
    return os.environ.get("YOUTUBE_API_KEY", "")


def extract_transcript_captions_api(video_id):
    """
    Method 1: Use YouTube Data API v3 captions.list + download.
    
    This uses the official API with our API keys, which are NOT blocked
    from CI environments (unlike scraping approaches).
    
    Note: Downloading caption tracks via API requires OAuth for third-party
    videos, so this method can only LIST available captions. If the video 
    has captions, it confirms they exist and we use other methods to fetch.
    
    Returns: True if captions exist, False otherwise
    """
    api_key = _get_api_key()
    if not api_key:
        return None
    
    url = "https://www.googleapis.com/youtube/v3/captions"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "key": api_key
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        
        if resp.status_code == 403:
            logger.debug(f"Captions API 403 for {video_id} (need OAuth for caption list)")
            return None
        
        resp.raise_for_status()
        data = resp.json()
        
        captions = data.get("items", [])
        if captions:
            langs = [c.get("snippet", {}).get("language", "?") for c in captions]
            logger.info(f"Video {video_id} has captions in: {', '.join(langs)}")
            return True
        else:
            logger.info(f"Video {video_id} has no caption tracks listed")
            return False
            
    except Exception as e:
        logger.debug(f"Captions API check failed for {video_id}: {e}")
        return None


def extract_transcript_api(video_id):
    """
    Method 2: Use youtube-transcript-api to fetch transcript text.
    
    Supports both v0.6.x and v1.x API styles.
    May fail in CI environments due to YouTube IP blocking.
    
    Returns transcript text string, or None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Try the v1.x API style first (newer)
        try:
            # v1.x: YouTubeTranscriptApi.get(video_id)
            fetched = YouTubeTranscriptApi.get(video_id)
            if fetched:
                # v1.x returns FetchedTranscript object(s)
                if hasattr(fetched, 'snippets'):
                    text = " ".join([s.text for s in fetched.snippets])
                elif hasattr(fetched, '__iter__'):
                    parts = []
                    for entry in fetched:
                        if hasattr(entry, 'text'):
                            parts.append(entry.text)
                        elif isinstance(entry, dict):
                            parts.append(entry.get("text", ""))
                    text = " ".join(parts)
                else:
                    text = str(fetched)
                
                if text and len(text) >= 50:
                    logger.info(f"Got transcript via API .get() for {video_id} ({len(text)} chars)")
                    return text
        except TypeError:
            pass  # v1.x .get() might not exist or different signature
        except AttributeError:
            pass  # Different API version
        except Exception as e:
            logger.debug(f"v1.x API style failed for {video_id}: {type(e).__name__}: {e}")
        
        # Try the v0.6.x API style (older but more common)
        try:
            # v0.6.x: YouTubeTranscriptApi.get_transcript(video_id)
            entries = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            text = " ".join([entry.get("text", "") if isinstance(entry, dict) 
                           else entry.text if hasattr(entry, 'text') else str(entry)
                           for entry in entries])
            if text and len(text) >= 50:
                logger.info(f"Got transcript via get_transcript(en) for {video_id} ({len(text)} chars)")
                return text
        except Exception as e:
            logger.debug(f"get_transcript(en) failed for {video_id}: {type(e).__name__}: {e}")
        
        # Try without language filter (get any available language)
        try:
            entries = YouTubeTranscriptApi.get_transcript(video_id)
            text = " ".join([entry.get("text", "") if isinstance(entry, dict)
                           else entry.text if hasattr(entry, 'text') else str(entry)
                           for entry in entries])
            if text and len(text) >= 50:
                logger.info(f"Got transcript via get_transcript(any) for {video_id} ({len(text)} chars)")
                return text
        except Exception as e:
            logger.debug(f"get_transcript(any) failed for {video_id}: {type(e).__name__}: {e}")
        
        # Try listing transcripts and fetching the best one
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try manual English first
            for transcript in transcript_list:
                if not transcript.is_generated and transcript.language_code == 'en':
                    entries = transcript.fetch()
                    text = " ".join([e.get("text", "") if isinstance(e, dict)
                                   else e.text if hasattr(e, 'text') else str(e)
                                   for e in entries])
                    if text and len(text) >= 50:
                        logger.info(f"Got manual English transcript for {video_id}")
                        return text
            
            # Try auto-generated English
            for transcript in transcript_list:
                if transcript.is_generated and transcript.language_code == 'en':
                    entries = transcript.fetch()
                    text = " ".join([e.get("text", "") if isinstance(e, dict)
                                   else e.text if hasattr(e, 'text') else str(e)
                                   for e in entries])
                    if text and len(text) >= 50:
                        logger.info(f"Got auto-generated English transcript for {video_id}")
                        return text
            
            # Try any language and translate
            for transcript in transcript_list:
                try:
                    translated = transcript.translate('en')
                    entries = translated.fetch()
                    text = " ".join([e.get("text", "") if isinstance(e, dict)
                                   else e.text if hasattr(e, 'text') else str(e)
                                   for e in entries])
                    if text and len(text) >= 50:
                        logger.info(f"Got translated transcript for {video_id} (from {transcript.language_code})")
                        return text
                except Exception:
                    continue
                    
        except Exception as e:
            logger.debug(f"list_transcripts failed for {video_id}: {type(e).__name__}: {e}")
        
        logger.info(f"No transcript available via API for {video_id}")
        return None
        
    except ImportError:
        logger.warning("youtube-transcript-api not installed. Install: pip install youtube-transcript-api")
        return None
    except Exception as e:
        logger.error(f"Transcript API error for {video_id}: {type(e).__name__}: {e}")
        return None


def extract_transcript_innertube(video_id):
    """
    Method 3: Direct innertube API call to get captions.
    
    Uses ANDROID client context to avoid LOGIN_REQUIRED bot detection
    that occurs with WEB client from CI environments (e.g., GitHub Actions).
    
    Returns transcript text string, or None if unavailable.
    """
    # Try multiple client contexts — ANDROID avoids bot detection in CI
    client_configs = [
        {
            "name": "ANDROID",
            "payload": {
                "context": {
                    "client": {
                        "clientName": "ANDROID",
                        "clientVersion": "19.09.37",
                        "androidSdkVersion": 30,
                        "hl": "en",
                        "gl": "US"
                    }
                },
                "videoId": video_id
            },
            "headers": {
                "Content-Type": "application/json",
                "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip"
            }
        },
        {
            "name": "WEB_EMBEDDED",
            "payload": {
                "context": {
                    "client": {
                        "clientName": "WEB_EMBEDDED_PLAYER",
                        "clientVersion": "1.20240101.00.00",
                        "hl": "en",
                        "gl": "US"
                    }
                },
                "videoId": video_id
            },
            "headers": {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        },
        {
            "name": "WEB",
            "payload": {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": "2.20240101.00.00",
                        "hl": "en",
                        "gl": "US"
                    }
                },
                "videoId": video_id
            },
            "headers": {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        }
    ]
    
    innertube_url = "https://www.youtube.com/youtubei/v1/player"
    
    for config in client_configs:
        try:
            resp = requests.post(
                innertube_url, 
                json=config["payload"], 
                headers=config["headers"], 
                timeout=15
            )
            if resp.status_code != 200:
                logger.info(f"Innertube {config['name']} request failed ({resp.status_code}) for {video_id}")
                continue
            
            data = resp.json()
            
            # Check playability status
            play_status = data.get("playabilityStatus", {}).get("status", "")
            if play_status != "OK":
                play_reason = data.get("playabilityStatus", {}).get("reason", "")
                logger.info(f"Innertube {config['name']}: {play_status} — {play_reason} for {video_id}")
                continue
            
            # Extract caption tracks
            captions = data.get("captions", {}).get("playerCaptionsTracklistRenderer", {})
            caption_tracks = captions.get("captionTracks", [])
            
            if not caption_tracks:
                logger.info(f"No caption tracks via innertube {config['name']} for {video_id}")
                continue
            
            # Find English track (prefer manual, then auto)
            target_track = None
            for track in caption_tracks:
                lang = track.get("languageCode", "")
                kind = track.get("kind", "")
                if lang == "en" and kind != "asr":
                    target_track = track  # Manual English — best
                    break
            
            if not target_track:
                for track in caption_tracks:
                    lang = track.get("languageCode", "")
                    if lang == "en":
                        target_track = track  # Auto-generated English
                        break
            
            if not target_track:
                # Fall back to any track
                target_track = caption_tracks[0]
                logger.info(f"Using {target_track.get('languageCode', '?')} captions for {video_id}")
            
            # Download the caption track
            base_url = target_track.get("baseUrl", "")
            if not base_url:
                continue
            
            # Request format as JSON3
            if "?" in base_url:
                caption_url = f"{base_url}&fmt=json3"
            else:
                caption_url = f"{base_url}?fmt=json3"
            
            cap_resp = requests.get(caption_url, headers=config["headers"], timeout=15)
            if cap_resp.status_code != 200:
                logger.debug(f"Caption download failed ({cap_resp.status_code}) for {video_id}")
                continue
            
            # Parse JSON3 format
            cap_data = cap_resp.json()
            segments = []
            for event in cap_data.get("events", []):
                text_parts = []
                for seg in event.get("segs", []):
                    text = seg.get("utf8", "").strip()
                    if text and text != "\n":
                        text_parts.append(text)
                if text_parts:
                    segments.append(" ".join(text_parts))
            
            text = " ".join(segments)
            if text and len(text) >= 50:
                logger.info(f"Got transcript via innertube ({config['name']}) for {video_id} ({len(text)} chars)")
                return text
        
        except Exception as e:
            logger.info(f"Innertube {config['name']} error for {video_id}: {type(e).__name__}: {e}")
            continue
    
    logger.debug(f"All innertube clients failed for {video_id}")
    return None


def extract_transcript_ytdlp(video_url, output_name="transcript"):
    """
    Method 4: Pull subtitles via yt-dlp.
    Uses cookies file if available to bypass bot detection.
    
    Returns transcript text string, or None if unavailable.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    subtitle_path = os.path.join(TEMP_DIR, output_name)
    
    cookies_path = _get_cookies_path()
    
    cmd = [
        "yt-dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-lang", "en",
        "--sub-format", "json3",
        "--skip-download",
        "--no-check-certificates",
        "--no-warnings",
        "--no-playlist",
        "-o", subtitle_path,
        video_url
    ]
    
    # Add cookies if available
    if cookies_path:
        cmd.insert(-1, "--cookies")
        cmd.insert(-1, cookies_path)
        logger.info(f"yt-dlp using cookies: {cookies_path}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0 and result.stderr:
            logger.info(f"yt-dlp stderr: {result.stderr[:200]}")
        
        # Look for generated subtitle files
        for ext in [".en.json3", ".en.vtt", ".en.srt"]:
            sub_file = subtitle_path + ext
            if os.path.exists(sub_file):
                text = parse_subtitle_file(sub_file)
                try:
                    os.remove(sub_file)
                except Exception:
                    pass
                if text and len(text) >= 50:
                    logger.info(f"Got transcript via yt-dlp for {video_url} ({len(text)} chars)")
                    return text
        
        logger.info(f"No subtitles found via yt-dlp for {video_url}")
        return None
        
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp timed out for {video_url}")
        return None
    except FileNotFoundError:
        logger.info("yt-dlp not found")
        return None
    except Exception as e:
        logger.error(f"yt-dlp failed: {e}")
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
                segments.append(" ".join(text_parts))
        
        return " ".join(segments)
    except Exception as e:
        logger.error(f"JSON3 parse error: {e}")
        return None


def parse_srt_vtt(content):
    """Parse SRT or VTT subtitle format to plain text."""
    lines = content.split("\n")
    text_lines = []
    
    for line in lines:
        line = line.strip()
        if not line or line.isdigit() or "-->" in line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        line = re.sub(r'<[^>]+>', '', line)
        if line:
            text_lines.append(line)
    
    return " ".join(text_lines)


def extract_transcript_whisper(audio_path):
    """
    Method 5: Transcribe audio using OpenAI Whisper (base model).
    Returns transcript with word-level timestamps.
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
        logger.error("Whisper not installed")
        return None
    except Exception as e:
        logger.error(f"Whisper failed: {e}")
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
    
    Priority order (optimized for GitHub Actions CI):
    1. Direct innertube API (no library needed, works from most IPs)
    2. youtube-transcript-api library (may be blocked from CI IPs)
    3. yt-dlp subtitles (may be blocked from CI IPs)
    4. Whisper local transcription (last resort, needs audio file)
    
    Returns:
        dict with 'text' (full text), 'source', and optionally 'segments'
    """
    video_id = _extract_video_id(video_url)
    
    if not video_id:
        logger.error(f"Could not extract video ID from: {video_url}")
        return {"text": "", "source": "none", "segments": None}
    
    # Method 1: Direct innertube API (most reliable in CI)
    logger.info(f"Transcript [{video_id}]: trying innertube (ANDROID/WEB_EMBEDDED/WEB)...")
    text = extract_transcript_innertube(video_id)
    if text and len(text) >= 50:
        return {"text": text, "source": "innertube", "segments": None}
    logger.info(f"Transcript [{video_id}]: innertube failed")
    
    # Method 2: youtube-transcript-api library
    logger.info(f"Transcript [{video_id}]: trying youtube-transcript-api...")
    text = extract_transcript_api(video_id)
    if text and len(text) >= 50:
        return {"text": text, "source": "youtube_transcript_api", "segments": None}
    logger.info(f"Transcript [{video_id}]: youtube-transcript-api failed")
    
    # Method 3: yt-dlp subtitles
    logger.info(f"Transcript [{video_id}]: trying yt-dlp...")
    text = extract_transcript_ytdlp(video_url)
    if text and len(text) >= 50:
        return {"text": text, "source": "youtube_subs", "segments": None}
    logger.info(f"Transcript [{video_id}]: yt-dlp failed")
    
    # Method 4: Whisper (last resort — needs downloaded audio)
    if video_path and os.path.exists(video_path):
        logger.info(f"Transcript [{video_id}]: trying Whisper on local audio...")
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
    
    logger.warning(f"All transcript methods failed for {video_url} (id={video_id})")
    return {"text": "", "source": "none", "segments": None}

