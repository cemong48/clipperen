# src/router/topic_classifier.py
# Gemini classifies video into 1 of 5 themes

import json
import logging

from ..utils.gemini_client import call_gemini_with_retry

logger = logging.getLogger("clipper.router.classifier")

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

# Channel name mapping
CHANNEL_MAP = {
    "psychology_self_improvement": "psyched",
    "finance_business": "minted",
    "health_science": "vitals",
    "tech_ai": "wired",
    "philosophy_wisdom": "sage"
}


def classify_video(title, description, transcript_excerpt):
    """
    Classify a video into one of 5 themes using Gemini.
    
    Args:
        title: Video title
        description: Video description (will be truncated to 300 chars)
        transcript_excerpt: Transcript text (will be truncated to 2000 chars)
    
    Returns:
        dict with primary_theme, confidence, secondary_theme, target_channel, reasoning
    """
    prompt = CLASSIFIER_PROMPT.format(
        title=title,
        description=description[:300],
        transcript_excerpt=transcript_excerpt[:2000]
    )
    
    try:
        result = call_gemini_with_retry(prompt, parse_json=True)
        
        # Ensure target_channel is set correctly
        primary = result.get("primary_theme", "")
        if primary in CHANNEL_MAP:
            result["target_channel"] = CHANNEL_MAP[primary]
        else:
            logger.warning(f"Unknown theme: {primary}, defaulting to 'sage'")
            result["target_channel"] = "sage"
        
        logger.info(
            f"Classified '{title[:50]}' → {result['target_channel']} "
            f"(confidence: {result.get('confidence', 0)}%)"
        )
        return result
        
    except Exception as e:
        logger.error(f"Classification failed for '{title}': {e}")
        return {
            "primary_theme": "philosophy_wisdom",
            "confidence": 0,
            "secondary_theme": None,
            "target_channel": "sage",
            "reasoning": f"Classification failed: {e}"
        }
