# src/monitor/performance_checker.py
# Compare video metrics vs thresholds — trigger auto-optimization

import json
import logging
from datetime import datetime, timedelta

from ..utils.file_lock import read_json, write_json
from .analytics_puller import pull_video_metrics, pull_channel_impressions
from .auto_optimizer import optimize_video

logger = logging.getLogger("clipper.monitor.performance_checker")


def check_all_videos(settings_path="config/settings.json",
                      posted_path="database/posted.json",
                      perf_log_path="database/performance_log.json"):
    """
    Main performance check: review all posted videos after 48h.
    Compare metrics against thresholds. Trigger auto-optimization.
    """
    settings = read_json(settings_path, default={})
    perf_settings = settings.get("performance", {})
    
    review_after_hours = perf_settings.get("review_after_hours", 48)
    ctr_min = perf_settings.get("ctr_minimum_pct", 4.0)
    avd_min = perf_settings.get("avd_minimum_pct", 40.0)
    max_updates = perf_settings.get("max_auto_updates_per_video", 3)
    low_impression_threshold = perf_settings.get("low_impression_threshold", 500)
    
    posted = read_json(posted_path, default=[])
    perf_log = read_json(perf_log_path, default=[])
    
    cutoff = datetime.utcnow() - timedelta(hours=review_after_hours)
    
    checked = 0
    optimized = 0
    
    for entry in posted:
        video_id = entry.get("video_id", "")
        if not video_id or video_id == "DRY_RUN_ID":
            continue
        
        # Skip if already max-updated
        update_count = entry.get("auto_update_count", 0)
        if update_count >= max_updates:
            continue
        
        # Check if past review window
        posted_at = entry.get("posted_at", "")
        try:
            post_time = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            if post_time.replace(tzinfo=None) > cutoff:
                continue  # Too recent
        except (ValueError, AttributeError):
            continue
        
        # Pull metrics
        metrics = pull_video_metrics(video_id)
        impression_data = pull_channel_impressions(video_id)
        
        metrics["ctr_pct"] = impression_data.get("ctr_pct", 0)
        metrics["impressions"] = impression_data.get("impressions", 0)
        
        # Log performance
        perf_entry = {
            "video_id": video_id,
            "checked_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metrics": metrics,
            "update_count": update_count
        }
        perf_log.append(perf_entry)
        checked += 1
        
        # Check thresholds and optimize if needed
        needs_optimization = False
        optimization_reasons = []
        
        if metrics.get("ctr_pct", 0) < ctr_min:
            optimization_reasons.append("low_ctr")
            needs_optimization = True
        
        if metrics.get("avd_pct", 0) < avd_min:
            optimization_reasons.append("low_avd")
            needs_optimization = True
        
        if metrics.get("impressions", 0) < low_impression_threshold:
            optimization_reasons.append("low_impressions")
            needs_optimization = True
        
        if needs_optimization and update_count < max_updates:
            logger.info(
                f"Video {video_id} underperforming: {optimization_reasons}. "
                f"Triggering auto-optimization (update #{update_count + 1})"
            )
            try:
                optimize_video(video_id, entry, metrics, optimization_reasons)
                entry["auto_update_count"] = update_count + 1
                optimized += 1
            except Exception as e:
                logger.error(f"Auto-optimization failed for {video_id}: {e}")
    
    # Save updated data
    write_json(posted_path, posted)
    write_json(perf_log_path, perf_log)
    
    logger.info(f"Performance check complete: {checked} checked, {optimized} optimized")
    return {"checked": checked, "optimized": optimized}


if __name__ == "__main__":
    check_all_videos()
