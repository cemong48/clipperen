# src/monitor/auto_optimizer.py
# Auto-update title/thumbnail/description/tags for underperforming videos

import logging

from ..utils.gemini_client import call_gemini_with_retry
from ..upload.youtube_uploader import update_video_metadata
from ..utils.dry_run import is_dry_run

logger = logging.getLogger("clipper.monitor.auto_optimizer")


def optimize_video(video_id, posted_entry, metrics, reasons):
    """
    Auto-optimize an underperforming video.
    
    Logic from instructions:
        CTR < 4.0%  → new title + thumbnail
        AVD < 40%   → new description + tags
        Impressions < 500 → more niche tags + trending keywords
    """
    title = posted_entry.get("title", "")
    current_tags = posted_entry.get("tags", [])
    
    updates = {}
    
    if "low_ctr" in reasons:
        # Generate new title variations
        updates.update(_optimize_ctr(title, metrics))
    
    if "low_avd" in reasons:
        # Update description with better hook + refresh tags
        updates.update(_optimize_avd(title, current_tags, metrics))
    
    if "low_impressions" in reasons:
        # Add more specific niche tags
        updates.update(_optimize_impressions(title, current_tags, metrics))
    
    if updates:
        update_version = posted_entry.get("auto_update_count", 0) + 1
        logger.info(f"Applying optimization v{update_version} to {video_id}: {list(updates.keys())}")
        
        if not is_dry_run():
            update_video_metadata(video_id, updates)
        else:
            logger.info(f"[DRY_RUN] Would update {video_id} with: {updates}")
    
    return updates


def _optimize_ctr(current_title, metrics):
    """Generate new title for low CTR."""
    prompt = f"""
A YouTube video with this title is getting low click-through rate (CTR: {metrics.get('ctr_pct', 0):.1f}%):

Current title: "{current_title}"

Generate 1 improved title that:
- Is more curiosity-inducing
- Uses power words (shocking, hidden, secret, truth)
- Is under 60 characters
- Is different enough from the original to get attention

Return ONLY valid JSON:
{{
  "title": "new title here",
  "reasoning": "why this is better"
}}
"""
    try:
        result = call_gemini_with_retry(prompt, parse_json=True)
        new_title = result.get("title", "")
        if new_title and len(new_title) <= 60:
            logger.info(f"New title: '{new_title}' (was: '{current_title}')")
            return {"title": new_title}
    except Exception as e:
        logger.error(f"CTR optimization failed: {e}")
    
    return {}


def _optimize_avd(current_title, current_tags, metrics):
    """Improve description and tags for low average view duration."""
    prompt = f"""
A YouTube video is getting low average view duration (AVD: {metrics.get('avd_pct', 0):.1f}%).

Title: "{current_title}"
Current tags: {current_tags}

Generate:
1. An improved description with a better hook in the first line (max 200 chars for description)
2. Updated tags (10-15 relevant tags)

Return ONLY valid JSON:
{{
  "description": "improved description",
  "tags": ["tag1", "tag2", "..."]
}}
"""
    try:
        result = call_gemini_with_retry(prompt, parse_json=True)
        updates = {}
        if result.get("description"):
            updates["description"] = result["description"]
        if result.get("tags"):
            updates["tags"] = result["tags"]
        return updates
    except Exception as e:
        logger.error(f"AVD optimization failed: {e}")
    
    return {}


def _optimize_impressions(current_title, current_tags, metrics):
    """Add niche tags for low impressions."""
    prompt = f"""
A YouTube video has low impressions ({metrics.get('impressions', 0)} after 48 hours).

Title: "{current_title}"
Current tags: {current_tags}

Generate 5 additional highly specific, niche tags that could help this video
get discovered. Focus on long-tail keywords and trending related topics.

Return ONLY valid JSON:
{{
  "additional_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}
"""
    try:
        result = call_gemini_with_retry(prompt, parse_json=True)
        additional = result.get("additional_tags", [])
        if additional:
            merged_tags = list(set(current_tags + additional))
            return {"tags": merged_tags}
    except Exception as e:
        logger.error(f"Impressions optimization failed: {e}")
    
    return {}
