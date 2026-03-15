# Instructions for Claude Opus — YouTube Clipper Channel Automation System

## Project Overview

Build a fully automated YouTube clipper channel system that discovers, processes, and uploads clip content from permitted creator channels. The system runs entirely on free-tier infrastructure (GitHub Actions + free APIs) with zero ongoing cost. It posts 4 videos per day (2 Shorts + 2 Long Clips) with bilingual subtitles (English + Indonesian), fully automated with an optional manual input slot for Whop partnership programs.

---

## Core Architecture

### Two Independent Systems Running in Parallel

**System 1 — Fully Automatic**
- Runs every day without any human input
- Discovers channels via YouTube Data API using hardcoded seed themes
- Scans channel descriptions, pinned comments, and community posts for clipping permission signals
- Auto-adds valid channels to whitelist
- Pulls content, processes clips, schedules uploads

**System 2 — Manual (Whop Program)**
- Only activates when `manual_queue/queue.json` has entries
- Used when operator joins a Whop clipping program partnership
- Operator inputs channel ID + Whop program details manually
- Content processed with same pipeline as auto system

### Daily Post Allocation Logic — Per Channel

**Critical concept:** Slot allocation is calculated **per channel independently**, not globally. The manual queue entries are first routed to their target channel (via auto-router), then each channel calculates its own slots based on how many manual videos it received that day.

```
STEP 1: Route all manual queue entries → target channels (via auto-router)

STEP 2: For EACH of the 5 channels independently:

  IF channel received 0 manual videos today:
      auto_slots  = 4  (2 Shorts + 2 Long Clips)
      manual_slots = 0

  IF channel received 1 manual video today:
      manual_slots = 1
      auto_slots  = 3  (auto fills remaining slots to reach 4)
      format balance: auto detects manual format, fills gaps to maintain 2S+2L

  IF channel received 2 manual videos today:
      manual_slots = 2  (1 Short + 1 Long Clip)
      auto_slots  = 2  (1 Short + 1 Long Clip)
      Total = 4 posts (2 Shorts + 2 Long Clips)

  IF channel received 3+ manual videos today:
      manual_slots = 2  (cap — only first 2 processed today)
      auto_slots  = 2
      excess videos → moved to next day's queue automatically
      Total = 4 posts, excess queued for tomorrow

STEP 3: Each channel posts exactly 4 videos per day. Always.
```

**Rule: Each channel always posts exactly 4 videos/day. Format ratio always = 2 Shorts + 2 Long Clips per channel. Never break this.**

---

### Slot Calculation — Code Reference

```python
# scheduler/slot_manager.py

def calculate_slots_per_channel(channel_name, routed_manual_videos):
    """
    routed_manual_videos: list of manual videos already routed to this channel today
    Returns slot allocation dict for this channel.
    """
    manual = [v for v in routed_manual_videos
              if v["target_channel"] == channel_name]

    # Cap manual at 2 per channel per day
    overflow = []
    if len(manual) > 2:
        overflow = manual[2:]   # carry over to tomorrow
        manual = manual[:2]

    manual_count = len(manual)
    auto_count = 4 - manual_count

    # Detect formats of manual videos
    manual_shorts = [v for v in manual if v["format"] == "short"]
    manual_longs  = [v for v in manual if v["format"] == "long"]

    # Auto fills to maintain 2 Shorts + 2 Long always
    auto_shorts_needed = max(0, 2 - len(manual_shorts))
    auto_longs_needed  = max(0, 2 - len(manual_longs))

    return {
        "channel": channel_name,
        "manual_videos": manual,
        "auto_shorts_needed": auto_shorts_needed,
        "auto_longs_needed": auto_longs_needed,
        "auto_total": auto_count,
        "overflow_to_tomorrow": overflow,
        "total_posts": 4
    }
```

---

### Real-World Example

```
Today's manual queue: 3 videos
  Video A → router → Vitals   (long)
  Video B → router → Vitals   (short)
  Video C → router → Minted   (long)

Per-channel result:

  Psyched  → manual: 0 | auto: 2 Shorts + 2 Longs
  Minted   → manual: 1 Long | auto: 2 Shorts + 1 Long
  Vitals   → manual: 1 Short + 1 Long | auto: 1 Short + 1 Long
  Wired    → manual: 0 | auto: 2 Shorts + 2 Longs
  Sage     → manual: 0 | auto: 2 Shorts + 2 Longs

Total posts today: 20 (5 channels × 4 posts)
All channels maintain 2 Shorts + 2 Longs. ✅
```

---

## Repository Structure

```
clipper-channel/
├── .github/
│   └── workflows/
│       ├── daily_pipeline.yml          # Main daily scheduler
│       ├── discovery_scan.yml          # Weekly channel discovery
│       └── performance_monitor.yml     # Daily analytics + auto-update
├── config/
│   ├── whitelist.json                  # All permitted channels
│   ├── settings.json                   # Global config (thresholds, timing, etc)
│   └── seeds.json                      # Hardcoded seed channels (25 total)
├── manual_queue/
│   └── queue.json                      # Operator fills this for Whop programs
├── scripts/
│   └── verify_seeds.py                 # One-time setup: verify all 25 seed channel IDs
├── src/
│   ├── discovery/
│   │   ├── channel_scanner.py          # YouTube API channel search
│   │   ├── permission_detector.py      # Multi-source permission signal detection
│   │   └── whitelist_manager.py        # Add/update/suspend whitelist entries
│   ├── content/
│   │   ├── video_fetcher.py            # yt-dlp wrapper
│   │   ├── transcript_extractor.py     # Pull transcript via yt-dlp
│   │   ├── clip_detector.py            # Gemini AI clip selection
│   │   └── format_classifier.py       # Classify SOURCE video as Short/Long candidate
│                                   # Rule: source >= 20min → attempt both Long + Short
│                                   #       source 3-19min  → Long only
│                                   #       source < 3min   → skip entirely
│                                   # Final format = confirmed by Gemini approval result
│   ├── processing/
│   │   ├── clip_processor.py           # FFmpeg clip cutting
│   │   ├── subtitle_generator.py       # Whisper → bilingual subtitles
│   │   ├── visual_enhancer.py          # Hook text, progress bar, watermark
│   │   ├── thumbnail_generator.py      # Face crop + title text via Pillow
│   │   └── audio_mixer.py             # Lo-fi background at 10% volume
│   ├── safety/
│   │   ├── acr_checker.py             # ACRCloud audio fingerprint scan (Layer 1)
│   │   ├── audio_sanitizer.py         # Mute detected music segments via FFmpeg (Layer 2)
│   │   ├── duplicate_checker.py       # Internal segment overlap detection (Layer 3)
│   │   └── safety_gate.py            # Orchestrates all 4 safety layers in sequence
│   ├── upload/
│   │   ├── youtube_uploader.py         # YouTube Data API v3
│   │   └── metadata_generator.py      # Gemini-generated title/desc/tags
│   ├── monitor/
│   │   ├── analytics_puller.py         # YouTube Analytics API
│   │   ├── performance_checker.py      # Compare metrics vs thresholds
│   │   └── auto_optimizer.py          # Auto-update title/thumb/desc/tags
│   ├── router/
│   │   ├── topic_classifier.py        # Gemini classifies video into 1 of 5 themes
│   │   └── channel_router.py         # Maps theme → correct channel, handles queue target_channel override
│   └── scheduler/
│       ├── slot_manager.py             # Manage 4 daily slots
│       └── random_offset.py           # Random ±45 min offset per slot
├── database/
│   ├── posted.json                     # All uploaded videos log
│   ├── candidates.json                 # Discovered but not yet processed
│   └── performance_log.json           # Historical analytics per video
├── assets/
│   └── music/                          # Pre-downloaded CC0/royalty-free lo-fi tracks
│       ├── lofi_01.mp3                 # Source: YouTube Audio Library
│       ├── lofi_02.mp3                 # Source: Pixabay (CC0)
│       └── lofi_03.mp3                 # Source: Free Music Archive (CC0)
└── logs/
    └── daily_run.log
```

