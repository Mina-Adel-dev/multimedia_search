"""Openverse data importer for image and audio metadata + local downloads."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


OPENVERSE_API_URL = "https://api.openverse.org/v1"
USER_AGENT = "MultimediaSearchEngineStudentProject/0.1"

IMPORT_ROOT = Path("imported_data") / "openverse"
IMAGE_DIR = IMPORT_ROOT / "images"
AUDIO_DIR = IMPORT_ROOT / "audio"

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_AUDIO_BYTES = 80 * 1024 * 1024


def _get_json(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Call Openverse API and return JSON."""
    url = f"{OPENVERSE_API_URL}/{path}/?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _text_from_openverse_item(item: Dict[str, Any], media_type: str) -> str:
    """Build searchable text from one Openverse item."""
    fields = [
        item.get("title", ""),
        item.get("creator", ""),
        item.get("license", ""),
        item.get("license_version", ""),
        item.get("provider", ""),
        item.get("source", ""),
        item.get("foreign_landing_url", ""),
        item.get("url", ""),
        item.get("thumbnail", ""),
        media_type,
    ]

    tags = item.get("tags") or []
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                fields.append(str(tag.get("name", "")))
            else:
                fields.append(str(tag))

    return "\n".join(str(value) for value in fields if value)


def _best_extension_from_url(url: str, default_ext: str) -> str:
    """Guess a media extension from a URL."""
    clean_url = str(url).split("?")[0].split("#")[0].lower()

    for ext in ("jpg", "jpeg", "png", "webp", "mp3", "wav", "ogg", "flac", "m4a"):
        if clean_url.endswith(f".{ext}"):
            return ext

    return default_ext


def _extension_from_content_type(content_type: str, default_ext: str) -> str:
    """Guess extension from HTTP content type."""
    content_type = str(content_type or "").split(";")[0].strip().lower()
    guessed = mimetypes.guess_extension(content_type)

    if not guessed:
        return default_ext

    ext = guessed.lstrip(".").lower()

    if ext == "jpe":
        return "jpg"

    return ext or default_ext


def _safe_file_name(url: str, extension: str) -> str:
    """Create stable filename from media URL."""
    digest = hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()
    return f"{digest}.{extension}"


def _is_http_url(url: str) -> bool:
    """Return True if URL is HTTP/HTTPS."""
    parsed = urlparse(str(url))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _download_media(
    url: str,
    target_dir: Path,
    default_ext: str,
    max_bytes: int,
) -> Optional[Path]:
    """Download a media file and return local path."""
    url = str(url or "").strip()

    if not url or not _is_http_url(url):
        return None

    target_dir.mkdir(parents=True, exist_ok=True)

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    try:
        with urlopen(request, timeout=45) as response:
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        return None
                except ValueError:
                    pass

            content_type = response.headers.get("Content-Type", "")
            extension = _best_extension_from_url(
                url,
                _extension_from_content_type(content_type, default_ext),
            )

            local_path = target_dir / _safe_file_name(url, extension)

            if local_path.exists() and local_path.stat().st_size > 0:
                return local_path.resolve()

            downloaded = 0

            with local_path.open("wb") as output_file:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break

                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        output_file.close()
                        local_path.unlink(missing_ok=True)
                        return None

                    output_file.write(chunk)

            if local_path.exists() and local_path.stat().st_size > 0:
                return local_path.resolve()

            local_path.unlink(missing_ok=True)
            return None
    except Exception:
        return None


def fetch_openverse_images(query: str, limit: int = 20) -> List[Dict[str, str]]:
    """Download Openverse images and return them as source documents."""
    safe_limit = max(1, min(int(limit), 20))

    data = _get_json(
        "images",
        {
            "q": query,
            "page_size": safe_limit,
        },
    )

    results = data.get("results", [])
    documents: List[Dict[str, str]] = []

    for item in results:
        media_url = str(item.get("url", "") or "").strip()
        title = str(item.get("title", "") or "").strip() or "Openverse image"

        local_path = _download_media(
            media_url,
            IMAGE_DIR,
            default_ext="jpg",
            max_bytes=MAX_IMAGE_BYTES,
        )

        if local_path is None:
            continue

        file_type = local_path.suffix.lower().lstrip(".") or "jpg"
        raw_text = _text_from_openverse_item(item, "image")

        documents.append(
            {
                "path": str(local_path),
                "file_type": file_type,
                "raw_text": raw_text,
                "source_url": str(item.get("foreign_landing_url", "") or media_url),
                "title": title,
            }
        )

    return documents


def fetch_openverse_audio(query: str, limit: int = 20) -> List[Dict[str, str]]:
    """Download Openverse audio and return it as source documents."""
    safe_limit = max(1, min(int(limit), 20))

    data = _get_json(
        "audio",
        {
            "q": query,
            "page_size": safe_limit,
        },
    )

    results = data.get("results", [])
    documents: List[Dict[str, str]] = []

    for item in results:
        media_url = str(item.get("url", "") or "").strip()
        title = str(item.get("title", "") or "").strip() or "Openverse audio"

        local_path = _download_media(
            media_url,
            AUDIO_DIR,
            default_ext="mp3",
            max_bytes=MAX_AUDIO_BYTES,
        )

        if local_path is None:
            continue

        file_type = local_path.suffix.lower().lstrip(".") or "mp3"
        raw_text = _text_from_openverse_item(item, "audio")

        documents.append(
            {
                "path": str(local_path),
                "file_type": file_type,
                "raw_text": raw_text,
                "source_url": str(item.get("foreign_landing_url", "") or media_url),
                "title": title,
            }
        )

    return documents