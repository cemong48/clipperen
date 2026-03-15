# src/upload/metadata_generator.py
# Gemini-generated title/desc/tags with affiliate requirements support

import json
import logging

from ..utils.gemini_client import call_gemini_with_retry

logger = logging.getLogger("clipper.upload.metadata_generator")

METADATA_PROMPT = """
You are generating YouTube metadata for a clip video.

Clip content summary:
{clip_summary}

Original creator: {creator_name}
Original video URL: {original_url}
Clip format: {format_type}

AFFILIATE REQUIREMENTS — apply ALL of these exactly as specified:
{affiliate_requirements_json}

Generate the following, following all affiliate requirements above:

1. TITLE: Engaging, under 60 chars. If custom_instructions mentions title rules, follow them.
{shorts_title_note}

2. DESCRIPTION: 
   - Insert description_links marked as position="top" at the very top
   - Then write 2-3 sentences describing the clip content  
   - Then insert description_links marked as position="bottom"
   - Then append all mandatory_hashtags at the end
   - Always include: "Original video by @{creator_name}: {original_url}"
   - Follow any rules in custom_instructions

3. TAGS: 10-15 tags relevant to content + include mandatory_hashtags as tags (without #)

4. PINNED_COMMENT: Copy exactly from pinned_comment field. If null, return null.

5. WATERMARK_TEXT: Copy exactly from watermark_text field. If null, return null.

Return ONLY valid JSON:
{{
  "title": "...",
  "description": "...",
  "tags": ["...", "..."],
  "pinned_comment": "..." or null,
  "watermark_text": "..." or null
}}
"""


def resolve_affiliate_requirements(whitelist_entry, queue_entry=None):
    """
    Merge whitelist defaults with per-video queue overrides.
    Queue values take priority. Lists are merged (not replaced).
    """
    defaults = {}
    if whitelist_entry:
        defaults = whitelist_entry.get("default_affiliate_requirements", {}) or {}
    
    overrides = {}
    if queue_entry:
        overrides = queue_entry.get("affiliate_requirements", {}) or {}
    
    merged = {
        "description_links": (
            overrides.get("description_links") or
            defaults.get("description_links") or []
        ),
        "mandatory_hashtags": list(set(
            (defaults.get("mandatory_hashtags") or []) +
            (overrides.get("mandatory_hashtags") or [])
        )),
        "pinned_comment": (
            overrides.get("pinned_comment") or
            defaults.get("pinned_comment")
        ),
        "watermark_text": (
            overrides.get("watermark_text") or
            defaults.get("watermark_text")
        ),
        "custom_instructions": " ".join(filter(None, [
            defaults.get("custom_instructions", ""),
            overrides.get("custom_instructions", "")
        ]))
    }
    return merged


def generate_metadata(clip_info, creator_name, original_url,
                       format_type="long", whitelist_entry=None,
                       queue_entry=None):
    """
    Generate YouTube metadata using Gemini AI.
    
    Args:
        clip_info: dict from clip_detector (title, description_hook, tags, etc.)
        creator_name: Original channel name
        original_url: URL of the original video
        format_type: 'long' or 'short'
        whitelist_entry: Whitelist entry for the source channel
        queue_entry: Manual queue entry (if applicable)
    
    Returns:
        dict with title, description, tags, pinned_comment, watermark_text
    """
    # Resolve affiliate requirements
    affiliate_reqs = resolve_affiliate_requirements(whitelist_entry, queue_entry)
    
    # Build clip summary from available info
    clip_summary = clip_info.get("why_clipworthy", "")
    if clip_info.get("description_hook"):
        clip_summary = f"{clip_info['description_hook']}. {clip_summary}"
    if clip_info.get("title"):
        clip_summary = f"Title: {clip_info['title']}. {clip_summary}"
    
    # Shorts-specific title note
    shorts_note = ""
    if format_type == "short":
        shorts_note = "For Shorts: title MUST contain #Shorts"
    
    prompt = METADATA_PROMPT.format(
        clip_summary=clip_summary,
        creator_name=creator_name,
        original_url=original_url,
        format_type=format_type,
        affiliate_requirements_json=json.dumps(affiliate_reqs, indent=2),
        shorts_title_note=shorts_note
    )
    
    try:
        result = call_gemini_with_retry(prompt, parse_json=True)
        
        # Ensure title length
        if len(result.get("title", "")) > 60:
            result["title"] = result["title"][:57] + "..."
        
        # Ensure #Shorts for shorts
        if format_type == "short" and "#Shorts" not in result.get("title", ""):
            result["title"] = result["title"][:50] + " #Shorts"
        
        # Add standard fields
        result["categoryId"] = "22"  # People & Blogs
        result["defaultLanguage"] = "en"
        result["defaultAudioLanguage"] = "en"
        result["madeForKids"] = False
        
        logger.info(f"Metadata generated: {result.get('title', 'Unknown')}")
        return result
        
    except Exception as e:
        logger.error(f"Metadata generation failed: {e}")
        # Fallback metadata
        title = clip_info.get("title", f"Clip from {creator_name}")
        if format_type == "short":
            title = f"{title} #Shorts"
        
        return {
            "title": title[:60],
            "description": f"Clip from {creator_name}.\nOriginal: {original_url}",
            "tags": clip_info.get("tags", [creator_name, "clip"]),
            "pinned_comment": affiliate_reqs.get("pinned_comment"),
            "watermark_text": affiliate_reqs.get("watermark_text"),
            "categoryId": "22",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
            "madeForKids": False
        }
