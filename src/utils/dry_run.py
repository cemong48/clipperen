# src/utils/dry_run.py
# DRY_RUN mode helpers — prevents real uploads during testing

import os
import logging

logger = logging.getLogger(__name__)

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def is_dry_run():
    """Check if system is in DRY_RUN mode."""
    return DRY_RUN


def upload_video(file_path, metadata, channel, upload_func):
    """
    Wrapper for video upload. In DRY_RUN mode, logs what would
    happen instead of actually uploading.
    """
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would upload: {metadata.get('title', 'Unknown')} → {channel}")
        logger.info(f"[DRY_RUN] File: {file_path}")
        logger.info(f"[DRY_RUN] Tags: {metadata.get('tags', [])}")
        print(f"[DRY_RUN] Would upload: {metadata.get('title', 'Unknown')} → {channel}")
        print(f"[DRY_RUN] File: {file_path}")
        print(f"[DRY_RUN] Tags: {metadata.get('tags', [])}")
        return {"status": "dry_run", "video_id": "DRY_RUN_ID"}
    else:
        return upload_func(file_path, metadata, channel)


def post_pinned_comment(video_id, comment_text, comment_func):
    """
    Wrapper for pinned comment posting. In DRY_RUN mode, logs
    what would happen instead of actually posting.
    """
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would pin comment on {video_id}: {comment_text}")
        print(f"[DRY_RUN] Would pin comment on {video_id}: {comment_text}")
        return
    else:
        return comment_func(video_id, comment_text)
