#!/usr/bin/env python3
"""
Convert cookies from JSON format (browser extension export) to Netscape format (yt-dlp compatible).
Handles both JSON array format and already-Netscape format gracefully.
"""

import json
import sys
import os


def json_to_netscape(json_content):
    """Convert JSON cookies array to Netscape cookies.txt format."""
    try:
        cookies = json.loads(json_content)
    except json.JSONDecodeError:
        return None  # Not JSON, might already be Netscape
    
    if not isinstance(cookies, list):
        return None
    
    lines = ["# Netscape HTTP Cookie File", "# Converted from JSON format", ""]
    
    for cookie in cookies:
        # Handle different JSON cookie formats from various browser extensions
        domain = cookie.get("domain", cookie.get("Domain", ""))
        name = cookie.get("name", cookie.get("Name", ""))
        value = cookie.get("value", cookie.get("Value", ""))
        path = cookie.get("path", cookie.get("Path", "/"))
        
        # Expiration
        expiry = cookie.get("expirationDate", cookie.get("expiry", 
                 cookie.get("Expires", cookie.get("expires", 0))))
        try:
            expiry = int(float(expiry))
        except (ValueError, TypeError):
            expiry = 0
        
        # Secure flag
        secure = cookie.get("secure", cookie.get("Secure", False))
        secure_str = "TRUE" if secure else "FALSE"
        
        # HttpOnly (domain flag in Netscape format)
        # If domain starts with '.', it's accessible to subdomains
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        
        if domain and name:
            line = f"{domain}\t{include_subdomains}\t{path}\t{secure_str}\t{expiry}\t{name}\t{value}"
            lines.append(line)
    
    return "\n".join(lines) + "\n"


def is_netscape_format(content):
    """Check if content is already in Netscape format."""
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Netscape format has 7 tab-separated fields
        parts = line.split("\t")
        if len(parts) == 7:
            return True
        return False
    return False


def convert_file(input_path, output_path=None):
    """Convert a cookies file from JSON to Netscape format if needed."""
    if output_path is None:
        output_path = input_path
    
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    if not content:
        print(f"  EMPTY: {input_path}")
        return False
    
    # Check if already Netscape format
    if is_netscape_format(content):
        print(f"  OK (already Netscape): {input_path}")
        return True
    
    # Try to convert from JSON
    netscape = json_to_netscape(content)
    if netscape:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(netscape)
        cookie_count = netscape.count("\n") - 3  # minus header lines
        print(f"  CONVERTED: {input_path} ({cookie_count} cookies)")
        return True
    
    print(f"  ERROR: {input_path} — unknown format (not JSON, not Netscape)")
    return False


if __name__ == "__main__":
    # Convert all cookies files in temp/
    temp_dir = "temp"
    converted = 0
    
    for i in range(1, 6):
        path = os.path.join(temp_dir, f"cookies_{i}.txt")
        if os.path.exists(path):
            if convert_file(path):
                converted += 1
        else:
            print(f"  SKIP: cookies_{i}.txt not found")
    
    print(f"\nConverted {converted}/5 cookie files")