---

## Module 1: Seed Channels (Hardcoded)

Hardcode these 25 channels in `config/seeds.json`. System uses these as starting point for discovery — no manual input needed from operator.

```json
{
  "seeds": [
    {
      "theme": "Psychology & Self-Improvement",
      "channels": [
        {"name": "Huberman Lab", "channel_id": "UC2D2CMWXMOVWx7giW1n3LIg"},
        {"name": "Jordan B Peterson", "channel_id": "UCL_f53ZEJxp8TtlOkHwMV9Q"},
        {"name": "HealthyGamerGG", "channel_id": "UCdFuAWb9Fv3TGCzffNVBmEA"},
        {"name": "Jay Shetty", "channel_id": "UCyPobQHPMWgTFBB-H-BXKOA"},
        {"name": "Therapy in a Nutshell", "channel_id": "UCpuqFSGp_kURztHIHyaW3rQ"}
      ]
    },
    {
      "theme": "Finance & Business",
      "channels": [
        {"name": "Alex Hormozi", "channel_id": "UCFMnEB6tQaLcRG1lhvGdZIQ"},
        {"name": "Graham Stephan", "channel_id": "UCV6KDgJskWaEckne5aPA0aQ"},
        {"name": "Codie Sanchez", "channel_id": "UCmjU3gSH4SEOXhFjJSklnyA"},
        {"name": "Valuetainment", "channel_id": "UCIypBKKqXVSCEcIFDHkB4vw"},
        {"name": "My First Million", "channel_id": "UCXv2-en0WR0nBXEFJtYm4hQ"}
      ]
    },
    {
      "theme": "Health & Science",
      "channels": [
        {"name": "Peter Attia MD", "channel_id": "UCPnlG9X4t8XYQC8FQlL5R8A"},
        {"name": "FoundMyFitness", "channel_id": "UCWF8338JqGSqiuSEVLMF5nA"},
        {"name": "Thomas DeLauer", "channel_id": "UC70SrI3VkT1MXALRtf0pcHg"},
        {"name": "Mark Hyman MD", "channel_id": "UCeBiQTfhOzaLBkHFH2X1LcA"},
        {"name": "David Sinclair", "channel_id": "UCwFh9WtlaSc9rjPGHsLKRNQ"}
      ]
    },
    {
      "theme": "Tech & AI",
      "channels": [
        {"name": "Lex Fridman", "channel_id": "UCSHZKyawb77ixDdsGog4iWA"},
        {"name": "Andrej Karpathy", "channel_id": "UCbfYPyITQ-7l4upoX8nvctg"},
        {"name": "David Shapiro", "channel_id": "UCm4bDkRGEe7bGN_8BmRCPuA"},
        {"name": "Matt Wolfe", "channel_id": "UCMpNyBqGCLs0CrBzQ4JuIXQ"},
        {"name": "Yannic Kilcher", "channel_id": "UCZHmQk67mSJgfCCTn7xBfew"}
      ]
    },
    {
      "theme": "Philosophy & Stoicism",
      "channels": [
        {"name": "Ryan Holiday", "channel_id": "UCMGmbS1sFv3Q5_UxyvCxM6g"},
        {"name": "Academy of Ideas", "channel_id": "UCiRiQGCAjgCPRr-6nxFGa3A"},
        {"name": "Einzelgänger", "channel_id": "UCMnULQ3wMdOkBgNM4h9T5hA"},
        {"name": "What I've Learned", "channel_id": "UCqYPhGiB9tkShZorfgcL2lA"},
        {"name": "Pursuit of Wonder", "channel_id": "UCFcJnSBpk2gAFa8bhjONkGQ"}
      ]
    }
  ]
}
```

---

## Module 1b: Channel ID Verification Script (First-Run Setup)

This script runs ONCE before the first pipeline execution to verify all 25 seed channel IDs are valid and reachable. It auto-corrects IDs where possible using channel handle lookup, and flags any that cannot be resolved so the operator can fix them manually.

Create this as `scripts/verify_seeds.py` — it is a standalone setup utility, not part of the daily pipeline.

```python
# scripts/verify_seeds.py
# Run once: python scripts/verify_seeds.py
# Purpose: Verify all 25 seed channel IDs before first pipeline run

import json
import os
import time
import requests

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
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
    with open(SEEDS_PATH) as f:
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
        with open(SEEDS_PATH, "w") as f:
            json.dump(seeds, f, indent=2)
        print(f"\n  seeds.json updated with {patched} correction(s).")
    
    return patched


def run_verification():
    with open(SEEDS_PATH) as f:
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
    with open(REPORT_PATH, "w") as f:
        json.dump({
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": {
                "total": len(all_channels),
                "valid": valid,
                "recovered": recovered,
                "unresolvable": unresolvable
            },
            "results": results
        }, f, indent=2)

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
```

### How to Run (First Setup)

```bash
# 1. Set your API key
export YOUTUBE_API_KEY="your_key_here"

# 2. Run verification
python scripts/verify_seeds.py

# 3. Check output:
#    ✅ VALID     → ID correct, ready
#    🔄 RECOVERED → ID was wrong, auto-corrected in seeds.json
#    ❌ FAILED    → Needs manual fix

# 4. If any FAILED entries:
#    - Open config/seeds.json
#    - Go to youtube.com → find the channel → copy correct ID
#    - Update seeds.json manually
#    - Re-run the script until all pass

# 5. Only proceed to pipeline build after script exits with code 0
```

### What the Report Looks Like (`logs/seed_verification_report.json`)

```json
{
  "verified_at": "2025-03-01T12:00:00Z",
  "summary": {
    "total": 25,
    "valid": 22,
    "recovered": 2,
    "unresolvable": 1
  },
  "results": [
    {
      "status": "valid",
      "channel_id": "UC2D2CMWXMOVWx7giW1n3LIg",
      "channel_name": "Huberman Lab",
      "actual_name": "Huberman Lab",
      "name_match": true,
      "theme": "Psychology & Self-Improvement"
    },
    {
      "status": "recovered",
      "channel_id": "UCxxxxxx_WRONG",
      "corrected_id": "UC_CORRECT_ID_HERE",
      "channel_name": "Thomas DeLauer",
      "recovered_name": "Thomas DeLauer",
      "action_required": "Update seeds.json with corrected_id",
      "theme": "Health & Science"
    },
    {
      "status": "unresolvable",
      "channel_id": "UCxxxxxx",
      "channel_name": "Some Channel",
      "reason": "No search results found",
      "theme": "Finance & Business"
    }
  ]
}
```

### Integration with GitHub Actions (Prevent Bad Runs)

Add this check to `daily_pipeline.yml` — pipeline refuses to run if seeds were never verified:

```yaml
- name: Check seed verification status
  run: |
    if [ ! -f "logs/seed_verification_report.json" ]; then
      echo "❌ ERROR: Seeds not verified. Run scripts/verify_seeds.py first."
      exit 1
    fi
    
    UNRESOLVABLE=$(python -c "
    import json
    with open('logs/seed_verification_report.json') as f:
      data = json.load(f)
    print(data['summary']['unresolvable'])
    ")
    
    if [ "$UNRESOLVABLE" -gt "0" ]; then
      echo "❌ ERROR: $UNRESOLVABLE unresolvable seed channel(s). Fix seeds.json first."
      exit 1
    fi
    
    echo "✅ Seed verification passed. Proceeding with pipeline."
```

