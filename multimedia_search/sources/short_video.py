"""Short-video metadata importer.

Metadata-first only.
No scraping, no login bypass, no media downloading.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from multimedia_search.sources.source_document import SourceDocument


_HASHTAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return ", ".join(_safe_text(item) for item in value if _safe_text(item))

    return str(value).strip()


def _list_from_value(value: Any) -> List[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        return [_safe_text(item).lstrip("#") for item in value if _safe_text(item)]

    text = _safe_text(value)
    if not text:
        return []

    if "," in text:
        return [part.strip().lstrip("#") for part in text.split(",") if part.strip()]

    matches = _HASHTAG_PATTERN.findall(text)
    if matches:
        return matches

    return [text.lstrip("#")]


def _extract_hashtags(*values: Any) -> List[str]:
    seen = set()
    hashtags: List[str] = []

    for value in values:
        for tag in _list_from_value(value):
            clean = tag.strip().lstrip("#")
            key = clean.lower()
            if clean and key not in seen:
                hashtags.append(clean)
                seen.add(key)

        for tag in _HASHTAG_PATTERN.findall(_safe_text(value)):
            key = tag.lower()
            if tag and key not in seen:
                hashtags.append(tag)
                seen.add(key)

    return hashtags


def _stable_short_video_path(platform: str, title: str, url: str) -> str:
    basis = f"{platform}|{title}|{url}".encode("utf-8", errors="ignore")
    digest = hashlib.sha256(basis).hexdigest()[:16]
    safe_platform = platform.lower().replace(" ", "_") or "unknown"
    return f"shortvideo://{safe_platform}/{digest}"


def normalize_short_video_item(
    item: Mapping[str, Any],
    default_platform: str = "",
) -> SourceDocument:
    platform = _safe_text(item.get("platform", default_platform)) or "short_video"
    title = _safe_text(item.get("title", "")) or "Short video"
    description = _safe_text(item.get("description", item.get("caption", "")))
    caption = _safe_text(item.get("caption", ""))
    transcript = _safe_text(item.get("transcript", item.get("captions", "")))
    creator = _safe_text(item.get("creator", item.get("channel", item.get("author", ""))))
    duration = _safe_text(item.get("duration", item.get("duration_seconds", "")))
    published_at = _safe_text(item.get("published_at", item.get("publish_date", "")))
    url = _safe_text(item.get("url", item.get("source_url", "")))
    thumbnail_url = _safe_text(item.get("thumbnail_url", item.get("thumbnail", "")))

    hashtags = _extract_hashtags(
        item.get("hashtags"),
        item.get("tags"),
        title,
        description,
        caption,
        transcript,
    )

    path = url or _stable_short_video_path(platform, title, _safe_text(item.get("id", "")))
    hashtag_text = " ".join(f"#{tag}" for tag in hashtags)

    raw_text = f"""
Source: short video metadata
Media type: short_video
Platform: {platform}
Title: {title}
Creator/channel: {creator}
Description: {description}
Caption: {caption}
Transcript/captions: {transcript}
Hashtags: {hashtag_text}
Duration: {duration}
Published date: {published_at}
URL: {url}
Thumbnail URL: {thumbnail_url}
Short video metadata terms: short video reel reels shorts clip vertical video social media external link metadata
""".strip()

    return SourceDocument(
        path=path,
        file_type="short_video",
        raw_text=raw_text,
        source_name=platform,
        media_type="short_video",
        title=title,
        url=url,
        thumbnail_url=thumbnail_url,
        published_at=published_at,
        metadata={
            "platform": platform,
            "creator": creator,
            "description": description,
            "caption": caption,
            "transcript": transcript,
            "hashtags": hashtags,
            "duration": duration,
            "published_at": published_at,
            "url": url,
            "thumbnail_url": thumbnail_url,
        },
    )


def build_short_video_documents(
    items: Iterable[Mapping[str, Any]],
    platform: str = "",
) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []

    for item in items:
        if not isinstance(item, Mapping):
            continue

        document = normalize_short_video_item(item, default_platform=platform)
        if document.path and document.raw_text:
            documents.append(document.to_dict())

    return documents


def load_short_video_metadata_file(path_value: str | Path) -> List[Dict[str, Any]]:
    path = Path(path_value).expanduser()

    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Short-video metadata file not found.")

    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        if isinstance(data, dict):
            for key in ("items", "videos", "short_videos"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [data]

        return []

    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as input_file:
            return [dict(row) for row in csv.DictReader(input_file)]

    raise ValueError("Short-video metadata file must be JSON or CSV.")