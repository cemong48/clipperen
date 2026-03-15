# src/monitor/analytics_puller.py
# YouTube Analytics API — pull performance metrics (per-channel credentials)

import os
import json
import logging
from datetime import datetime, timedelta

from ..utils.channel_credentials import get_analytics_service_for_channel

logger = logging.getLogger("clipper.monitor.analytics")


def get_analytics_service(channel_name=None):
    """Build YouTube Analytics API service for a specific channel."""
    return get_analytics_service_for_channel(channel_name or "psyched")


def pull_video_metrics(video_id, channel_name=None):
    """
    Pull key metrics for a specific video.
    
    Returns:
        dict with views, ctr, avd_pct, impressions, subscriber_gain
    """
    try:
        analytics = get_analytics_service(channel_name)
        
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
            filters=f"video=={video_id}",
            dimensions="video"
        ).execute()
        
        rows = response.get("rows", [])
        if not rows:
            return {
                "video_id": video_id,
                "views": 0,
                "ctr_pct": 0,
                "avd_pct": 0,
                "impressions": 0,
                "subscriber_gain": 0,
                "pulled_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        
        row = rows[0]
        return {
            "video_id": video_id,
            "views": row[1] if len(row) > 1 else 0,
            "minutes_watched": row[2] if len(row) > 2 else 0,
            "avd_seconds": row[3] if len(row) > 3 else 0,
            "subscribers_gained": row[4] if len(row) > 4 else 0,
            "subscribers_lost": row[5] if len(row) > 5 else 0,
            "subscriber_gain": (row[4] if len(row) > 4 else 0) - (row[5] if len(row) > 5 else 0),
            "pulled_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
    except Exception as e:
        logger.error(f"Failed to pull metrics for {video_id}: {e}")
        return {
            "video_id": video_id,
            "views": 0,
            "ctr_pct": 0,
            "avd_pct": 0,
            "impressions": 0,
            "subscriber_gain": 0,
            "error": str(e),
            "pulled_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        }


def pull_channel_impressions(video_id, channel_name=None):
    """
    Pull impression and CTR data for a video.
    Uses YouTube Data API since Analytics may not have CTR directly.
    """
    try:
        analytics = get_analytics_service(channel_name)
        
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="cardClickRate,cardImpressions",
            filters=f"video=={video_id}"
        ).execute()
        
        rows = response.get("rows", [])
        if rows:
            return {
                "ctr_pct": rows[0][0] if rows[0] else 0,
                "impressions": rows[0][1] if len(rows[0]) > 1 else 0
            }
    except Exception as e:
        logger.warning(f"Impression data unavailable for {video_id}: {e}")
    
    return {"ctr_pct": 0, "impressions": 0}
