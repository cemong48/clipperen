# src/discovery/whitelist_manager.py
# Whitelist CRUD operations + weekly re-validation

import logging
from datetime import datetime

from ..utils.file_lock import read_json, write_json
from .permission_detector import check_for_revocation

logger = logging.getLogger("clipper.discovery.whitelist")

WHITELIST_PATH = "config/whitelist.json"


def load_whitelist(path=None):
    """Load whitelist from file."""
    return read_json(path or WHITELIST_PATH, default={"channels": []})


def save_whitelist(whitelist, path=None):
    """Save whitelist to file atomically."""
    write_json(path or WHITELIST_PATH, whitelist)


def add_to_whitelist(channel_info, permission_result, path=None):
    """
    Add a new channel to the whitelist.
    
    Args:
        channel_info: dict with channel_id, channel_name, theme
        permission_result: dict from permission_detector.scan_channel_permissions()
    """
    whitelist = load_whitelist(path)
    
    # Check if already exists
    for ch in whitelist["channels"]:
        if ch["channel_id"] == channel_info["channel_id"]:
            logger.info(f"Channel {channel_info['channel_name']} already in whitelist, skipping.")
            return False
    
    confidence = permission_result.get("confidence", 0)
    
    # Determine status based on confidence
    if confidence >= 85:
        status = "active"
    elif confidence >= 70:
        status = "pending_review"
    else:
        logger.info(f"Channel {channel_info['channel_name']} below threshold ({confidence}), not adding.")
        return False
    
    entry = {
        "channel_id": channel_info["channel_id"],
        "channel_name": channel_info["channel_name"],
        "theme": channel_info.get("theme", "Unknown"),
        "source": permission_result.get("source", "auto"),
        "permission_proof_url": permission_result.get("permission_proof_url", ""),
        "confidence": confidence,
        "permission_verified_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "last_revalidated": datetime.utcnow().strftime("%Y-%m-%d"),
        "status": status,
        "restrictions": [],
        "revenue_share_pct": None,
        "whop_program_id": None,
        "default_affiliate_requirements": None,
        "notes": ""
    }
    
    whitelist["channels"].append(entry)
    save_whitelist(whitelist, path)
    logger.info(f"Added {channel_info['channel_name']} to whitelist (status: {status}, confidence: {confidence})")
    return True


def add_manual_whop_channel(channel_id, channel_name, whop_program_id,
                             revenue_share_pct, affiliate_requirements=None, path=None):
    """
    Manually add a Whop program channel to the whitelist.
    These get confidence 99 and are always active.
    """
    whitelist = load_whitelist(path)
    
    # Check if already exists
    for ch in whitelist["channels"]:
        if ch["channel_id"] == channel_id:
            logger.info(f"Channel {channel_name} already in whitelist, updating Whop info.")
            ch["whop_program_id"] = whop_program_id
            ch["revenue_share_pct"] = revenue_share_pct
            ch["source"] = "manual_whop"
            if affiliate_requirements:
                ch["default_affiliate_requirements"] = affiliate_requirements
            save_whitelist(whitelist, path)
            return True
    
    entry = {
        "channel_id": channel_id,
        "channel_name": channel_name,
        "theme": None,  # Will be classified by router
        "source": "manual_whop",
        "permission_proof_url": "",
        "confidence": 99,
        "permission_verified_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "last_revalidated": datetime.utcnow().strftime("%Y-%m-%d"),
        "status": "active",
        "restrictions": ["no_paid_content"],
        "revenue_share_pct": revenue_share_pct,
        "whop_program_id": whop_program_id,
        "default_affiliate_requirements": affiliate_requirements or {},
        "notes": f"Whop program: {whop_program_id}"
    }
    
    whitelist["channels"].append(entry)
    save_whitelist(whitelist, path)
    logger.info(f"Added Whop channel {channel_name} to whitelist")
    return True


def get_active_channels(path=None):
    """Get all channels with status 'active'."""
    whitelist = load_whitelist(path)
    return [ch for ch in whitelist["channels"] if ch.get("status") == "active"]


def suspend_channel(channel_id, reason="", path=None):
    """Suspend a channel (e.g., revocation detected)."""
    whitelist = load_whitelist(path)
    for ch in whitelist["channels"]:
        if ch["channel_id"] == channel_id:
            ch["status"] = "suspended"
            ch["notes"] = f"Suspended: {reason}" if reason else ch.get("notes", "")
            save_whitelist(whitelist, path)
            logger.warning(f"Channel {ch['channel_name']} SUSPENDED: {reason}")
            return True
    return False


def remove_channel(channel_id, path=None):
    """Remove a channel from whitelist entirely."""
    whitelist = load_whitelist(path)
    original_len = len(whitelist["channels"])
    whitelist["channels"] = [ch for ch in whitelist["channels"] if ch["channel_id"] != channel_id]
    if len(whitelist["channels"]) < original_len:
        save_whitelist(whitelist, path)
        logger.info(f"Removed channel {channel_id} from whitelist")
        return True
    return False


def revalidate_all(path=None):
    """
    Weekly re-validation: re-scan all active channels for revocation signals.
    If revocation found → set status to 'suspended'.
    """
    whitelist = load_whitelist(path)
    suspended_count = 0
    
    for ch in whitelist["channels"]:
        if ch.get("status") != "active":
            continue
        
        logger.info(f"Re-validating: {ch['channel_name']}")
        revoked, keywords = check_for_revocation(ch["channel_id"], ch["channel_name"])
        
        if revoked:
            ch["status"] = "suspended"
            ch["notes"] = f"Revocation detected: {', '.join(keywords)}"
            logger.warning(f"  ❌ REVOKED: {ch['channel_name']} — {keywords}")
            suspended_count += 1
        else:
            ch["last_revalidated"] = datetime.utcnow().strftime("%Y-%m-%d")
            logger.info(f"  ✅ Still valid: {ch['channel_name']}")
    
    save_whitelist(whitelist, path)
    logger.info(f"Re-validation complete. {suspended_count} channel(s) suspended.")
    return suspended_count


def get_whitelist_entry(channel_id, path=None):
    """Get a specific channel's whitelist entry."""
    whitelist = load_whitelist(path)
    for ch in whitelist["channels"]:
        if ch["channel_id"] == channel_id:
            return ch
    return None
