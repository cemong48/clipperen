# scripts/verify_seeds.py
# Run once: python scripts/verify_seeds.py
# Purpose: Verify all 25 seed channel IDs before first pipeline run

import json
import os
import time
import requests

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
SEEDS_PATH = "config/seeds.json"
REPORT_PATH = "logs/seed_verification_report.json"


def verify_channel_id(channel_id, channel_name):
    """
    Check if a channel_id is valid via YouTube Data API.
    Returns dict with status and corrected ID if found.
    """
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "snippet,status",
        "id": channel_id,
        "key": YOUTUBE_API_KEY
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        return {
            "status": "error",
            "channel_id": channel_id,
            "channel_name": channel_name,
            "reason": str(e)
        }

    if data.get("pageInfo", {}).get("totalResults", 0) > 0:
        item = data["items"][0]
        actual_name = item["snippet"]["title"]
        return {
            "status": "valid",
            "channel_id": channel_id,
            "channel_name": channel_name,
            "actual_name": actual_name,
            "name_match": actual_name.lower() == channel_name.lower()
        }
    else:
        # ID invalid — try lookup by handle/search
        return lookup_by_search(channel_id, channel_name)


def lookup_by_search(original_id, channel_name):
    """
    Fallback: search YouTube for the channel by name
    and attempt to recover the correct ID.
    """
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": channel_name,
        "type": "channel",
        "maxResults": 3,
        "key": YOUTUBE_API_KEY
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        return {
            "status": "unresolvable",
            "channel_id": original_id,
            "channel_name": channel_name,
            "reason": f"Search failed: {e}"
        }

    items = data.get("items", [])
    if not items:
        return {
            "status": "unresolvable",
            "channel_id": original_id,
            "channel_name": channel_name,
            "reason": "No search results found"
        }

    # Return best candidate (first result)
    best = items[0]
    recovered_id = best["snippet"]["channelId"]
    recovered_name = best["snippet"]["channelTitle"]

    return {
        "status": "recovered",
        "channel_id": original_id,
        "corrected_id": recovered_id,
        "channel_name": channel_name,
        "recovered_name": recovered_name,
        "action_required": "Update seeds.json with corrected_id"
    }


def auto_patch_seeds(results):
    """
    Automatically update seeds.json with recovered IDs.
    Only patches entries with status = "recovered".
    Leaves "unresolvable" entries unchanged for manual fix.
    """
    with open(SEEDS_PATH, encoding="utf-8") as f:
        seeds = json.load(f)

    patched = 0
    for theme in seeds["seeds"]:
        for channel in theme["channels"]:
            for result in results:
                if (result["channel_id"] == channel["channel_id"] and
                        result["status"] == "recovered"):
                    old_id = channel["channel_id"]
                    channel["channel_id"] = result["corrected_id"]
                    print(f"  ✅ PATCHED: {channel['name']}")
                    print(f"     {old_id} → {result['corrected_id']}")
                    patched += 1

    if patched > 0:
        with open(SEEDS_PATH, "w", encoding="utf-8") as f:
            json.dump(seeds, f, indent=2, ensure_ascii=False)
        print(f"\n  seeds.json updated with {patched} correction(s).")

    return patched


def run_verification():
    if not YOUTUBE_API_KEY:
        print("❌ ERROR: YOUTUBE_API_KEY not set.")
        print("   Set it: export YOUTUBE_API_KEY='your_key_here'")
        exit(1)

    with open(SEEDS_PATH, encoding="utf-8") as f:
        seeds = json.load(f)

    all_channels = []
    for theme in seeds["seeds"]:
        for ch in theme["channels"]:
            all_channels.append({
                "theme": theme["theme"],
                "name": ch["name"],
                "channel_id": ch["channel_id"]
            })

    print(f"\n🔍 Verifying {len(all_channels)} seed channels...\n")
    print("=" * 60)

    results = []
    valid = 0
    recovered = 0
    unresolvable = 0

    for i, ch in enumerate(all_channels, 1):
        print(f"[{i:2d}/25] {ch['name']:<35}", end=" ")
        result = verify_channel_id(ch["channel_id"], ch["name"])
        result["theme"] = ch["theme"]
        results.append(result)

        if result["status"] == "valid":
            match = "✓ name match" if result["name_match"] else f"⚠ actual: {result['actual_name']}"
            print(f"✅  VALID    {match}")
            valid += 1
        elif result["status"] == "recovered":
            print(f"🔄  RECOVERED → {result['corrected_id']}")
            recovered += 1
        else:
            print(f"❌  FAILED   {result.get('reason', 'Unknown')}")
            unresolvable += 1

        # Respect YouTube API quota — 1 req/sec
        time.sleep(1.1)

    print("\n" + "=" * 60)
    print(f"\n📊 SUMMARY")
    print(f"   ✅ Valid        : {valid}")
    print(f"   🔄 Recovered    : {recovered}")
    print(f"   ❌ Unresolvable : {unresolvable}")

    # Auto-patch recovered IDs
    if recovered > 0:
        print(f"\n🔧 Auto-patching {recovered} recovered ID(s) in seeds.json...")
        auto_patch_seeds(results)

    # Save full report
    os.makedirs("logs", exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": {
                "total": len(all_channels),
                "valid": valid,
                "recovered": recovered,
                "unresolvable": unresolvable
            },
            "results": results
        }, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Full report saved to: {REPORT_PATH}")

    # Exit with error code if any unresolvable — blocks pipeline from running
    if unresolvable > 0:
        print(f"\n⚠️  ACTION REQUIRED: {unresolvable} channel(s) could not be resolved.")
        print("   Edit config/seeds.json manually to fix or remove them.")
        print("   Then re-run: python scripts/verify_seeds.py")
        exit(1)
    else:
        print(f"\n✅ All channels verified. System is ready to run.")
        exit(0)


if __name__ == "__main__":
    run_verification()
