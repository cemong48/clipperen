"""
Diagnostic: test each CF Worker to check if it's deployed, reachable, and working.
Also verify cookies can be loaded and forwarded.
Run from LOCAL machine where env vars are NOT set — reads URLs from DEPLOY.md.
"""
import requests
import os
import json
from http.cookiejar import MozillaCookieJar

# Read from GitHub Secrets file or manual input
# The user should paste their actual CF Worker URLs here
CF_WORKERS = {
    1: {"name": "psyched", "url": "", "auth": ""},
    2: {"name": "minted",  "url": "", "auth": ""},
    3: {"name": "vitals",  "url": "", "auth": ""},
    4: {"name": "wired",   "url": "", "auth": ""},
    5: {"name": "sage",    "url": "", "auth": ""},
}

# Known auth keys from DEPLOY.md
AUTH_KEYS = {
    1: "cpk_Xt9mQ4vL7nRjW2bFhKs8dYpA3",
    2: "cpk_Bw6rH1eZcN5gTyUx0jMfKq4P9",
    3: "cpk_Jn3sV8dLkR7wYm2XpF6hCt0G5",
    4: "cpk_Dz5fA9qWu1xNb4vKy7JmEh3S8",
    5: "cpk_Mg2tL0pHr6cXw9kBn4YfQj8V1",
}

# Try to get URLs from env vars (like GitHub Actions does)
for idx in range(1, 6):
    url = os.environ.get(f"CF_WORKER_URL_{idx}", "")
    auth = os.environ.get(f"CF_WORKER_AUTH_KEY_{idx}", "")
    if url:
        CF_WORKERS[idx]["url"] = url
    if auth:
        CF_WORKERS[idx]["auth"] = auth
    # Fall back to DEPLOY.md auth keys
    if not CF_WORKERS[idx]["auth"]:
        CF_WORKERS[idx]["auth"] = AUTH_KEYS.get(idx, "")

print("=" * 60)
print("CF WORKER DIAGNOSTIC TEST")
print("=" * 60)

# Step 1: Check if URLs are configured
print("\n--- Step 1: URL Configuration ---")
has_urls = False
for idx, cfg in CF_WORKERS.items():
    if cfg["url"]:
        has_urls = True
        print(f"  #{idx} {cfg['name']}: {cfg['url'][:50]}...")
    else:
        print(f"  #{idx} {cfg['name']}: NOT CONFIGURED")

if not has_urls:
    print("\nNo CF Worker URLs found in environment variables.")
    print("Please enter your CF Worker URLs to test:")
    for idx in range(1, 6):
        url = input(f"  CF_WORKER_URL_{idx} (or empty to skip): ").strip()
        if url:
            CF_WORKERS[idx]["url"] = url
            has_urls = True

if not has_urls:
    print("\nNo URLs to test. Exiting.")
    exit(1)

# Step 2: Test each worker reachability
print("\n--- Step 2: Reachability Test ---")
for idx, cfg in CF_WORKERS.items():
    if not cfg["url"]:
        print(f"  #{idx} {cfg['name']}: SKIPPED (no URL)")
        continue
    
    try:
        # Test with wrong auth to see if worker is alive
        resp = requests.post(
            cfg["url"],
            json={"action": "transcript", "video_id": "test"},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"  #{idx} {cfg['name']}: HTTP {resp.status_code} — {'ALIVE' if resp.status_code in [401, 200, 404, 400] else 'UNKNOWN'}")
        
        # Test with correct auth
        resp2 = requests.post(
            cfg["url"],
            json={"action": "transcript", "video_id": "test"},
            headers={
                "Content-Type": "application/json",
                "X-Auth-Key": cfg["auth"]
            },
            timeout=10
        )
        print(f"       with auth: HTTP {resp2.status_code}")
        try:
            data = resp2.json()
            print(f"       response: {json.dumps(data)[:150]}")
        except:
            print(f"       body: {resp2.text[:150]}")
            
    except requests.exceptions.ConnectionError:
        print(f"  #{idx} {cfg['name']}: CONNECTION FAILED — worker not deployed or URL wrong")
    except requests.exceptions.Timeout:
        print(f"  #{idx} {cfg['name']}: TIMEOUT")
    except Exception as e:
        print(f"  #{idx} {cfg['name']}: ERROR — {e}")

# Step 3: Test actual transcript extraction (with a real video ID)
print("\n--- Step 3: Transcript Test (rfscVS0vtbw) ---")
test_vid = "rfscVS0vtbw"

for idx, cfg in CF_WORKERS.items():
    if not cfg["url"]:
        continue
    
    # Load cookies if available
    cookie_str = ""
    cookie_path = f"temp/cookies_{idx}.txt"
    if os.path.exists(cookie_path):
        try:
            jar = MozillaCookieJar(cookie_path)
            jar.load(ignore_discard=True, ignore_expires=True)
            cookie_str = "; ".join([f"{c.name}={c.value}" for c in jar])
            print(f"  #{idx}: loaded {len(list(jar))} cookies from {cookie_path}")
        except Exception as e:
            print(f"  #{idx}: could not load cookies: {e}")
    
    try:
        resp = requests.post(
            cfg["url"],
            json={
                "action": "transcript",
                "video_id": test_vid,
                "cookies": cookie_str
            },
            headers={
                "Content-Type": "application/json",
                "X-Auth-Key": cfg["auth"]
            },
            timeout=30
        )
        print(f"  #{idx} {cfg['name']}: HTTP {resp.status_code}")
        try:
            data = resp.json()
            if data.get("success"):
                print(f"       SUCCESS: {data.get('chars', '?')} chars via {data.get('source', '?')}")
                preview = data.get("text", "")[:80]
                print(f"       Preview: {preview}")
            else:
                errors = data.get("errors", [])
                for e in errors:
                    print(f"       Error: {e}")
        except:
            print(f"       Body: {resp.text[:200]}")
    except Exception as e:
        print(f"  #{idx} {cfg['name']}: {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