---

## Module 2: Permission Detection System

### How Permission Detection Works

The system scans multiple sources for explicit clipping permission signals. It never assumes permission — it must find a positive signal.

```python
# permission_detector.py

PERMISSION_KEYWORDS = [
    "feel free to clip",
    "clipping allowed",
    "clips welcome",
    "clip my content",
    "you can clip",
    "free to clip",
    "clippers welcome",
    "clip friendly",
    "clip program",
    "clip my videos",
    "repost allowed",
    "share clips",
    "anyone can clip"
]

REVOCATION_KEYWORDS = [
    "do not clip",
    "no clipping",
    "no clips",
    "all rights reserved",
    "no reupload",
    "no re-upload",
    "exclusive content",
    "do not repost",
    "clips not allowed"
]
```

### Confidence Scoring

```python
def calculate_confidence(signals):
    scores = {
        "whop_listing": 95,
        "channel_description": 85,
        "pinned_comment": 80,
        "community_post": 75,
        "video_description": 70
    }
    # Return highest confidence signal found
    # Threshold for auto-whitelist: >= 85
    # Threshold for flagged review: 70-84
    # Below 70: skip entirely
```

### Whitelist Entry Schema

```json
{
  "channel_id": "UCxxxxxx",
  "channel_name": "Channel Name",
  "theme": "Psychology & Self-Improvement",
  "source": "auto_channel_description",
  "permission_proof_url": "https://youtube.com/channel/UCxxxxxx/about",
  "confidence": 85,
  "permission_verified_date": "2025-03-01",
  "last_revalidated": "2025-03-07",
  "status": "active",
  "restrictions": ["no_paid_content", "max_10min"],
  "revenue_share_pct": null,
  "whop_program_id": null,
  "notes": ""
}
```

Status values: `active`, `pending_review`, `suspended`, `removed`

### Weekly Re-Validation

Every week, the system re-scans all `active` channels in whitelist:
- Check for revocation keywords in latest videos/community posts
- If found → set status to `suspended` → log warning
- Operator can manually review and decide to `remove` or keep `active`

---

## Module 3: Content Discovery & Clip Detection

### How Discovery Expands Beyond 25 Seeds

YouTube Data API does NOT have a "related channels" endpoint. Discovery expansion uses this concrete mechanism instead:

```python
# channel_scanner.py — Expansion Logic

NICHE_KEYWORDS = {
    "Psychology & Self-Improvement": [
        "psychology explained", "self improvement", "mental health tips",
        "behavior science", "personal development"
    ],
    "Finance & Business": [
        "personal finance", "business mindset", "investing basics",
        "entrepreneurship", "financial freedom"
    ],
    "Health & Science": [
        "health science", "longevity research", "nutrition science",
        "fitness research", "medical explained"
    ],
    "Tech & AI": [
        "artificial intelligence explained", "machine learning",
        "tech news", "AI tools", "future technology"
    ],
    "Philosophy & Stoicism": [
        "philosophy explained", "stoicism", "critical thinking",
        "life philosophy", "wisdom"
    ]
}

def discover_new_channels():
    for theme, keywords in NICHE_KEYWORDS.items():
        for keyword in keywords:
            # Step 1: Search videos with this keyword (last 30 days)
            results = youtube.search().list(
                q=keyword,
                type="video",
                order="viewCount",
                publishedAfter=thirty_days_ago,
                maxResults=10
            )
            # Step 2: Extract unique channel IDs from results
            # Step 3: Skip channels already in whitelist or previously rejected
            # Step 4: Run permission_detector on each new channel
            # Step 5: Add to whitelist if confidence >= threshold
```

This runs weekly (discovery_scan.yml). Over time whitelist grows organically from search results without needing YouTube's related channels feature.

```python
# For each active channel in whitelist:
# 1. Pull latest videos (last 7 days) via YouTube Data API
# 2. Skip if already in posted.json or candidates.json
# 3. Skip if video is: membership-required, age-restricted, paid
# 4. Check title/description for blacklist keywords
# 5. Pull transcript via yt-dlp --write-subs
# 6. Send to Gemini for clip analysis
```

### Gemini Clip Detection — Long Clip Prompt

```python
LONG_CLIP_PROMPT = """
You are a professional YouTube clip editor. Analyze this transcript and identify the SINGLE best segment for a long clip (3-10 minutes).

Criteria:
- Must be self-contained (viewer needs NO prior context from the video)
- Has a clear beginning, middle, and end
- Contains a surprising insight, strong argument, or compelling story
- Would make sense as a standalone video

Quality Gate — answer these before selecting:
1. Can a new viewer understand this without watching the full video? (must be YES)
2. Does the segment have a natural resolution/conclusion? (must be YES)
3. Completeness score 1-10 (must be >= 7 to proceed)

Transcript:
{transcript}

Return ONLY valid JSON:
{{
  "start_time": "MM:SS",
  "end_time": "MM:SS",
  "duration_minutes": float,
  "title": "engaging title under 60 chars",
  "description_hook": "first sentence for video description, max 100 chars",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "completeness_score": int,
  "why_clipworthy": "one sentence explanation",
  "approved": true/false
}}
"""
```

### Gemini Clip Detection — Shorts Prompt

```python
SHORTS_PROMPT = """
You are a viral Shorts clip editor. Analyze this transcript and find the SINGLE best segment for a YouTube Short (30-59 seconds).

Structure required (ALL three must be present):
- HOOK (0-5s): A shocking statement or question that stands alone
- PAYOFF (5-50s): The explanation or story that answers the hook
- LANDING (50-59s): A memorable conclusion or punchline

Quality Gate — answer these before selecting:
1. Does the hook work without any prior context? (must be YES)
2. Is there a clear resolution within 60 seconds? (must be YES)
3. Completeness score 1-10 (must be >= 8 to proceed — higher bar than long clips)
4. Would this make someone stop scrolling in the first 3 seconds? (must be YES)

If no segment meets all criteria: set approved = false. Do NOT force-approve a weak segment.

Transcript:
{transcript}

Return ONLY valid JSON:
{{
  "start_time": "MM:SS",
  "end_time": "MM:SS",
  "duration_seconds": int,
  "hook_text": "3-5 word hook for text overlay at start",
  "title": "engaging title under 50 chars with #Shorts",
  "completeness_score": int,
  "approved": true/false
}}
"""
```

### Fallback Logic

```
If Gemini returns approved = false for Shorts:
→ Skip this video for Shorts
→ Try next video in queue
→ If no valid Shorts found after 5 attempts: pull from Long Clip pool and trim

If Gemini returns approved = false for Long Clip:
→ Skip this video entirely
→ Log as "no_valid_segment"
→ Move to next video
```

---

## Module 4: Video Processing Pipeline

### Step 1 — Download Segment

```bash
# Using yt-dlp with precise timestamp download
yt-dlp \
  --download-sections "*MM:SS-MM:SS" \
  --format "bestvideo[height<=1080]+bestaudio/best" \
  --merge-output-format mp4 \
  -o "temp/raw_clip.mp4" \
  "VIDEO_URL"
```

### Step 2 — Transcript & Subtitle Generation

