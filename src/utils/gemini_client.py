# src/utils/gemini_client.py
# Gemini API wrapper using NEW google-genai SDK
# Per-channel API keys with retry logic and rate limit handling

import os
import json
import time
import logging
import re

from google import genai

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.0-flash"

# Cache client instances per channel (each has its own API key)
_client_cache = {}

# Track which channel is currently active (for modules that don't pass channel_name)
_active_channel = "psyched"


def set_active_channel(channel_name):
    """Set the currently active channel for Gemini calls that don't specify one."""
    global _active_channel
    _active_channel = channel_name


def get_client(channel_name=None):
    """Get or create Gemini client for a specific channel's API key.
    STRICT isolation: each channel uses ONLY GEMINI_API_KEY_{idx}.
    """
    global _client_cache

    ch = channel_name or _active_channel

    if ch in _client_cache:
        return _client_cache[ch]

    # Get per-channel Gemini key — NO fallback to generic key
    from .channel_credentials import get_gemini_api_key
    api_key = get_gemini_api_key(ch)

    if not api_key:
        raise ValueError(
            f"GEMINI_API_KEY not set for channel {ch}. "
            f"Set GEMINI_API_KEY_{{idx}} in GitHub Secrets."
        )

    client = genai.Client(api_key=api_key)
    _client_cache[ch] = client
    logger.info(f"Gemini client initialized for channel: {ch}")
    return client


def call_gemini_with_retry(prompt, max_retries=3, parse_json=True, channel_name=None):
    """
    Call Gemini API with exponential backoff retry logic.

    Args:
        prompt: The text prompt to send to Gemini.
        max_retries: Maximum number of retries (default 3).
        parse_json: If True, attempt to parse response as JSON.
        channel_name: Optional channel name to use specific API key.

    Returns:
        Parsed JSON dict if parse_json=True, else raw text string.

    Raises:
        Exception if all retries fail.
    """
    client = get_client(channel_name)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            text = response.text.strip()

            if parse_json:
                return extract_json(text)
            return text

        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries - 1:
                wait = (2 ** attempt) * 5  # 5s, 10s, 20s
                logger.warning(
                    f"Gemini rate limit hit (attempt {attempt + 1}/{max_retries}). "
                    f"Waiting {wait}s..."
                )
                time.sleep(wait)
            elif attempt < max_retries - 1:
                wait = (2 ** attempt) * 2  # 2s, 4s for other errors
                logger.warning(
                    f"Gemini error (attempt {attempt + 1}/{max_retries}): {error_str}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                logger.error(f"Gemini failed after {max_retries} attempts: {error_str}")
                raise


def extract_json(text):
    """
    Extract JSON from Gemini response text.
    Handles cases where JSON is wrapped in markdown code blocks.
    """
    # Try direct JSON parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` blocks
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON object pattern { ... }
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from Gemini response:\n{text[:500]}")


def call_gemini_text(prompt, max_retries=3, channel_name=None):
    """Convenience wrapper that returns raw text (no JSON parsing)."""
    return call_gemini_with_retry(prompt, max_retries=max_retries, parse_json=False, channel_name=channel_name)
