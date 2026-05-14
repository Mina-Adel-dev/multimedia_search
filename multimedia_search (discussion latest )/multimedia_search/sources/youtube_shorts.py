"""YouTube short-video metadata connector.

Uses the official YouTube Data API.
Requires YOUTUBE_API_KEY.
Does not scrape YouTube pages and does not download videos.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any, Dict, Iterable, List
from urllib.request import Request, urlopen

from multimedia_search.sources.source_document import SourceDocument


YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
USER_AGENT = "MultimediaSearchEngineStudentProject/0.1"

_ISO_DURATION_RE = re.compile(
    r"^PT"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?$"
)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _api_get_json(url: str) -> Dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _parse_iso8601_duration_seconds(duration: str) -> int:
    """Parse simple YouTube ISO-8601 duration like PT42S or PT1M05S."""
    match = _ISO_DURATION_RE.match(_safe_text(duration))

    if not match:
        return 0

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)

    return hours * 3600 + minutes * 60 + seconds


def _best_thumbnail(thumbnails: Dict[str, Any]) -> str:
    if not isinstance(thumbnails, dict):
        return ""

    for key in ("maxres", "standard", "high", "medium", "default"):
        item = thumbnails.get(key)

        if isinstance(item, dict) and item.get("url"):
            return _safe_text(item.get("url"))

    return ""


def _extract_video_ids(search_items: Iterable[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    seen = set()

    for item in search_items:
        if not isinstance(item, dict):
            continue

        id_value = item.get("id", {})
        video_id = ""

        if isinstance(id_value, dict):
            video_id = _safe_text(id_value.get("videoId"))

        if video_id and video_id not in seen:
            ids.append(video_id)
            seen.add(video_id)

    return ids


def fetch_youtube_short_videos(
    query: str,
    limit: int = 10,
    max_duration_seconds: int = 60,
) -> List[Dict[str, Any]]:
    """Fetch YouTube short-style video metadata for a topic."""
    api_key = _safe_text(os.environ.get("YOUTUBE_API_KEY"))

    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY is not set. YouTube short-video import was skipped.")

    clean_query = _safe_text(query)

    if not clean_query:
        return []

    safe_limit = max(1, min(int(limit), 50))

    search_params = {
        "part": "snippet",
        "type": "video",
        "videoDuration": "short",
        "q": clean_query,
        "maxResults": str(safe_limit),
        "key": api_key,
        "safeSearch": "moderate",
    }

    search_url = f"{YOUTUBE_SEARCH_URL}?{urllib.parse.urlencode(search_params)}"
    search_data = _api_get_json(search_url)

    video_ids = _extract_video_ids(search_data.get("items", []))

    if not video_ids:
        return []

    videos_params = {
        "part": "snippet,contentDetails",
        "id": ",".join(video_ids),
        "key": api_key,
    }

    videos_url = f"{YOUTUBE_VIDEOS_URL}?{urllib.parse.urlencode(videos_params)}"
    videos_data = _api_get_json(videos_url)

    documents: List[Dict[str, Any]] = []

    for item in videos_data.get("items", []):
        if not isinstance(item, dict):
            continue

        video_id = _safe_text(item.get("id"))
        snippet = item.get("snippet", {})
        content_details = item.get("contentDetails", {})

        if not isinstance(snippet, dict):
            snippet = {}

        if not isinstance(content_details, dict):
            content_details = {}

        duration_iso = _safe_text(content_details.get("duration"))
        duration_seconds = _parse_iso8601_duration_seconds(duration_iso)

        if duration_seconds <= 0:
            continue

        if duration_seconds > max_duration_seconds:
            continue

        title = _safe_text(snippet.get("title")) or "YouTube short video"
        description = _safe_text(snippet.get("description"))
        creator = _safe_text(snippet.get("channelTitle"))
        published_at = _safe_text(snippet.get("publishedAt"))
        tags = snippet.get("tags", [])
        thumbnail_url = _best_thumbnail(snippet.get("thumbnails", {}))

        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        shorts_url = f"https://www.youtube.com/shorts/{video_id}"

        raw_text = f"""
Source: YouTube short-video metadata
Media type: short_video
Query topic: {clean_query}
Platform: youtube
Title: {title}
Creator/channel: {creator}
Description: {description}
Tags: {tags}
Duration seconds: {duration_seconds}
Published date: {published_at}
URL: {shorts_url}
Watch URL: {watch_url}
Thumbnail URL: {thumbnail_url}
Short video metadata terms: short video youtube shorts clip vertical video social media metadata
""".strip()

        document = SourceDocument(
            path=shorts_url,
            file_type="short_video",
            raw_text=raw_text,
            source_name="youtube",
            media_type="short_video",
            title=title,
            url=shorts_url,
            thumbnail_url=thumbnail_url,
            published_at=published_at,
            metadata={
                "source_name": "youtube",
                "media_type": "short_video",
                "platform": "youtube",
                "title": title,
                "creator": creator,
                "description": description,
                "duration": str(duration_seconds),
                "published_at": published_at,
                "url": shorts_url,
                "watch_url": watch_url,
                "thumbnail_url": thumbnail_url,
                "tags": tags if isinstance(tags, list) else [],
                "query": clean_query,
                "provider": "youtube_data_api",
            },
        )

        documents.append(document.to_dict())

    return documents