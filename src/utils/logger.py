# src/utils/logger.py
# Structured logging setup for the clipper pipeline

import os
import logging
import sys
from datetime import datetime


def setup_logger(name="clipper", log_dir="logs"):
    """
    Setup structured logging to both console and file.
    
    Creates a logger that writes to:
    - Console (INFO level, human-readable)
    - logs/daily_run.log (DEBUG level, structured)
    """
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler — INFO level, concise
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler — DEBUG level, structured
    log_file = os.path.join(log_dir, "daily_run.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    return logger


def get_logger(module_name):
    """
    Get a child logger for a specific module.
    Usage: logger = get_logger(__name__)
    """
    return logging.getLogger(f"clipper.{module_name}")


# Initialize the root logger on import
_root_logger = setup_logger()
