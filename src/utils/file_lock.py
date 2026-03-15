# src/utils/file_lock.py
# Atomic JSON file read/write to prevent corruption from concurrent runs

import json
import os
import shutil
import tempfile
import logging

logger = logging.getLogger(__name__)


def read_json(path, default=None):
    """
    Read a JSON file safely. Returns default if file doesn't exist.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else []
    except json.JSONDecodeError:
        logger.error(f"Corrupted JSON file: {path}")
        return default if default is not None else []


def write_json(path, data):
    """
    Write JSON atomically — write to temp file first, then rename.
    Prevents corruption if pipeline crashes mid-write.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    # Write to temp file in same directory (so rename is atomic)
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Atomic rename (on same filesystem)
        shutil.move(tmp_path, path)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def append_to_json_list(path, entry):
    """
    Append a single entry to a JSON file that contains a list.
    Creates the file with [entry] if it doesn't exist.
    """
    data = read_json(path, default=[])
    data.append(entry)
    write_json(path, data)
