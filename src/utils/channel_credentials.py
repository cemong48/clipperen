# src/utils/channel_credentials.py
# Per-channel YouTube credential management
# Supports YOUTUBE_API_KEY_1 to _5 and YOUTUBE_CLIENT_SECRET_1 to _5

import os
import json
import logging

logger = logging.getLogger("clipper.utils.credentials")

# Channel name → credential index mapping
CHANNEL_INDEX = {
    "psyched": 1,   # Psychology & Self-Improvement
    "minted": 2,    # Finance & Business
    "vitals": 3,    # Health & Science
    "wired": 4,     # Tech & AI
    "sage": 5       # Philosophy & Stoicism
}

# Reverse mapping
INDEX_TO_CHANNEL = {v: k for k, v in CHANNEL_INDEX.items()}


def get_api_key(channel_name):
    """
    Get YouTube API key for a specific channel.
    STRICT isolation: only returns YOUTUBE_API_KEY_{index} for this channel.
    NO fallback to other channels' keys.
    """
    idx = CHANNEL_INDEX.get(channel_name, 1)
    
    key = os.environ.get(f"YOUTUBE_API_KEY_{idx}", "")
    if key:
        return key
    
    raise ValueError(
        f"No API key found for channel {channel_name} (idx={idx}). "
        f"Set YOUTUBE_API_KEY_{idx} in GitHub Secrets."
    )


def get_client_secret(channel_name):
    """
    Get OAuth2 client secret JSON for a specific channel.
    STRICT isolation: only returns YOUTUBE_CLIENT_SECRET_{index}.
    """
    idx = CHANNEL_INDEX.get(channel_name, 1)
    
    secret = os.environ.get(f"YOUTUBE_CLIENT_SECRET_{idx}", "")
    if secret:
        return secret
    
    raise ValueError(
        f"No client secret found for channel {channel_name} (idx={idx}). "
        f"Set YOUTUBE_CLIENT_SECRET_{idx} in GitHub Secrets."
    )


def get_refresh_token(channel_name):
    """
    Get OAuth2 refresh token for a specific channel.
    STRICT isolation: only returns YOUTUBE_REFRESH_TOKEN_{index}.
    """
    idx = CHANNEL_INDEX.get(channel_name, 1)
    
    token = os.environ.get(f"YOUTUBE_REFRESH_TOKEN_{idx}", "")
    if token:
        return token
    
    raise ValueError(
        f"No refresh token found for channel {channel_name} (idx={idx}). "
        f"Set YOUTUBE_REFRESH_TOKEN_{idx} in GitHub Secrets."
    )


def get_youtube_service_for_channel(channel_name):
    """
    Build YouTube API service for a specific channel with its own credentials.
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    
    client_secret_raw = get_client_secret(channel_name)
    refresh_token = get_refresh_token(channel_name)
    
    # Parse client secret JSON
    try:
        secret_data = json.loads(client_secret_raw)
        installed = secret_data.get("installed", secret_data.get("web", {}))
        client_id = installed.get("client_id", "")
        client_secret_val = installed.get("client_secret", "")
    except json.JSONDecodeError:
        # If not JSON, try as raw values
        client_id = os.environ.get(f"YOUTUBE_CLIENT_ID_{CHANNEL_INDEX.get(channel_name, 1)}", "")
        client_secret_val = client_secret_raw
    
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret_val,
        token_uri="https://oauth2.googleapis.com/token"
    )
    
    service = build("youtube", "v3", credentials=credentials)
    logger.info(f"YouTube service built for channel: {channel_name} (index {CHANNEL_INDEX.get(channel_name, '?')})")
    return service


def get_analytics_service_for_channel(channel_name):
    """
    Build YouTube Analytics API service for a specific channel.
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    
    client_secret_raw = get_client_secret(channel_name)
    refresh_token = get_refresh_token(channel_name)
    
    try:
        secret_data = json.loads(client_secret_raw)
        installed = secret_data.get("installed", secret_data.get("web", {}))
        client_id = installed.get("client_id", "")
        client_secret_val = installed.get("client_secret", "")
    except json.JSONDecodeError:
        client_id = os.environ.get(f"YOUTUBE_CLIENT_ID_{CHANNEL_INDEX.get(channel_name, 1)}", "")
        client_secret_val = client_secret_raw
    
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret_val,
        token_uri="https://oauth2.googleapis.com/token"
    )
    
    return build("youtubeAnalytics", "v2", credentials=credentials)


def get_gemini_api_key(channel_name):
    """
    Get Gemini API key for a specific channel.
    STRICT isolation: only returns GEMINI_API_KEY_{index}.
    """
    idx = CHANNEL_INDEX.get(channel_name, 1)
    
    key = os.environ.get(f"GEMINI_API_KEY_{idx}", "")
    if key:
        return key
    
    raise ValueError(
        f"No Gemini API key found for channel {channel_name} (idx={idx}). "
        f"Set GEMINI_API_KEY_{idx} in GitHub Secrets."
    )


def list_all_credentials_status():
    """Debug: print which credentials are set for each channel."""
    print("\nCredential Status:")
    print("=" * 60)
    for channel_name, idx in CHANNEL_INDEX.items():
        yt_key = "OK" if os.environ.get(f"YOUTUBE_API_KEY_{idx}") else "MISSING"
        client = "OK" if os.environ.get(f"YOUTUBE_CLIENT_SECRET_{idx}") else "MISSING"
        token = "OK" if os.environ.get(f"YOUTUBE_REFRESH_TOKEN_{idx}") else "MISSING"
        gemini = "OK" if os.environ.get(f"GEMINI_API_KEY_{idx}") else "MISSING"
        print(f"  {channel_name:<10} (#{idx}): YT_KEY={yt_key}  CLIENT={client}  TOKEN={token}  GEMINI={gemini}")
    print("=" * 60)
