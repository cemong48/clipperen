# scripts/generate_refresh_tokens.py
# Run ONCE locally to generate OAuth2 refresh tokens for all 5 channels.
# Each channel needs its own refresh token.
#
# Prerequisites:
#   pip install google-auth-oauthlib google-api-python-client
#
# Usage:
#   python scripts/generate_refresh_tokens.py
#
# The script will:
#   1. Ask you to place each channel's client_secret JSON file
#   2. Open browser for OAuth2 consent (login with each channel's Google account)
#   3. Print the refresh token → you copy-paste into GitHub Secrets

import json
import os
import sys

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly"
]

CHANNELS = {
    1: "psyched (Psychology & Self-Improvement)",
    2: "minted (Finance & Business)",
    3: "vitals (Health & Science)",
    4: "wired (Tech & AI)",
    5: "sage (Philosophy & Wisdom)"
}


def generate_token_for_channel(channel_idx):
    """Generate refresh token for one channel."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: Install required package:")
        print("  pip install google-auth-oauthlib")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"Channel #{channel_idx}: {CHANNELS[channel_idx]}")
    print(f"{'='*60}")
    
    # Look for client secret file
    possible_names = [
        f"client_secret_{channel_idx}.json",
        f"client_secret_channel_{channel_idx}.json",
        f"secrets/client_secret_{channel_idx}.json"
    ]
    
    secret_file = None
    for name in possible_names:
        if os.path.exists(name):
            secret_file = name
            break
    
    if not secret_file:
        secret_file = input(
            f"Enter path to client_secret JSON for channel #{channel_idx} "
            f"({CHANNELS[channel_idx]}): "
        ).strip().strip('"')
    
    if not os.path.exists(secret_file):
        print(f"ERROR: File not found: {secret_file}")
        return None
    
    print(f"Using: {secret_file}")
    print(f"⚠️  Browser will open — LOGIN with the Google account for: {CHANNELS[channel_idx]}")
    print(f"   Make sure you login with the CORRECT account!\n")
    
    input("Press ENTER when ready to open browser...")
    
    flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
    credentials = flow.run_local_server(port=8080 + channel_idx)
    
    refresh_token = credentials.refresh_token
    
    if refresh_token:
        print(f"\n✅ SUCCESS! Refresh token for channel #{channel_idx}:")
        print(f"\n{'─'*40}")
        print(refresh_token)
        print(f"{'─'*40}")
        print(f"\n📋 Copy the above token and paste it into GitHub Secrets as:")
        print(f"   Secret name: YOUTUBE_REFRESH_TOKEN_{channel_idx}")
        print(f"   Secret value: {refresh_token}")
        return refresh_token
    else:
        print(f"❌ FAILED: No refresh token received for channel #{channel_idx}")
        return None


def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║     YouTube Clipper — Refresh Token Generator            ║
║     Generate OAuth2 tokens for all 5 channels            ║
╚══════════════════════════════════════════════════════════╝
    
Before starting, prepare:
  1. Download client_secret JSON for each channel from Google Cloud Console
  2. Name them: client_secret_1.json, client_secret_2.json, etc.
  3. Place them in the project root or secrets/ folder
  
Channel mapping:
  #1 = psyched (Psychology & Self-Improvement)
  #2 = minted (Finance & Business)
  #3 = vitals (Health & Science)
  #4 = wired (Tech & AI)
  #5 = sage (Philosophy & Wisdom)
""")
    
    all_tokens = {}
    
    for idx in range(1, 6):
        token = generate_token_for_channel(idx)
        if token:
            all_tokens[idx] = token
        
        if idx < 5:
            cont = input(f"\nProceed to channel #{idx+1}? (y/n): ").strip().lower()
            if cont != 'y':
                break
    
    # Summary
    print(f"\n\n{'='*60}")
    print("SUMMARY — GitHub Secrets to set:")
    print(f"{'='*60}")
    
    for idx, token in all_tokens.items():
        print(f"  YOUTUBE_REFRESH_TOKEN_{idx} = {token[:20]}...{token[-10:]}")
    
    missing = [i for i in range(1, 6) if i not in all_tokens]
    if missing:
        print(f"\n⚠️  Missing tokens for channel(s): {missing}")
        print("   Run this script again to generate the missing tokens.")
    else:
        print(f"\n✅ All 5 refresh tokens generated!")
        print("   Paste them into: https://github.com/cemong48/clipperen/settings/secrets/actions")


if __name__ == "__main__":
    main()
