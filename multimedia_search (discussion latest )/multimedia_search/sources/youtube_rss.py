"""YouTube channel RSS short-video metadata connector.

No API key.
No scraping.
No video downloading.

Reads public YouTube channel RSS feeds and imports matching videos as
short-video metadata candidates.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List
from urllib.request import Request, urlopen

from multimedia_search.sources.source_document import SourceDocument


USER_AGENT = "MultimediaSearchEngineStudentProject/0.1"


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _local_name(tag: str) -> str:
    return str(tag).split("}")[-1].lower()


def _first_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}

    for child in node.iter():
        if _local_name(child.tag) in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return text

    return ""


def _first_attr(node: ET.Element, local_name: str, attr_name: str) -> str:
    for child in node.iter():
        if _local_name(child.tag) == local_name.lower():
            value = child.attrib.get(attr_name, "").strip()
            if value:
                return value

    return ""


def _entry_link(entry: ET.Element) -> str:
    for child in entry.iter():
        if _local_name(child.tag) != "link":
            continue

        href = child.attrib.get("href", "").strip()
        if href:
            return href

    return ""


def _entry_author(entry: ET.Element) -> str:
    for child in entry.iter():
        if _local_name(child.tag) == "author":
            return _first_text(child, "name")

    return ""


def _extract_video_id(entry: ET.Element) -> str:
    video_id = _first_text(entry, "videoId")
    if video_id:
        return video_id

    raw_id = _first_text(entry, "id")
    if raw_id.startswith("yt:video:"):
        return raw_id.replace("yt:video:", "").strip()

    link = _entry_link(entry)
    match = re.search(r"[?&]v=([^&]+)", link)
    if match:
        return match.group(1).strip()

    return ""


def _query_matches(text: str, topics: Iterable[str]) -> bool:
    haystack = text.lower()

    for topic in topics:
        topic = _safe_text(topic).lower()
        if not topic:
            continue

        words = [word for word in re.findall(r"[a-z0-9_]+", topic) if len(word) >= 3]

        if not words:
            continue

        if topic in haystack:
            return True

        if any(word in haystack for word in words):
            return True

    return False


def _looks_short_video(text: str) -> bool:
    """Weak marker check. RSS does not reliably include duration."""
    lowered = text.lower()

    markers = {
        "#shorts",
        "#short",
        "youtube shorts",
        "shorts",
        "short video",
        "quick tip",
        "60 seconds",
        "1 minute",
    }

    return any(marker in lowered for marker in markers)


def parse_youtube_rss_documents(
    xml_text: str,
    feed_url: str,
    topics: List[str],
    limit: int = 10,
    require_short_marker: bool = False,
) -> List[Dict[str, Any]]:
    """Parse one YouTube RSS feed into short-video metadata documents."""
    safe_limit = max(1, min(int(limit), 50))
    root = ET.fromstring(xml_text)

    channel_title = _first_text(root, "title") or "YouTube channel"
    documents: List[Dict[str, Any]] = []

    entries = [node for node in root.iter() if _local_name(node.tag) == "entry"]

    for entry in entries:
        title = _first_text(entry, "title")
        description = _first_text(entry, "description")
        published_at = _first_text(entry, "published", "updated")
        creator = _entry_author(entry) or channel_title
        video_id = _extract_video_id(entry)
        thumbnail_url = _first_attr(entry, "thumbnail", "url")
        watch_url = _entry_link(entry)

        if not watch_url and video_id:
            watch_url = f"https://www.youtube.com/watch?v={video_id}"

        if not title and not description:
            continue

        combined = f"{title}\n{description}\n{creator}"

        if topics and not _query_matches(combined, topics):
            continue

        has_short_marker = _looks_short_video(combined)

        if require_short_marker and not has_short_marker:
            continue

        raw_text = f"""
Source: YouTube channel RSS metadata
Media type: short_video
Platform: youtube
Channel: {creator}
Title: {title}
Description: {description}
Published date: {published_at}
URL: {watch_url}
Thumbnail URL: {thumbnail_url}
Feed URL: {feed_url}
Short marker found: {has_short_marker}
Short-video metadata terms: short video youtube shorts clip channel rss metadata external link
""".strip()

        document = SourceDocument(
            path=watch_url or f"youtube-rss://{video_id or len(documents)}",
            file_type="short_video",
            raw_text=raw_text,
            source_name="youtube_rss",
            media_type="short_video",
            title=title,
            url=watch_url,
            thumbnail_url=thumbnail_url,
            published_at=published_at,
            metadata={
                "source_name": "youtube_rss",
                "media_type": "short_video",
                "platform": "youtube",
                "creator": creator,
                "description": description,
                "published_at": published_at,
                "url": watch_url,
                "thumbnail_url": thumbnail_url,
                "feed_url": feed_url,
                "video_id": video_id,
                "short_marker_found": has_short_marker,
                "duration": "unknown from RSS",
            },
        )

        documents.append(document.to_dict())

        if len(documents) >= safe_limit:
            break

    return documents


def fetch_youtube_rss_short_video_documents(
    feed_urls: List[str],
    topics: List[str],
    limit: int = 10,
    require_short_marker: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch short-video metadata candidates from YouTube channel RSS feeds."""
    documents: List[Dict[str, Any]] = []

    for feed_url in feed_urls:
        clean_url = _safe_text(feed_url)
        if not clean_url:
            continue

        request = Request(
            clean_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/atom+xml, application/xml, text/xml, */*",
            },
        )

        with urlopen(request, timeout=20) as response:
            xml_text = response.read().decode("utf-8", errors="replace")

        documents.extend(
            parse_youtube_rss_documents(
                xml_text=xml_text,
                feed_url=clean_url,
                topics=topics,
                limit=limit,
                require_short_marker=require_short_marker,
            )
        )

    return documents[: max(1, min(int(limit), 50))]