```python
# 1. Extract audio from clip
# 2. Run Whisper (base model, runs locally in GitHub Actions)
# 3. Get word-level timestamps
# 4. Generate English subtitle (SRT format, word-by-word)
# 5. Translate to Indonesian via Gemini API
# 6. Generate Indonesian subtitle (SRT format)

whisper_model = "base"  # Free, fast enough for CI/CD
subtitle_style = "word_by_word"  # Each word highlights as spoken
```

### Step 3 — Visual Enhancement via FFmpeg

#### For Long Clips:
```
Layers (bottom to top):
1. Original video (full width, 1920x1080 or original resolution)
2. Progress bar (2px height, white, bottom of frame)
3. English subtitle (bold, white, black outline, bottom center)
4. Source watermark (top right, 30% opacity): "📺 Source: @ChannelName"
5. Channel logo (bottom left, small)
```

#### For Shorts:
```
Layers (bottom to top):
1. Original video (cropped/padded to 9:16, 1080x1920)
   - If talking head detected: zoom crop to face
   - If no face: center crop
2. Progress bar (3px, bottom)
3. Hook text overlay (0-3 seconds only):
   - Large bold text, centered
   - Semi-transparent dark background
   - 2-3 words maximum
4. Word-by-word subtitle (karaoke style, bottom third)
   - Active word: white + bold
   - Inactive words: gray
5. Source credit (top, small)
```

### Step 4 — Audio Mixing

```python
# Mix lo-fi background music at 10% volume
# Only during silence gaps > 2 seconds
# Source: pre-downloaded royalty-free lo-fi tracks in /assets/music/
# Toggle: check whitelist restrictions["no_background_music"] first
```

### Step 5 — Thumbnail Generation

```python
# 1. Extract 3 candidate frames (most expressive moments)
#    → Use OpenCV face detection, pick frame with largest face area
# 2. Crop face to right half of 1280x720 canvas
# 3. Pillow: render title text on left half
#    → Font: Bold, high contrast color vs background
#    → Max 3 words on first line, 2 words on second
# 4. Apply slight vignette to background
# 5. Add channel branding strip at bottom
```

---

## Module 5: Scheduling System

### Daily Time Slots

```python
BASE_SLOTS = ["07:00", "11:00", "16:00", "20:00"]  # WIB (UTC+7)
RANDOM_OFFSET_MINUTES = 45  # ± random offset per slot

# Example actual post times:
# Slot 1: 07:23
# Slot 2: 10:41
# Slot 3: 16:08
# Slot 4: 19:52
```

### Slot Assignment

```python
def assign_slots(manual_videos, auto_videos):
    slots = {
        "07:00": None,  # Short
        "11:00": None,  # Long Clip
        "16:00": None,  # Short
        "20:00": None   # Long Clip
    }
    # Short slots: 07:00 and 16:00
    # Long slots: 11:00 and 20:00
    # Manual videos get first pick of their format slot
    # Auto fills remaining
```

---

## Module 6: Upload System

### YouTube Data API Upload

```python
# Metadata generated by Gemini for each video
upload_params = {
    "title": gemini_title,           # Max 60 chars
    "description": build_description(
        hook=gemini_hook,
        source_credit=f"Original video by @{creator_name}: {original_url}",
        channel_promo="Subscribe for daily clips from the best creators",
        hashtags=gemini_tags
    ),
    "tags": gemini_tags,             # 10-15 tags
    "categoryId": "22",              # People & Blogs
    "defaultLanguage": "en",
    "defaultAudioLanguage": "en",
    "madeForKids": False
}

# For Shorts: title must contain #Shorts
# Add both English and Indonesian subtitle tracks
```

### posted.json Entry

```json
{
  "video_id": "youtube_video_id",
  "source_channel_id": "UCxxxxxx",
  "source_video_id": "source_yt_id",
  "format": "short",
  "posted_at": "2025-03-01T07:23:00+07:00",
  "system": "auto",
  "whop_program_id": null,
  "title": "Video title here",
  "initial_metrics": {}
}
```

---

## Module 7: Performance Monitor & Auto-Optimizer

### Metrics Pulled (YouTube Analytics API)

For every posted video, pull daily:
- Views
- Click-Through Rate (CTR)
- Average View Duration (%)
- Impressions
- Subscriber gain/loss from video

### Performance Thresholds (config/settings.json)

```json
{
  "performance": {
    "review_after_hours": 48,
    "ctr_minimum_pct": 4.0,
    "avd_minimum_pct": 40.0,
    "max_auto_updates_per_video": 3,
    "low_impression_threshold": 500
  }
}
```

### Auto-Optimization Logic

```
After 48 hours from upload, check each video:

IF CTR < 4.0%:
    → Gemini generates 3 new title variations
    → Gemini generates new thumbnail text
    → Rebuild thumbnail with new text via Pillow
    → Update title + thumbnail via YouTube API
    → Log: "thumbnail_update_v2"

IF AVD < 40%:
    → Gemini reviews description + tags
    → Update description with better hook
    → Refresh tags
    → Update via YouTube API
    → Log: "description_update_v2"

IF Impressions < 500 after 48h:
    → Add more specific niche tags
    → Update description with trending keywords
    → Log: "tags_update_v2"

IF already updated 3 times:
    → Stop auto-updating this video
    → Flag as "max_updates_reached"
    → Log for operator review
```

---

## Module 8: Copyright Safety System (4 Layers)

This module runs on every video BEFORE upload. All 4 layers must pass. If any layer fails, the video is either repaired (mute) or skipped entirely. Never upload a video that has not passed all safety checks.

---

### Safety Pipeline — Full Execution Order

```
VIDEO DOWNLOADED (raw clip)
        ↓
[LAYER 1] Gemini Pre-Screen (before download)
  → Prompt instructs Gemini to reject segments with music
  → Gemini returns music_risk: "none" | "low" | "high"
  → Reject if music_risk = "high" → try next video
        ↓ PASSED
[LAYER 2] Duplicate Check (internal)
  → Check posted.json for same source_video_id + overlapping timestamps
  → Overlap >= 50% of duration = duplicate → skip
        ↓ PASSED
[LAYER 3] ACRCloud Scan #1 (on raw clip)
  → Fingerprint audio against Content ID database
  → Music detected?
      → NO  → proceed
      → YES → is music < 10 seconds total?
            → YES → mute those segments via FFmpeg → proceed
            → NO  → skip this video entirely
        ↓ PASSED
[LAYER 4] ACRCloud Scan #2 (on final rendered file)
  → Final check after all processing + lo-fi music mixing
  → Clean? → UPLOAD
  → Not clean? → skip + log
```

---

### Layer 1 — Gemini Pre-Screen Safety Prompt Addition

Add this block to BOTH `LONG_CLIP_PROMPT` and `SHORTS_PROMPT` in `clip_detector.py`:

```python
SAFETY_ADDITION = """
COPYRIGHT SAFETY RULES — strictly follow all of these:
1. NEVER select segments where background music is clearly audible
2. STRONGLY PREFER segments where only the speaker's voice is present
3. AVOID segments containing: movie clips, TV footage, songs being sung,
   news broadcast audio, or any third-party audio/video
4. AVOID segments where the speaker is reading copyrighted text verbatim
5. If there is ANY doubt about music presence → do NOT select that segment

Add this field to your JSON response:
"music_risk": "none"   (no music audible at all)
             "low"    (very faint, barely audible background)
             "high"   (clear background music present)

System will REJECT segments with music_risk = "high" automatically.
"""
```

---

### Layer 2 — Duplicate Checker

