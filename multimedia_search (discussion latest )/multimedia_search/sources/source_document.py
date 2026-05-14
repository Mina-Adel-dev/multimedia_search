"""Normalized source-document schema for external connectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping


KNOWN_MEDIA_TYPES = {
    "text",
    "image",
    "audio",
    "video",
    "web",
    "short_video",
    "news_article",
}


@dataclass(frozen=True)
class SourceDocument:
    """One normalized importable external record."""

    path: str
    file_type: str
    raw_text: str
    source_name: str = ""
    media_type: str = "text"
    title: str = ""
    url: str = ""
    thumbnail_url: str = ""
    published_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "file_type": self.file_type,
            "raw_text": self.raw_text,
            "source_name": self.source_name,
            "media_type": self.media_type,
            "title": self.title,
            "url": self.url,
            "thumbnail_url": self.thumbnail_url,
            "published_at": self.published_at,
            "metadata": dict(self.metadata),
        }


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return ", ".join(_safe_text(item) for item in value if _safe_text(item))

    if isinstance(value, dict):
        return ", ".join(
            f"{key}: {_safe_text(val)}"
            for key, val in value.items()
            if _safe_text(val)
        )

    return str(value).strip()


def _media_type_from_file_type(file_type: Any) -> str:
    """Infer media type from file extension or external pseudo-type."""
    ft = _safe_text(file_type).lower().lstrip(".").replace("-", "_").strip()

    if ft in {"jpg", "jpeg", "png", "webp", "gif", "bmp"}:
        return "image"

    if ft in {"mp3", "wav", "m4a", "ogg", "flac", "aac", "mpga"}:
        return "audio"

    if ft in {"mp4", "webm", "mov", "mkv", "avi", "m4v", "mpg", "mpeg", "ogv"}:
        return "video"

    if ft in {"html", "htm", "web"}:
        return "web"

    if ft == "short_video":
        return "short_video"

    if ft == "news_article":
        return "news_article"

    return "text"


def _clean_media_type(value: Any, fallback: str = "text") -> str:
    media_type = _safe_text(value).lower().replace("-", "_").strip()

    if media_type in KNOWN_MEDIA_TYPES:
        return media_type

    inferred = _media_type_from_file_type(media_type)
    if inferred != "text":
        return inferred

    return fallback


def _build_raw_text(data: Mapping[str, Any], media_type: str) -> str:
    fields = [
        data.get("title", ""),
        data.get("description", ""),
        data.get("summary", ""),
        data.get("caption", ""),
        data.get("transcript", ""),
        data.get("hashtags", ""),
        data.get("tags", ""),
        data.get("creator", data.get("channel", "")),
        data.get("platform", data.get("source_name", "")),
        data.get("published_at", data.get("publish_date", "")),
        data.get("url", ""),
        media_type,
    ]

    metadata = data.get("metadata", {})
    if isinstance(metadata, Mapping):
        fields.extend(metadata.values())

    return "\n".join(_safe_text(value) for value in fields if _safe_text(value)).strip()


def normalize_source_document(item: SourceDocument | Mapping[str, Any]) -> SourceDocument:
    """Normalize old dict connector output or a SourceDocument instance."""
    if isinstance(item, SourceDocument):
        return item

    if not isinstance(item, Mapping):
        raise TypeError("Source document must be a mapping or SourceDocument.")

    file_type = _safe_text(item.get("file_type", "")) or "txt"
    file_type = file_type.lower().lstrip(".")

    explicit_media_type = item.get("media_type", "")

    if explicit_media_type:
        media_type = _clean_media_type(
            explicit_media_type,
            fallback=_media_type_from_file_type(file_type),
        )
    else:
        media_type = _media_type_from_file_type(file_type)

    url = _safe_text(item.get("url", item.get("source_url", "")))
    path = _safe_text(item.get("path", "")) or url

    title = _safe_text(item.get("title", ""))
    source_name = _safe_text(item.get("source_name", item.get("source", "")))
    thumbnail_url = _safe_text(item.get("thumbnail_url", item.get("thumbnail", "")))
    published_at = _safe_text(item.get("published_at", item.get("publish_date", "")))

    raw_text = _safe_text(item.get("raw_text", ""))
    if not raw_text:
        raw_text = _build_raw_text(item, media_type)

    metadata_value = item.get("metadata", {})
    if isinstance(metadata_value, Mapping):
        metadata = dict(metadata_value)
    else:
        metadata = {"metadata": metadata_value}

    for key in (
        "source_name",
        "media_type",
        "title",
        "url",
        "thumbnail_url",
        "published_at",
        "creator",
        "channel",
        "platform",
        "duration",
        "hashtags",
        "tags",
        "description",
        "summary",
    ):
        if key in item and key not in metadata:
            metadata[key] = item[key]

    metadata["media_type"] = media_type
    metadata["file_type"] = file_type

    return SourceDocument(
        path=path,
        file_type=file_type,
        raw_text=raw_text,
        source_name=source_name,
        media_type=media_type,
        title=title,
        url=url,
        thumbnail_url=thumbnail_url,
        published_at=published_at,
        metadata=metadata,
    )