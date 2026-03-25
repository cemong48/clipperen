#!/usr/bin/env python3
"""
One-time CF Worker deployer: updates all 5 Cloudflare Workers with new worker.js
using the Cloudflare API. Run this ONCE from your local machine.

Usage:
    python scripts/deploy_cf_workers.py

Requires Cloudflare API tokens. You'll be prompted to enter them.
"""

import requests
import sys
import os


def read_worker_js():
    """Read the worker.js file."""
    path = os.path.join(os.path.dirname(__file__), "..", "cloudflare", "worker.js")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def deploy_worker(account_id, worker_name, api_token, js_code):
    """Deploy worker.js to Cloudflare using the API."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{worker_name}"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/javascript",
    }
    
    resp = requests.put(url, headers=headers, data=js_code, timeout=30)
    
    if resp.status_code == 200:
        data = resp.json()
        if data.get("success"):
            return True, "Deployed successfully"
        else:
            errors = data.get("errors", [])
            return False, f"API error: {errors}"
    else:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


def main():
    print("=" * 60)
    print("Cloudflare Worker Deployer")
    print("=" * 60)
    print()
    
    js_code = read_worker_js()
    print(f"Loaded worker.js ({len(js_code)} bytes)")
    print()
    
    # Channel mapping
    channels = [
        {"idx": 1, "name": "psyched"},
        {"idx": 2, "name": "minted"},
        {"idx": 3, "name": "vitals"},
        {"idx": 4, "name": "wired"},
        {"idx": 5, "name": "sage"},
    ]
    
    print("For each channel, enter the Cloudflare Account ID, Worker name, and API Token.")
    print("You can find these in the Cloudflare Dashboard > Workers & Pages.")
    print("To get an API Token: My Profile > API Tokens > Create Token > Edit Workers")
    print()
    
    results = []
    
    for ch in channels:
        print(f"--- Channel #{ch['idx']}: {ch['name']} ---")
        
        account_id = input(f"  Cloudflare Account ID (or 'skip'): ").strip()
        if account_id.lower() == "skip":
            results.append((ch["name"], False, "Skipped"))
            print()
            continue
        
        worker_name = input(f"  Worker name (e.g. yt-transcript-proxy): ").strip()
        if not worker_name:
            worker_name = "yt-transcript-proxy"
        
        api_token = input(f"  API Token: ").strip()
        
        print(f"  Deploying to {worker_name}...")
        success, msg = deploy_worker(account_id, worker_name, api_token, js_code)
        
        if success:
            print(f"  ✅ {msg}")
        else:
            print(f"  ❌ {msg}")
        
        results.append((ch["name"], success, msg))
        print()
    
    print("=" * 60)
    print("RESULTS:")
    for name, success, msg in results:
        status = "✅" if success else "❌"
        print(f"  {status} {name}: {msg}")
    print("=" * 60)


if __name__ == "__main__":
    main()