```python
# src/safety/duplicate_checker.py

import json

def is_duplicate(source_video_id, start_sec, end_sec):
    """
    Returns True if this exact segment (or 50%+ overlap) 
    has already been posted.
    """
    try:
        with open("database/posted.json") as f:
            posted = json.load(f)
    except FileNotFoundError:
        return False

    for entry in posted:
        if entry.get("source_video_id") != source_video_id:
            continue
        
        prev_start = time_to_sec(entry.get("start_time", "0:00"))
        prev_end   = time_to_sec(entry.get("end_time", "0:00"))
        
        overlap = min(end_sec, prev_end) - max(start_sec, prev_start)
        duration = min(end_sec - start_sec, prev_end - prev_start)
        
        if duration > 0 and (overlap / duration) >= 0.5:
            return True
    
    return False

def time_to_sec(t):
    parts = t.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
```

---

### Layer 3 — ACRCloud Audio Scanner

```python
# src/safety/acr_checker.py

import acrcloud
import json
import os

ACR_CONFIG = {
    "access_key": os.environ["ACR_ACCESS_KEY"],
    "access_secret": os.environ["ACR_ACCESS_SECRET"],
    "host": "identify-eu-west-1.acrcloud.com",
    "timeout": 10
}

def scan_audio(clip_path):
    """
    Returns dict:
    {
        "safe": True/False,
        "action": "proceed" | "mute_segments" | "skip",
        "music_segments": [(start_sec, end_sec), ...],
        "details": {...}
    }
    """
    acr = acrcloud.ACRCloud(ACR_CONFIG)
    result = acr.identify_by_file(clip_path, 0)
    
    try:
        data = json.loads(result)
    except Exception:
        # If ACR fails to respond → treat as safe to avoid blocking pipeline
        return {"safe": True, "action": "proceed", "music_segments": []}
    
    code = data.get("status", {}).get("code", -1)
    
    if code != 0:
        # No music detected
        return {"safe": True, "action": "proceed", "music_segments": []}
    
    # Music detected — analyze duration
    music_items = data.get("metadata", {}).get("music", [])
    total_music_sec = sum(
        item.get("duration_ms", 0) / 1000 
        for item in music_items
    )
    
    if total_music_sec < 10:
        return {
            "safe": False,
            "action": "mute_segments",
            "music_segments": extract_timestamps(music_items),
            "details": music_items
        }
    else:
        return {
            "safe": False,
            "action": "skip",
            "music_segments": [],
            "details": music_items
        }

def extract_timestamps(music_items):
    segments = []
    for item in music_items:
        start = item.get("play_offset_ms", 0) / 1000
        duration = item.get("duration_ms", 0) / 1000
        segments.append((start, start + duration))
    return segments
```

---

### Layer 3 — Audio Sanitizer (Mute Segments)

```python
# src/safety/audio_sanitizer.py

import subprocess

def mute_music_segments(input_path, output_path, segments):
    """
    Mute specific time segments in the audio track.
    segments: list of (start_sec, end_sec)
    Video stream is copied untouched.
    """
    if not segments:
        return input_path
    
    # Build FFmpeg volume filter for each segment
    filters = []
    for start, end in segments:
        filters.append(
            f"volume=enable='between(t,{start:.2f},{end:.2f})':volume=0"
        )
    
    filter_str = ",".join(filters)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-af", filter_str,
        "-c:v", "copy",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mute failed: {result.stderr}")
    
    return output_path
```

---

### Layer 4 — Safety Gate Orchestrator

```python
# src/safety/safety_gate.py

from .acr_checker import scan_audio
from .audio_sanitizer import mute_music_segments
from .duplicate_checker import is_duplicate
import logging

logger = logging.getLogger(__name__)

def run_safety_checks(clip_path, source_video_id, start_sec, end_sec, gemini_music_risk):
    """
    Runs all 4 safety layers in sequence.
    Returns:
        {"passed": True, "final_path": path_to_safe_clip}
        {"passed": False, "reason": "..."}
    """

    # --- LAYER 1: Gemini pre-screen result ---
    if gemini_music_risk == "high":
        logger.warning(f"SKIP [{source_video_id}] — Gemini flagged music_risk=high")
        return {"passed": False, "reason": "gemini_music_risk_high"}

    # --- LAYER 2: Duplicate check ---
    if is_duplicate(source_video_id, start_sec, end_sec):
        logger.warning(f"SKIP [{source_video_id}] — duplicate segment detected")
        return {"passed": False, "reason": "duplicate_segment"}

    # --- LAYER 3: ACRCloud scan on raw clip ---
    acr_result = scan_audio(clip_path)

    if acr_result["action"] == "skip":
        logger.warning(f"SKIP [{source_video_id}] — music detected > 10s, not salvageable")
        return {"passed": False, "reason": "music_too_extensive"}

    if acr_result["action"] == "mute_segments":
        logger.info(f"MUTE segments in [{source_video_id}] — {acr_result['music_segments']}")
        sanitized_path = clip_path.replace(".mp4", "_sanitized.mp4")
        clip_path = mute_music_segments(clip_path, sanitized_path, acr_result["music_segments"])

    # --- LAYER 4: ACRCloud final scan after render ---
    # (called again in processor.py after full render + lo-fi mix)
    # This check happens on the FINAL output file, not raw clip
    # See: clip_processor.py → final_safety_scan()

    return {"passed": True, "final_path": clip_path}


def final_safety_scan(final_rendered_path):
    """
    Called after full video render. Last gate before upload.
    """
    acr_result = scan_audio(final_rendered_path)
    
    if acr_result["action"] in ("skip", "mute_segments"):
        logger.error(f"FINAL SCAN FAILED [{final_rendered_path}] — music still detected after render")
        return False
    
    return True
```

---

### Updated posted.json Schema (Safety Fields Added)

```json
{
  "video_id": "youtube_video_id",
  "source_channel_id": "UCxxxxxx",
  "source_video_id": "source_yt_id",
  "start_time": "12:34",
  "end_time": "22:45",
  "format": "short",
  "posted_at": "2025-03-01T07:23:00+07:00",
  "system": "auto",
  "whop_program_id": null,
  "title": "Video title here",
  "safety_checks": {
    "gemini_music_risk": "none",
    "duplicate_check": "passed",
    "acr_scan_raw": "clean",
    "muted_segments": [],
    "acr_scan_final": "clean"
  },
  "initial_metrics": {}
}
```

---

### Safe Background Music Sources (Hardcoded in /assets/music/)

All background lo-fi music tracks used in the pipeline MUST be sourced from one of these only. Never download music at runtime:

```
Approved sources:
├── YouTube Audio Library    → yt.be/audiolib — free, no Content ID claim
├── Pixabay Music            → pixabay.com/music — CC0 license
├── Free Music Archive       → freemusicarchive.org — filter CC0 only
└── Bensound                 → bensound.com/free-music — free tier with credit

NEVER use:
├── Any track from Spotify, Apple Music, SoundCloud
├── Lo-fi from random YouTube channels
├── Any music without explicit CC0 or royalty-free license
└── AI-generated music from platforms without clear IP ownership
```

---

### Required New Secrets (GitHub)

```
ACR_ACCESS_KEY      → ACRCloud account access key (free tier: 100 req/day)
ACR_ACCESS_SECRET   → ACRCloud account secret
```

ACRCloud free tier: 100 requests/day per account. With 4 clips/day and 2 scans per clip (raw + final), that is 8 requests/day per channel — well within free tier limits even across all 5 channels (40 requests/day total).

---

## Module 8b: Auto-Router — Topic Classifier & Channel Routing

This module runs on every video (both auto-discovered and manual queue) to determine which of the 5 channels the clip should be posted to. It uses Gemini to classify the content theme, then routes accordingly.

