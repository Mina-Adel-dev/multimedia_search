"""Helpers for audio document types and audio result sections."""

from __future__ import annotations

from typing import Dict, List


AUDIO_EXTENSIONS = {
    "mp3",
    "wav",
    "m4a",
    "ogg",
    "webm",
    "mp4",
    "mpeg",
    "mpga",
    "flac",
}


_AUDIO_SECTION_MARKERS = {
    "transcript": "AUDIO_TRANSCRIPT:",
    "summary": "AUDIO_SUMMARY:",
    "conclusion": "AUDIO_CONCLUSION:",
    "action_items": "AUDIO_ACTION_ITEMS:",
    "keywords": "AUDIO_KEYWORDS:",
    "mentioned_people": "AUDIO_MENTIONED_PEOPLE:",
    "mentioned_places": "AUDIO_MENTIONED_PLACES:",
    "mentioned_organizations": "AUDIO_MENTIONED_ORGANIZATIONS:",
}


def is_audio_file_type(file_type: str) -> bool:
    """Return True if file_type is a supported audio/video-with-audio type."""
    return str(file_type).lower().lstrip(".") in AUDIO_EXTENSIONS


def _clean_section_value(value: str) -> str:
    """Normalize section text for UI display."""
    return str(value or "").strip()


def _split_csv_like(value: str) -> List[str]:
    """Split comma/newline/bullet-like model output into clean items."""
    raw = str(value or "").replace("\n", ",")
    parts = []

    for item in raw.split(","):
        cleaned = item.strip().strip("-").strip()
        if cleaned:
            parts.append(cleaned)

    return parts


def extract_audio_sections(raw_text: str) -> Dict[str, object]:
    """Extract audio sections from the parser raw_text.

    The parser stores clear marker lines so the UI can display
    summary/conclusion/entities without needing new index metadata fields.
    """
    text = str(raw_text or "")
    sections: Dict[str, str] = {}

    marker_to_key = {
        marker: key
        for key, marker in _AUDIO_SECTION_MARKERS.items()
    }

    current_key = None
    buffer: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()

        if stripped in marker_to_key:
            if current_key is not None:
                sections[current_key] = "\n".join(buffer).strip()

            current_key = marker_to_key[stripped]
            buffer = []
            continue

        if current_key is not None:
            buffer.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(buffer).strip()

    return {
        "transcript": _clean_section_value(sections.get("transcript", "")),
        "summary": _clean_section_value(sections.get("summary", "")),
        "conclusion": _clean_section_value(sections.get("conclusion", "")),
        "action_items": _split_csv_like(sections.get("action_items", "")),
        "keywords": _split_csv_like(sections.get("keywords", "")),
        "mentioned_people": _split_csv_like(sections.get("mentioned_people", "")),
        "mentioned_places": _split_csv_like(sections.get("mentioned_places", "")),
        "mentioned_organizations": _split_csv_like(sections.get("mentioned_organizations", "")),
    }