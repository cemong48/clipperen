# src/processing/subtitle_generator.py
# Whisper → bilingual subtitles (English + Indonesian)

import os
import logging

from ..utils.gemini_client import call_gemini_text

logger = logging.getLogger("clipper.processing.subtitle_generator")

TEMP_DIR = "temp"


def generate_whisper_subtitles(audio_path):
    """
    Run Whisper (base model) on audio to get word-level timestamps.
    Returns list of segments with timestamps.
    """
    try:
        import whisper
        
        logger.info(f"Running Whisper on: {audio_path}")
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, word_timestamps=True, language="en")
        
        return result.get("segments", [])
    except ImportError:
        logger.error("Whisper not installed.")
        return []
    except Exception as e:
        logger.error(f"Whisper failed: {e}")
        return []


def segments_to_srt(segments, output_path):
    """
    Convert Whisper segments to SRT subtitle format.
    Word-by-word highlighting style.
    """
    os.makedirs(os.path.dirname(output_path) or TEMP_DIR, exist_ok=True)
    
    srt_entries = []
    idx = 1
    
    for segment in segments:
        start = format_timestamp_srt(segment.get("start", 0))
        end = format_timestamp_srt(segment.get("end", 0))
        text = segment.get("text", "").strip()
        
        if text:
            srt_entries.append(f"{idx}\n{start} --> {end}\n{text}\n")
            idx += 1
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))
    
    logger.info(f"English SRT generated: {output_path} ({len(srt_entries)} entries)")
    return output_path


def format_timestamp_srt(seconds):
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def translate_to_indonesian(english_text):
    """
    Translate English text to Indonesian using Gemini API.
    """
    prompt = f"""
Translate the following English text to Indonesian (Bahasa Indonesia).
Keep it natural and conversational. Do NOT add any explanation.
Return ONLY the translated text.

English:
{english_text}

Indonesian:
"""
    try:
        return call_gemini_text(prompt).strip()
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return english_text  # Fallback to English


def generate_indonesian_srt(english_srt_path, output_path):
    """
    Generate Indonesian subtitle file by translating English SRT.
    Translates segment by segment to maintain timing.
    """
    with open(english_srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Parse SRT entries
    entries = content.strip().split("\n\n")
    translated_entries = []
    
    for entry in entries:
        lines = entry.strip().split("\n")
        if len(lines) >= 3:
            idx = lines[0]
            timestamp = lines[1]
            text = " ".join(lines[2:])
            
            # Translate text
            translated = translate_to_indonesian(text)
            translated_entries.append(f"{idx}\n{timestamp}\n{translated}")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(translated_entries))
    
    logger.info(f"Indonesian SRT generated: {output_path}")
    return output_path


def generate_bilingual_subtitles(audio_path, output_dir=None):
    """
    Main entry point: generate both English and Indonesian SRT files.
    
    Returns:
        dict with 'english_srt' and 'indonesian_srt' paths
    """
    if output_dir is None:
        output_dir = TEMP_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    # Step 1: Whisper transcription
    segments = generate_whisper_subtitles(audio_path)
    
    if not segments:
        logger.warning("No segments from Whisper. Subtitle generation skipped.")
        return {"english_srt": None, "indonesian_srt": None}
    
    # Step 2: English SRT
    en_path = os.path.join(output_dir, "subtitles_en.srt")
    segments_to_srt(segments, en_path)
    
    # Step 3: Indonesian SRT
    id_path = os.path.join(output_dir, "subtitles_id.srt")
    generate_indonesian_srt(en_path, id_path)
    
    return {
        "english_srt": en_path,
        "indonesian_srt": id_path,
        "segments": segments
    }