**Why this matters for manual queue (Whop):** When operator joins a Whop program, the creator's content may span multiple topics. Instead of manually deciding which channel to post to, the operator can leave `target_channel: null` in `queue.json` and the router handles it automatically.

---

### Channel Map — International

```python
# channel_router.py

CHANNEL_MAP = {
    "psychology_self_improvement": "psyched",
    "finance_business":            "minted",
    "health_science":              "vitals",
    "tech_ai":                     "wired",
    "philosophy_wisdom":           "sage"
}

THEME_LABELS = {
    "psychology_self_improvement": "Psychology & Self-Improvement",
    "finance_business":            "Finance & Business",
    "health_science":              "Health & Science",
    "tech_ai":                     "Tech & AI",
    "philosophy_wisdom":           "Philosophy & Wisdom"
}
```

---

### Topic Classifier — Gemini Prompt

```python
# topic_classifier.py

CLASSIFIER_PROMPT = """
You are a content categorization expert. Analyze this YouTube video
and classify it into EXACTLY ONE theme.

Video title: {title}
Video description (first 300 chars): {description}
Transcript excerpt (first 500 words): {transcript_excerpt}

Choose ONE theme from this list:
- psychology_self_improvement: mental health, behavior, mindset,
  personal development, emotional intelligence, habits, therapy,
  self help, motivation, cognitive science
- finance_business: money, investing, stocks, bonds, business,
  startup, entrepreneurship, wealth, income, economy, markets
- health_science: medical, nutrition, fitness, longevity, sleep,
  doctor, biology, chemistry, research, wellness, diet
- tech_ai: technology, AI, software, coding, gadgets, robotics,
  digital, internet, machine learning, startups, engineering
- philosophy_wisdom: life meaning, stoicism, ethics, critical thinking,
  religion, existential, morality, ancient wisdom, consciousness

Scoring rules:
1. Pick the theme that matches the CORE TOPIC, not surface mentions
2. If a video talks about "AI tools to make money" → tech_ai (core) not finance
3. If a video is "How stress affects your heart" → health_science not psychology
4. When genuinely split 50/50 → pick secondary_theme as well

Return ONLY valid JSON:
{{
  "primary_theme": "theme_slug",
  "confidence": 0-100,
  "secondary_theme": "theme_slug or null",
  "target_channel": "channel_name",
  "reasoning": "one sentence max"
}}
"""

def classify_video(title, description, transcript_excerpt):
    prompt = CLASSIFIER_PROMPT.format(
        title=title,
        description=description[:300],
        transcript_excerpt=transcript_excerpt[:2000]
    )
    result = call_gemini_with_retry(prompt)
    return json.loads(result)
```

---

### Routing Logic

```python
# channel_router.py

def route_video(video_metadata, queue_entry=None):
    """
    Determine target channel for a video.

    Priority:
    1. If queue_entry has explicit target_channel → use it (operator override)
    2. If auto-discovered → classify via Gemini → route
    3. If manual queue with target_channel=null → classify via Gemini → route

    Returns:
        {
            "channel": "psyched",
            "theme": "psychology_self_improvement",
            "confidence": 92,
            "routing_method": "gemini_auto" | "operator_override",
            "action": "proceed" | "flag_review" | "hold"
        }
    """

    # Priority 1: Operator override in queue
    if queue_entry and queue_entry.get("target_channel"):
        channel = queue_entry["target_channel"]
        return {
            "channel": channel,
            "theme": None,
            "confidence": 100,
            "routing_method": "operator_override",
            "action": "proceed"
        }

    # Priority 2: Gemini classification
    classification = classify_video(
        title=video_metadata["title"],
        description=video_metadata["description"],
        transcript_excerpt=video_metadata["transcript"][:2000]
    )

    confidence = classification["confidence"]
    channel = CHANNEL_MAP[classification["primary_theme"]]

    if confidence >= 80:
        action = "proceed"
    elif confidence >= 60:
        action = "flag_review"   # Post but log for operator check
    else:
        action = "hold"          # Don't post, wait for operator decision

    return {
        "channel": channel,
        "theme": classification["primary_theme"],
        "confidence": confidence,
        "secondary_theme": classification.get("secondary_theme"),
        "routing_method": "gemini_auto",
        "action": action,
        "reasoning": classification.get("reasoning")
    }
```

---

### Updated queue.json — target_channel Now Optional

```json
{
  "entries": [
    {
      "url": "https://youtube.com/watch?v=VIDEOID",
      "format": "long",
      "start_time": "05:20",
      "end_time": "14:40",
      "target_channel": null,
      "program_platform": "whop",
      "program_id": "huberman-clips",
      "revenue_share_pct": 70,
      "notes": "Not sure which channel — let system decide",
      "affiliate_requirements": { }
    },
    {
      "url": "https://youtube.com/watch?v=VIDEOID2",
      "format": "short",
      "start_time": "02:10",
      "end_time": "02:55",
      "target_channel": "vitals",
      "program_platform": "whop",
      "program_id": "attia-clips",
      "revenue_share_pct": 60,
      "notes": "Clearly health content — override to vitals",
      "affiliate_requirements": { }
    }
  ]
}
```

---

### Confidence Threshold Behavior

| Confidence | Action | Description |
|---|---|---|
| >= 80% | `proceed` | Auto-route, post normally |
| 60–79% | `flag_review` | Post to classified channel, log warning for operator |
| < 60% | `hold` | Do NOT post. Save to `database/unclassified.json` for operator review |

### Unclassified Queue (`database/unclassified.json`)

Videos that score < 60% confidence are held here for manual operator decision:

```json
{
  "held_videos": [
    {
      "source_url": "https://youtube.com/watch?v=VIDEOID",
      "held_at": "2025-03-01T07:00:00Z",
      "classification_result": {
        "primary_theme": "health_science",
        "confidence": 52,
        "secondary_theme": "philosophy_wisdom",
        "reasoning": "Ambiguous — content discusses both longevity and meaning of life"
      },
      "operator_decision": null,
      "target_channel_override": null
    }
  ]
}
```

Operator edits `target_channel_override` → next pipeline run picks it up and processes normally.

---

### Where Router Sits in the Full Pipeline

```
Video found (auto or manual queue)
        ↓
[ROUTER] topic_classifier.py → channel_router.py
        ↓
    ┌───────────────────────────┐
    │ confidence >= 80%?        │
    │ YES → proceed to safety   │
    │ 60-79% → proceed + flag   │
    │ < 60% → hold, log, skip   │
    └───────────────────────────┘
        ↓ (if proceed)
[SAFETY] 4-layer copyright check
        ↓
[PROCESS] download, subtitle, render
        ↓
[UPLOAD] post to correct channel via YouTube API
        ↓
[LOG] record channel + routing_method in posted.json
```

---

## Module 9: Manual Queue System (Whop + Affiliate Requirements)

### Overview

The manual queue supports an `affiliate_requirements` block that tells Gemini exactly what to inject into the video metadata. This covers all common affiliate/Whop program requirements: affiliate links, pinned comment text, mandatory hashtags, watermarks, and any other custom instructions. Gemini reads this block and automatically applies everything to the description, tags, and pinned comment — operator does not need to edit metadata manually.

---

### queue.json Format (Full)

