"""Internet Archive video source importer."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


_VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
    "mov",
    "mkv",
    "avi",
    "m4v",
    "mpg",
    "mpeg",
    "ogv",
}


def _fetch_json(url: str, timeout: int = 20) -> Dict[str, Any]:
    """Fetch JSON from a public API endpoint."""
    request = Request(
        url,
        headers={
            "User-Agent": "multimedia-search-engine/0.1",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="ignore")

    data = json.loads(payload)
    return data if isinstance(data, dict) else {}


def _safe_text(value) -> str:
    """Normalize metadata values into readable text."""
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())

    return str(value or "").strip()


def _file_extension(filename: str) -> str:
    """Return lowercase file extension without dot."""
    if "." not in filename:
        return ""

    return filename.rsplit(".", 1)[-1].lower().strip()


def _choose_video_file(identifier: str, metadata: Dict[str, Any]) -> Dict[str, str]:
    """Choose one playable-looking video file from Internet Archive metadata."""
    files = metadata.get("files", [])

    if not isinstance(files, list):
        return {}

    best = {}

    for item in files:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        if not name:
            continue

        ext = _file_extension(name)

        if ext not in _VIDEO_EXTENSIONS:
            continue

        best = {
            "filename": name,
            "extension": ext,
            "format": str(item.get("format", "") or "").strip(),
            "size": str(item.get("size", "") or "").strip(),
            "url": f"https://archive.org/download/{quote(identifier)}/{quote(name)}",
        }

        if ext in {"mp4", "webm"}:
            return best

    return best


def _build_video_document(identifier: str, metadata_response: Dict[str, Any]) -> Dict[str, str]:
    """Convert one Internet Archive item into an indexable document."""
    metadata = metadata_response.get("metadata", {})

    if not isinstance(metadata, dict):
        metadata = {}

    item_url = f"https://archive.org/details/{quote(identifier)}"
    video_file = _choose_video_file(identifier, metadata_response)

    title = _safe_text(metadata.get("title")) or identifier
    creator = _safe_text(metadata.get("creator"))
    description = _safe_text(metadata.get("description"))
    subject = _safe_text(metadata.get("subject"))
    date = _safe_text(metadata.get("date"))
    collection = _safe_text(metadata.get("collection"))
    license_url = _safe_text(metadata.get("licenseurl"))
    runtime = _safe_text(metadata.get("runtime"))

    video_url = video_file.get("url", "")
    video_filename = video_file.get("filename", "")
    video_format = video_file.get("format", "")
    video_size = video_file.get("size", "")
    file_type = video_file.get("extension", "mp4") or "mp4"

    raw_text = f"""
Source: Internet Archive video
Video title: {title}
Video identifier: {identifier}
Video creator: {creator}
Video date: {date}
Video collection: {collection}
Video subjects: {subject}
Video description: {description}
Video runtime: {runtime}
Video format: {video_format}
Video filename: {video_filename}
Video size: {video_size}
Video item URL: {item_url}
Video file URL: {video_url}
Video metadata terms: external video internet archive movie film recording clip media mp4 webm streaming metadata

AUDIO_TRANSCRIPT:
No transcript imported yet. This external video was indexed using Internet Archive metadata.

AUDIO_SUMMARY:
External video metadata imported from Internet Archive. Search uses the title, description, subjects, creator, collection, and file metadata.

AUDIO_CONCLUSION:
This is an external video metadata result. The video file was not downloaded locally.

AUDIO_ACTION_ITEMS:

AUDIO_KEYWORDS:
video, internet archive, external media, metadata, {subject}

AUDIO_MENTIONED_PEOPLE:
{creator}

AUDIO_MENTIONED_PLACES:

AUDIO_MENTIONED_ORGANIZATIONS:
Internet Archive
""".strip()

    return {
        "path": item_url,
        "file_type": file_type,
        "raw_text": raw_text,
    }


def fetch_internet_archive_videos(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """Fetch Internet Archive video metadata for a query."""
    clean_query = str(query or "").strip()

    if not clean_query:
        return []

    safe_limit = max(1, min(int(limit), 20))

    params = urlencode(
        {
            "q": f'({clean_query}) AND mediatype:movies',
            "fl[]": [
                "identifier",
                "title",
                "creator",
                "description",
                "subject",
                "date",
            ],
            "rows": safe_limit,
            "page": 1,
            "output": "json",
        },
        doseq=True,
    )

    search_url = f"https://archive.org/advancedsearch.php?{params}"
    search_payload = _fetch_json(search_url)

    docs = (
        search_payload
        .get("response", {})
        .get("docs", [])
    )

    if not isinstance(docs, list):
        return []

    results: List[Dict[str, str]] = []

    for item in docs:
        if not isinstance(item, dict):
            continue

        identifier = str(item.get("identifier", "")).strip()

        if not identifier:
            continue

        metadata_url = f"https://archive.org/metadata/{quote(identifier)}"

        try:
            metadata_response = _fetch_json(metadata_url)
        except Exception:
            metadata_response = {
                "metadata": item,
                "files": [],
            }

        document = _build_video_document(identifier, metadata_response)

        if document.get("path") and document.get("raw_text"):
            results.append(document)

    return results