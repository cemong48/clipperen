# src/upload/youtube_uploader.py
# YouTube Data API v3 upload with OAuth2 — per-channel credentials

import os
import json
import logging
import time

from ..utils.dry_run import is_dry_run
from ..utils.channel_credentials import get_youtube_service_for_channel

logger = logging.getLogger("clipper.upload.youtube_uploader")


def get_youtube_service(channel_name=None):
    """
    Build YouTube API service for a specific channel.
    Each channel has its own credentials (YOUTUBE_API_KEY_1 to _5).
    """
    return get_youtube_service_for_channel(channel_name or "psyched")


def upload_video(file_path, metadata, channel_name):
    """
    Upload a video to YouTube via Data API v3.
    
    Args:
        file_path: Path to the video file
        metadata: dict with title, description, tags, categoryId, etc.
        channel_name: Target channel name (for logging)
    
    Returns:
        dict with video_id and status
    """
    if is_dry_run():
        logger.info(f"[DRY_RUN] Would upload: {metadata.get('title', 'Unknown')} → {channel_name}")
        logger.info(f"[DRY_RUN] File: {file_path}")
        logger.info(f"[DRY_RUN] Tags: {metadata.get('tags', [])}")
        return {"status": "dry_run", "video_id": "DRY_RUN_ID"}
    
    from googleapiclient.http import MediaFileUpload
    
    youtube = get_youtube_service(channel_name)
    
    body = {
        "snippet": {
            "title": metadata.get("title", "Clip"),
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
            "categoryId": metadata.get("categoryId", "22"),  # People & Blogs
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }
    
    # Schedule publishing if scheduledStartTime is set
    if metadata.get("scheduledStartTime"):
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = metadata["scheduledStartTime"]
    
    media = MediaFileUpload(
        file_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=256 * 1024  # 256KB chunks
    )
    
    logger.info(f"Uploading: {metadata.get('title', 'Unknown')} → {channel_name}")
    
    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Upload progress: {int(status.progress() * 100)}%")
        
        video_id = response.get("id", "")
        logger.info(f"Upload complete! Video ID: {video_id}")
        
        return {
            "status": "uploaded",
            "video_id": video_id,
            "response": response
        }
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise


def upload_subtitles(video_id, subtitle_path, language, name, channel_name=None):
    """
    Upload subtitle track to an existing YouTube video.
    """
    if is_dry_run():
        logger.info(f"[DRY_RUN] Would upload {language} subtitles for {video_id}")
        return
    
    from googleapiclient.http import MediaFileUpload
    
    youtube = get_youtube_service(channel_name)
    
    body = {
        "snippet": {
            "videoId": video_id,
            "language": language,
            "name": name,
            "isDraft": False
        }
    }
    
    media = MediaFileUpload(subtitle_path, mimetype="application/x-subrip")
    
    try:
        youtube.captions().insert(
            part="snippet",
            body=body,
            media_body=media
        ).execute()
        logger.info(f"Subtitle uploaded ({language}): {video_id}")
    except Exception as e:
        logger.error(f"Subtitle upload failed ({language}): {e}")


def post_pinned_comment(video_id, comment_text, channel_name=None):
    """
    Post a comment on a video. 
    Note: YouTube API does not support programmatic pinning.
    Comment is posted, operator must pin manually in YouTube Studio.
    """
    if is_dry_run():
        logger.info(f"[DRY_RUN] Would post comment on {video_id}: {comment_text}")
        return
    
    if not comment_text:
        return
    
    youtube = get_youtube_service(channel_name)
    
    try:
        comment_response = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
        ).execute()
        
        comment_id = comment_response["snippet"]["topLevelComment"]["id"]
        logger.info(
            f"Comment posted (ID: {comment_id}). "
            f"PIN MANUALLY in YouTube Studio."
        )
        
    except Exception as e:
        logger.error(f"Comment posting failed: {e}")


def update_video_metadata(video_id, updates, channel_name=None):
    """
    Update title, description, tags of an existing video.
    Used by auto-optimizer.
    """
    if is_dry_run():
        logger.info(f"[DRY_RUN] Would update metadata for {video_id}")
        return
    
    youtube = get_youtube_service(channel_name)
    
    # Get current video data first
    current = youtube.videos().list(
        part="snippet",
        id=video_id
    ).execute()
    
    if not current.get("items"):
        logger.error(f"Video not found: {video_id}")
        return
    
    snippet = current["items"][0]["snippet"]
    
    # Merge updates
    if "title" in updates:
        snippet["title"] = updates["title"]
    if "description" in updates:
        snippet["description"] = updates["description"]
    if "tags" in updates:
        snippet["tags"] = updates["tags"]
    
    try:
        youtube.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": snippet
            }
        ).execute()
        logger.info(f"Video metadata updated: {video_id}")
    except Exception as e:
        logger.error(f"Metadata update failed: {e}")