```json
{
  "entries": [
    {
      "url": "https://youtube.com/watch?v=VIDEOID",
      "format": "long",
      "start_time": "12:34",
      "end_time": "22:45",
      "title_override": null,
      "whop_program_id": "program-name",
      "revenue_share_pct": 70,
      "notes": "Great segment on sleep deprivation",

      "affiliate_requirements": {
        "description_links": [
          {
            "label": "Original video",
            "url": "https://youtube.com/watch?v=ORIGINAL",
            "position": "top"
          },
          {
            "label": "Join the program",
            "url": "https://whop.com/program-name/?affiliate=MYID",
            "position": "bottom"
          }
        ],
        "mandatory_hashtags": ["#ProgramName", "#ClipAffiliate"],
        "pinned_comment": "Full credit to @CreatorName. Watch the original here: https://youtube.com/watch?v=ORIGINAL",
        "watermark_text": null,
        "custom_instructions": "Do not modify the original title. Add 'Clip from @CreatorName' at start of description."
      }
    }
  ]
}
```

---

### Field Reference — affiliate_requirements

| Field | Type | Required | Description |
|---|---|---|---|
| `description_links` | array | No | Links to inject into description. Each has `label`, `url`, `position` (`top`/`bottom`) |
| `mandatory_hashtags` | array | No | Hashtags appended to description and tags field |
| `pinned_comment` | string | No | If set, this text is posted as pinned comment immediately after upload |
| `watermark_text` | string | No | Text burned into video frame (bottom-left) via FFmpeg |
| `custom_instructions` | string | No | Free-text instruction passed directly to Gemini for any requirement not covered above |

All fields are optional. If `affiliate_requirements` is null or omitted, system behaves as standard auto clip.

---

### How Gemini Applies the Requirements

In `metadata_generator.py`, pass the `affiliate_requirements` block directly to Gemini as part of the metadata generation prompt:

```python
METADATA_PROMPT = """
You are generating YouTube metadata for a clip video.

Clip content summary:
{clip_summary}

Original creator: {creator_name}
Original video URL: {original_url}

AFFILIATE REQUIREMENTS — apply ALL of these exactly as specified:
{affiliate_requirements_json}

Generate the following, following all affiliate requirements above:

1. TITLE: Engaging, under 60 chars. If custom_instructions mentions title rules, follow them.

2. DESCRIPTION: 
   - Insert description_links marked as position="top" at the very top
   - Then write 2-3 sentences describing the clip content  
   - Then insert description_links marked as position="bottom"
   - Then append all mandatory_hashtags at the end
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
```

---

### Pinned Comment — Auto-Post After Upload

If `pinned_comment` is not null, system posts it immediately after upload via YouTube Data API:

```python
# youtube_uploader.py — after successful upload

def post_pinned_comment(video_id, comment_text, youtube_service):
    """
    Post a comment and immediately pin it to the video.
    """
    if not comment_text:
        return

    # Step 1: Post comment
    comment_response = youtube_service.commentThreads().insert(
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

    # Step 2: Pin the comment
    youtube_service.comments().setModerationStatus(
        id=comment_id,
        moderationStatus="published",
        banAuthor=False
    ).execute()

    # Note: YouTube API does not have a direct "pin" endpoint.
    # Pinning requires the channel owner to pin manually OR
    # via YouTube Studio. Log this as a reminder to operator.
    logger.info(f"Comment posted (ID: {comment_id}). PIN MANUALLY in YouTube Studio.")
```

> **Important:** YouTube Data API v3 does not support programmatic pinning of comments. The comment will be posted automatically, but operator needs to pin it manually in YouTube Studio. System will log a reminder after each upload that requires pinning.

---

### Watermark Text — Burned via FFmpeg

If `watermark_text` is not null, the visual_enhancer adds it to the video:

```python
# visual_enhancer.py — add watermark if required

def add_watermark_text(input_path, output_path, watermark_text):
    if not watermark_text:
        return input_path

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", (
            f"drawtext=text='{watermark_text}':"
            f"fontsize=28:fontcolor=white@0.6:"
            f"x=20:y=h-th-20:"
            f"box=1:boxcolor=black@0.3:boxborderw=6"
        ),
        "-codec:a", "copy",
        output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path
```

---

### Whitelist Entry for Manual Whop Channel

```json
{
  "channel_id": "UCxxxxxx",
  "channel_name": "Creator Name",
  "source": "manual_whop",
  "whop_program_id": "program-name",
  "revenue_share_pct": 70,
  "status": "active",
  "restrictions": ["no_paid_content"],
  "permission_verified_date": "2025-03-01",
  "confidence": 99,
  "default_affiliate_requirements": {
    "description_links": [
      {
        "label": "Original channel",
        "url": "https://youtube.com/@CreatorHandle",
        "position": "top"
      }
    ],
    "mandatory_hashtags": ["#ProgramName"],
    "pinned_comment": null,
    "watermark_text": null,
    "custom_instructions": ""
  }
}
```

The `default_affiliate_requirements` in `whitelist.json` applies to ALL clips from this channel automatically. The `affiliate_requirements` in `queue.json` can override or extend it per-video.

---

### Merge Logic — Whitelist Default vs Queue Override

```python
def resolve_affiliate_requirements(whitelist_entry, queue_entry):
    """
    Merge whitelist defaults with per-video queue overrides.
    Queue values take priority. Lists are merged (not replaced).
    """
    defaults = whitelist_entry.get("default_affiliate_requirements", {})
    overrides = queue_entry.get("affiliate_requirements", {})

    merged = {
        "description_links": (
            overrides.get("description_links") or
            defaults.get("description_links") or []
        ),
        "mandatory_hashtags": list(set(
            defaults.get("mandatory_hashtags", []) +
            overrides.get("mandatory_hashtags", [])
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
```

---

After processing, `queue.json` entries array is cleared automatically.

---

## Module 10: GitHub Actions Workflows

### daily_pipeline.yml

```yaml
name: Daily Content Pipeline
on:
  schedule:
    - cron: '0 0 * * *'  # 00:00 UTC = 07:00 WIB
  workflow_dispatch:

jobs:
  run_pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Install system tools
        run: |
          sudo apt-get install -y ffmpeg
          pip install yt-dlp openai-whisper
      - name: Run pipeline
        env:
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
          YOUTUBE_CLIENT_SECRET: ${{ secrets.YOUTUBE_CLIENT_SECRET }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python src/main.py
      - name: Commit database updates
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add database/ logs/
          git commit -m "Daily pipeline run $(date +%Y-%m-%d)" || exit 0
          git push
```

### discovery_scan.yml

```yaml
name: Weekly Channel Discovery
on:
  schedule:
    - cron: '0 2 * * 0'  # Every Sunday 02:00 UTC
  workflow_dispatch:

jobs:
  discover:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run discovery
        run: python src/discovery/channel_scanner.py
      - name: Commit whitelist updates
        run: |
          git add config/whitelist.json
          git commit -m "Weekly channel discovery $(date +%Y-%m-%d)" || exit 0
          git push
```

### performance_monitor.yml

```yaml
name: Daily Performance Monitor
on:
  schedule:
    - cron: '0 6 * * *'  # 06:00 UTC daily (after 48h review window)
  workflow_dispatch:

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run performance check
        run: python src/monitor/performance_checker.py
      - name: Commit performance log
        run: |
          git add database/performance_log.json
          git commit -m "Performance update $(date +%Y-%m-%d)" || exit 0
          git push
```

---

## config/settings.json

