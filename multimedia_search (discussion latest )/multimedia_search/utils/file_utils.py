"""File utility functions."""

from pathlib import Path
from typing import Set

# Image extensions that can have sidecar .txt files
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

def is_sidecar_txt(file_path: Path) -> bool:
    """
    Determine if a .txt file is a sidecar for an image.
    Returns True if file_path has suffix .txt and there exists an image file
    with the same stem in the same directory.
    """
    if file_path.suffix.lower() != ".txt":
        return False
    stem = file_path.stem
    parent = file_path.parent
    for ext in IMAGE_EXTS:
        if (parent / (stem + ext)).exists():
            return True
    return False