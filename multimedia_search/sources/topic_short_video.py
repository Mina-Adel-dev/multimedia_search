"""Topic-based short-video metadata fallback.

Uses already-fetched public video metadata and creates short-video-style
external result cards. No scraping and no media downloading.
"""

from __future__ import annotations

from typing import Any, Dict, List

from multimedia_search.sources.source_document import SourceDocument, normalize_source_document


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def build_topic_short_video_documents(
    video_documents: List[Dict[str, Any]],
    topic: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Create short-video metadata candidates from public video metadata."""
    safe_limit = max(1, min(int(limit), 20))
    clean_topic = _safe_text(topic)
    documents: List[Dict[str, Any]] = []

    for item in video_documents:
        try:
            source_doc = normalize_source_document(item)
        except (TypeError, ValueError):
            continue

        metadata = dict(source_doc.metadata or {})

        title = source_doc.title or _safe_text(metadata.get("title")) or "Short video candidate"
        url = source_doc.url or _safe_text(metadata.get("url")) or source_doc.path
        thumbnail_url = source_doc.thumbnail_url or _safe_text(
            metadata.get("thumbnail_url") or metadata.get("thumbnail")
        )
        source_name = source_doc.source_name or _safe_text(metadata.get("source_name")) or "internet_archive"
        published_at = source_doc.published_at or _safe_text(metadata.get("published_at"))
        creator = _safe_text(metadata.get("creator") or metadata.get("channel") or metadata.get("author"))
        description = _safe_text(metadata.get("description") or metadata.get("summary"))
        duration = _safe_text(metadata.get("duration") or metadata.get("duration_seconds") or "unknown")

        if not url:
            continue

        raw_text = f"""
Source: topic short-video metadata candidate
Media type: short_video
Topic: {clean_topic}
Platform/source: {source_name}
Title: {title}
Creator/channel: {creator}
Description: {description}
Duration: {duration}
Published date: {published_at}
URL: {url}
Thumbnail URL: {thumbnail_url}
Short-video terms: short video clip topic video external link metadata public archive
""".strip()

        document = SourceDocument(
            path=f"{url}#short-video-candidate",
            file_type="short_video",
            raw_text=raw_text,
            source_name=source_name,
            media_type="short_video",
            title=title,
            url=url,
            thumbnail_url=thumbnail_url,
            published_at=published_at,
            metadata={
                "source_name": source_name,
                "media_type": "short_video",
                "platform": source_name,
                "title": title,
                "creator": creator,
                "description": description,
                "duration": duration,
                "published_at": published_at,
                "url": url,
                "thumbnail_url": thumbnail_url,
                "topic": clean_topic,
                "provider": "topic_video_metadata_fallback",
                "note": "No-key short-video candidate created from public video metadata.",
            },
        )

        documents.append(document.to_dict())

        if len(documents) >= safe_limit:
            break

    return documents