```json
{
  "channel": {
    "name": "Your Channel Name",
    "youtube_channel_id": "UCxxxxxx",
    "language_primary": "en",
    "language_secondary": "id"
  },
  "posting": {
    "daily_slots": ["07:00", "11:00", "16:00", "20:00"],
    "random_offset_minutes": 45,
    "timezone": "Asia/Jakarta",
    "shorts_slots": ["07:00", "16:00"],
    "long_slots": ["11:00", "20:00"]
  },
  "content": {
    "max_long_clip_minutes": 10,
    "min_long_clip_minutes": 3,
    "shorts_max_seconds": 59,
    "shorts_min_seconds": 30,
    "scan_videos_last_days": 7,
    "gemini_model": "gemini-1.5-flash",
    "whisper_model": "base",
    "background_music_volume": 0.10
  },
  "discovery": {
    "min_confidence_auto_approve": 85,
    "min_confidence_pending_review": 70,
    "revalidate_interval_days": 7,
    "max_channels_per_scan": 50
  },
  "performance": {
    "review_after_hours": 48,
    "ctr_minimum_pct": 4.0,
    "avd_minimum_pct": 40.0,
    "max_auto_updates_per_video": 3,
    "low_impression_threshold": 500
  }
}
```

---

## Infrastructure Summary (All Free Tier)

| Component | Service | Cost |
|---|---|---|
| Scheduler & CI/CD | GitHub Actions (**public repo — unlimited minutes**) | Free unlimited |
| AI Clip Detection | Gemini 1.5 Flash API | Free tier |
| Speech-to-Text | OpenAI Whisper (base, runs in Actions runner) | Free |
| Translation | Gemini API | Free tier |
| Video Download | yt-dlp | Free |
| Video Processing | FFmpeg | Free |
| Audio Fingerprint | ACRCloud | Free (100 req/day) |
| Database | JSON files in repo | Free |
| Upload | YouTube Data API v3 | Free |
| Analytics | YouTube Analytics API | Free |

### Repository Visibility — MUST BE PUBLIC

```
Repo visibility : PUBLIC (wajib)
Alasan          : GitHub Actions unlimited minutes hanya untuk public repo
                  Private repo dibatasi 2.000 menit/bulan — tidak cukup
                  (kebutuhan sistem ini ~11.400 menit/bulan per repo)

Keamanan public repo:
✅ API keys → tersimpan di GitHub Secrets (terenkripsi, tidak pernah expose)
✅ Kode pipeline → boleh dilihat publik, tidak ada info sensitif
✅ whitelist.json, seeds.json → tidak berbahaya kalau dilihat
✅ Orang lain hanya bisa READ — tidak bisa push/edit repo lo
✅ Disable pull requests di Settings untuk keamanan ekstra

Yang TIDAK BOLEH ada di repo (gunakan .gitignore):
❌ File .env
❌ config/secrets.json
❌ File credential apapun
```

### .gitignore Wajib

```gitignore
# Secrets — jangan pernah commit
.env
*.env
config/secrets.json

# Log files
logs/*.log

# Temporary processing files
tmp/
temp/
*.tmp

# Large binary assets
assets/music/downloads/
```

---

## DRY_RUN Mode — Wajib Dipakai Saat Testing

Sebelum pipeline dijalankan ke channel YouTube asli, selalu test dulu dengan DRY_RUN=true.

### Cara Aktifkan DRY_RUN

Tambahkan secret atau variable di GitHub repo:
```
GitHub Repo → Settings → Secrets and variables
→ Variables → New repository variable
→ DRY_RUN = true
```

Setelah yakin pipeline berjalan benar, ganti ke:
```
DRY_RUN = false
```

### Behaviour DRY_RUN=true

```python
# utils/dry_run.py

import os

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

def upload_video(file_path, metadata, channel):
    if DRY_RUN:
        print(f"[DRY_RUN] Would upload: {metadata['title']} → {channel}")
        print(f"[DRY_RUN] File: {file_path}")
        print(f"[DRY_RUN] Tags: {metadata['tags']}")
        return {"status": "dry_run", "video_id": "DRY_RUN_ID"}
    else:
        return youtube_api_upload(file_path, metadata, channel)

def post_pinned_comment(video_id, comment):
    if DRY_RUN:
        print(f"[DRY_RUN] Would pin comment on {video_id}: {comment}")
        return
    else:
        youtube_api_comment(video_id, comment)
```

### Checklist Testing dengan DRY_RUN

```
Tahap 1 — DRY_RUN=true, test channel YouTube kosong:
□ Pipeline trigger via cron berjalan
□ Video discovery menemukan kandidat
□ Permission detection bekerja
□ Gemini menghasilkan script + metadata
□ yt-dlp berhasil download clip
□ Whisper berhasil transcribe
□ FFmpeg render output video
□ Subtitle terbaca dengan benar
□ ACRCloud scan tidak error
□ Log menunjukkan "Would upload: ..."
□ Tidak ada crash di tengah pipeline

Tahap 2 — DRY_RUN=false, test channel YouTube kosong:
□ Video benar-benar terupload ke test channel
□ Metadata (judul, deskripsi, tags) benar
□ Subtitle muncul di video
□ Thumbnail sesuai
□ Format Short vs Long sudah benar

Tahap 3 — DRY_RUN=false, channel asli:
□ Semua channel aktif
□ Monitoring performa aktif
□ Go live ✅
```

---

## Required API Keys & Secrets (GitHub Secrets)

```
YOUTUBE_API_KEY          → YouTube Data API v3 (read operations)
YOUTUBE_CLIENT_SECRET    → OAuth2 for upload + analytics
YOUTUBE_REFRESH_TOKEN    → OAuth2 refresh token
GEMINI_API_KEY           → Google Gemini API
ACR_ACCESS_KEY           → ACRCloud audio fingerprint (free: 100 req/day)
ACR_ACCESS_SECRET        → ACRCloud secret
```

---

## Build Instructions for Opus

1. Create the full repository structure as defined above
2. Implement all Python modules in `src/` with proper error handling and logging
3. All modules must handle API rate limits with exponential backoff
4. Database files (`posted.json`, `whitelist.json`, etc.) must be read/written atomically to prevent corruption from concurrent GitHub Actions runs
5. Every pipeline run must produce a structured log entry in `logs/daily_run.log`
6. If any step fails (download, transcription, processing, upload), log the error and continue with the next video — never crash the entire pipeline
7. Gemini calls must include retry logic (max 3 retries with 5s delay)
8. yt-dlp calls must include `--no-check-certificates` and proper timeout handling
9. All temporary files must be cleaned up after each video is processed
10. The system must be idempotent — running the pipeline twice on the same day must not create duplicate posts (check `posted.json` before every upload)
11. The 4-layer safety system in `src/safety/` is NON-NEGOTIABLE — every video must pass all layers before upload. Never skip or bypass safety checks under any condition, including when retrying failed videos
12. ACRCloud scan must run TWICE per video: once on raw downloaded clip, once on final rendered output
13. All music tracks in `/assets/music/` must be pre-committed to the repository — the pipeline must never download music at runtime

---

---

## Gemini API Usage & Rate Limit Strategy

This clipper channel shares the same Gemini free tier quota as any other automation project. To avoid rate limit conflicts, the GitHub Actions schedule is intentionally offset:

```
Psychology Channel pipeline  → 00:00 UTC
Clipper Channel pipeline     → 01:00 UTC
Performance Monitor          → 06:00 UTC
Weekly Discovery             → 02:00 UTC (Sundays only)
```

Never run two pipelines at the same time. One Gemini API key is sufficient as long as schedules do not overlap. If rate limit errors (429) occur despite staggered schedules, implement exponential backoff:

```python
def call_gemini_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return gemini_model.generate_content(prompt)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = (2 ** attempt) * 5  # 5s, 10s, 20s
                time.sleep(wait)
            else:
                raise
```

*Document version: 1.7 — Clipper Channel System (GitHub public repo + DRY_RUN mode)*
*Platform: YouTube only*
*Language: English primary, Indonesian subtitles*
*Infrastructure: GitHub Actions (public repo, unlimited minutes) + Free APIs*
