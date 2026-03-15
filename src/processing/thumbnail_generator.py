# src/processing/thumbnail_generator.py
# Face crop + title text via Pillow for YouTube thumbnails

import os
import subprocess
import logging

logger = logging.getLogger("clipper.processing.thumbnail")

TEMP_DIR = "temp"
THUMB_WIDTH = 1280
THUMB_HEIGHT = 720


def extract_candidate_frames(video_path, count=3):
    """
    Extract candidate frames from the video at evenly spaced intervals.
    Uses ffmpeg to extract frames.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    frames = []
    
    # Get video duration
    try:
        probe_cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
        duration = float(result.stdout.strip())
    except Exception:
        duration = 60  # fallback
    
    # Extract frames at evenly spaced points
    for i in range(count):
        time_pos = duration * (i + 1) / (count + 1)
        frame_path = os.path.join(TEMP_DIR, f"thumb_frame_{i}.jpg")
        
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(time_pos),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            frame_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if os.path.exists(frame_path):
            frames.append(frame_path)
    
    return frames


def detect_face_in_frame(frame_path):
    """
    Detect face in a frame using OpenCV.
    Returns face bounding box or None.
    """
    try:
        import cv2
        
        img = cv2.imread(frame_path)
        if img is None:
            return None
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Use OpenCV's built-in Haar cascade face detector
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        if len(faces) > 0:
            # Return the largest face
            largest = max(faces, key=lambda f: f[2] * f[3])
            return {
                "x": int(largest[0]),
                "y": int(largest[1]),
                "w": int(largest[2]),
                "h": int(largest[3]),
                "area": int(largest[2] * largest[3])
            }
    except ImportError:
        logger.warning("OpenCV not available for face detection.")
    except Exception as e:
        logger.error(f"Face detection error: {e}")
    
    return None


def generate_thumbnail(video_path, title_text, output_path=None):
    """
    Generate a YouTube thumbnail:
    1. Extract candidate frames (pick most expressive)
    2. Crop face to right half of 1280x720 canvas
    3. Render title text on left half
    4. Apply slight vignette
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        logger.error("Pillow not installed.")
        return None
    
    if output_path is None:
        output_path = os.path.join(TEMP_DIR, "thumbnail.jpg")
    os.makedirs(os.path.dirname(output_path) or TEMP_DIR, exist_ok=True)
    
    # Step 1: Extract frames
    frames = extract_candidate_frames(video_path, count=3)
    if not frames:
        logger.error("No frames extracted for thumbnail.")
        return None
    
    # Step 2: Find frame with largest face
    best_frame = frames[0]
    best_face = None
    best_area = 0
    
    for frame_path in frames:
        face = detect_face_in_frame(frame_path)
        if face and face["area"] > best_area:
            best_area = face["area"]
            best_face = face
            best_frame = frame_path
    
    # Step 3: Create thumbnail canvas
    canvas = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT), (20, 20, 30))
    draw = ImageDraw.Draw(canvas)
    
    # Load the best frame
    frame_img = Image.open(best_frame)
    
    if best_face:
        # Crop around face for right half
        cx = best_face["x"] + best_face["w"] // 2
        cy = best_face["y"] + best_face["h"] // 2
        crop_size = max(best_face["w"], best_face["h"]) * 2
        
        left = max(0, cx - crop_size // 2)
        top = max(0, cy - crop_size // 2)
        right = min(frame_img.width, left + crop_size)
        bottom = min(frame_img.height, top + crop_size)
        
        face_crop = frame_img.crop((left, top, right, bottom))
        face_crop = face_crop.resize((THUMB_WIDTH // 2, THUMB_HEIGHT))
        canvas.paste(face_crop, (THUMB_WIDTH // 2, 0))
    else:
        # No face — use center of frame for right half
        frame_resized = frame_img.resize((THUMB_WIDTH, THUMB_HEIGHT))
        right_half = frame_resized.crop((THUMB_WIDTH // 2, 0, THUMB_WIDTH, THUMB_HEIGHT))
        canvas.paste(right_half, (THUMB_WIDTH // 2, 0))
    
    # Step 4: Render title text on left half
    # Split title into 2-3 lines
    words = title_text.split()
    lines = []
    if len(words) <= 3:
        lines = [title_text]
    elif len(words) <= 6:
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        third = len(words) // 3
        lines = [
            " ".join(words[:third]),
            " ".join(words[third:third*2]),
            " ".join(words[third*2:])
        ]
    
    # Try to use a bold font
    try:
        font = ImageFont.truetype("arial.ttf", 52)
    except OSError:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        except OSError:
            font = ImageFont.load_default()
    
    y_pos = THUMB_HEIGHT // 2 - (len(lines) * 60) // 2
    for line in lines:
        # Draw text shadow
        draw.text((42, y_pos + 2), line, fill=(0, 0, 0), font=font)
        # Draw text
        draw.text((40, y_pos), line, fill=(255, 255, 255), font=font)
        y_pos += 65
    
    # Step 5: Apply slight gradient/vignette overlay
    # Simple darkening at edges
    gradient = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for i in range(50):
        alpha = int(80 * (i / 50))
        gradient_draw.rectangle(
            [0, THUMB_HEIGHT - 50 + i, THUMB_WIDTH, THUMB_HEIGHT - 50 + i + 1],
            fill=(0, 0, 0, alpha)
        )
    
    canvas = Image.alpha_composite(canvas.convert("RGBA"), gradient)
    canvas = canvas.convert("RGB")
    
    # Save
    canvas.save(output_path, "JPEG", quality=90)
    logger.info(f"Thumbnail generated: {output_path}")
    return output_path
