# src/content/clip_detector.py
# Gemini AI clip selection — Long Clips + Shorts with safety pre-screen

import logging

from ..utils.gemini_client import call_gemini_with_retry

logger = logging.getLogger("clipper.content.clip_detector")

# Copyright safety addition — appended to both prompts
SAFETY_ADDITION = """
COPYRIGHT SAFETY RULES — strictly follow all of these:
1. NEVER select segments where background music is clearly audible
2. STRONGLY PREFER segments where only the speaker's voice is present
3. AVOID segments containing: movie clips, TV footage, songs being sung,
   news broadcast audio, or any third-party audio/video
4. AVOID segments where the speaker is reading copyrighted text verbatim
5. If there is ANY doubt about music presence → do NOT select that segment

Add this field to your JSON response:
"music_risk": "none"   (no music audible at all)
             "low"    (very faint, barely audible background)
             "high"   (clear background music present)

System will REJECT segments with music_risk = "high" automatically.
"""

# Long Clip Prompt (3-10 minutes)
LONG_CLIP_PROMPT = """
You are a professional YouTube clip editor. Analyze this transcript and identify the SINGLE best segment for a long clip (3-10 minutes).

Criteria:
- Must be self-contained (viewer needs NO prior context from the video)
- Has a clear beginning, middle, and end
- Contains a surprising insight, strong argument, or compelling story
- Would make sense as a standalone video

Quality Gate — answer these before selecting:
1. Can a new viewer understand this without watching the full video? (must be YES)
2. Does the segment have a natural resolution/conclusion? (must be YES)
3. Completeness score 1-10 (must be >= 7 to proceed)

{safety}

Transcript:
{transcript}

Return ONLY valid JSON:
{{
  "start_time": "MM:SS",
  "end_time": "MM:SS",
  "duration_minutes": float,
  "title": "engaging title under 60 chars",
  "description_hook": "first sentence for video description, max 100 chars",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "completeness_score": int,
  "why_clipworthy": "one sentence explanation",
  "music_risk": "none|low|high",
  "approved": true/false
}}
"""

# Shorts Prompt (30-59 seconds)
SHORTS_PROMPT = """
You are a viral Shorts clip editor. Analyze this transcript and find the SINGLE best segment for a YouTube Short (30-59 seconds).

Structure required (ALL three must be present):
- HOOK (0-5s): A shocking statement or question that stands alone
- PAYOFF (5-50s): The explanation or story that answers the hook
- LANDING (50-59s): A memorable conclusion or punchline

Quality Gate — answer these before selecting:
1. Does the hook work without any prior context? (must be YES)
2. Is there a clear resolution within 60 seconds? (must be YES)
3. Completeness score 1-10 (must be >= 8 to proceed — higher bar than long clips)
4. Would this make someone stop scrolling in the first 3 seconds? (must be YES)

If no segment meets all criteria: set approved = false. Do NOT force-approve a weak segment.

{safety}

Transcript:
{transcript}

Return ONLY valid JSON:
{{
  "start_time": "MM:SS",
  "end_time": "MM:SS",
  "duration_seconds": int,
  "hook_text": "3-5 word hook for text overlay at start",
  "title": "engaging title under 50 chars with #Shorts",
  "completeness_score": int,
  "music_risk": "none|low|high",
  "approved": true/false
}}
"""


def detect_long_clip(transcript_text):
    """
    Use Gemini to find the best long clip segment (3-10 min).
    
    Args:
        transcript_text: Full transcript text of the source video.
    
    Returns:
        dict with clip details if approved, None if no valid clip found.
    """
    # Truncate transcript to avoid token limits
    truncated = transcript_text[:15000]
    
    prompt = LONG_CLIP_PROMPT.format(
        transcript=truncated,
        safety=SAFETY_ADDITION
    )
    
    try:
        result = call_gemini_with_retry(prompt, parse_json=True)
        
        if not result.get("approved", False):
            logger.info(f"Long clip not approved. Score: {result.get('completeness_score', 0)}")
            return None
        
        if result.get("music_risk") == "high":
            logger.warning("Long clip rejected — music_risk=high")
            return None
        
        score = result.get("completeness_score", 0)
        if score < 7:
            logger.info(f"Long clip below quality threshold. Score: {score}")
            return None
        
        result["format"] = "long"
        logger.info(f"Long clip approved: {result.get('title', 'Unknown')} "
                    f"[{result.get('start_time')}-{result.get('end_time')}] "
                    f"Score: {score}")
        return result
        
    except Exception as e:
        logger.error(f"Long clip detection failed: {e}")
        return None


def detect_short_clip(transcript_text):
    """
    Use Gemini to find the best Shorts clip segment (30-59 sec).
    
    Args:
        transcript_text: Full transcript text of the source video.
    
    Returns:
        dict with clip details if approved, None if no valid clip found.
    """
    truncated = transcript_text[:15000]
    
    prompt = SHORTS_PROMPT.format(
        transcript=truncated,
        safety=SAFETY_ADDITION
    )
    
    try:
        result = call_gemini_with_retry(prompt, parse_json=True)
        
        if not result.get("approved", False):
            logger.info(f"Short clip not approved. Score: {result.get('completeness_score', 0)}")
            return None
        
        if result.get("music_risk") == "high":
            logger.warning("Short clip rejected — music_risk=high")
            return None
        
        score = result.get("completeness_score", 0)
        if score < 8:  # Higher bar for Shorts
            logger.info(f"Short clip below quality threshold. Score: {score}")
            return None
        
        result["format"] = "short"
        logger.info(f"Short clip approved: {result.get('title', 'Unknown')} "
                    f"[{result.get('start_time')}-{result.get('end_time')}] "
                    f"Score: {score}")
        return result
        
    except Exception as e:
        logger.error(f"Short clip detection failed: {e}")
        return None


def detect_clips_for_video(transcript_text, source_duration_minutes, needs_long=True, needs_short=True):
    """
    Detect both long and short clips for a single video based on needs.
    Respects format classification rules.
    
    Returns:
        dict with 'long' and 'short' keys (each None if not found/needed)
    """
    results = {"long": None, "short": None}
    
    if needs_long and source_duration_minutes >= 3:
        results["long"] = detect_long_clip(transcript_text)
    
    if needs_short and source_duration_minutes >= 20:
        results["short"] = detect_short_clip(transcript_text)
    
    return results
