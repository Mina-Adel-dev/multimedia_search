"""Helpers for video document types."""

from __future__ import annotations


VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
    "mov",
    "mkv",
    "avi",
    "m4v",
    "mpg",
    "mpeg",
    "wmv",
}


def is_video_file_type(file_type: str) -> bool:
    """Return True if file_type is a supported video type."""
    return str(file_type).lower().lstrip(".") in VIDEO_EXTENSIONS