"""Service layer for web interface – reuses core logic without printing."""

import re
from os.path import commonpath, normcase
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from multimedia_search.audio.metadata import (
    AUDIO_EXTENSIONS,
    extract_audio_sections,
    is_audio_file_type as is_supported_audio_file_type,
)
from multimedia_search.config import INDEX_FILE
from multimedia_search.core.analytics import get_document_info, get_term_info
from multimedia_search.core.boolean import BooleanQueryError, BooleanRetriever
from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder, IndexReader
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.core.phrase import PhraseSearcher
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.core.retrieval import RankedRetriever
from multimedia_search.parsers.parser_factory import ParserFactory
from multimedia_search.scanner.file_scanner import FileScanner
from multimedia_search.sources.internet_archive import fetch_internet_archive_videos
from multimedia_search.sources.news_rss import fetch_news_rss_documents
from multimedia_search.sources.openverse import (
    fetch_openverse_audio,
    fetch_openverse_images,
)
from multimedia_search.sources.short_video import (
    build_short_video_documents,
    load_short_video_metadata_file,
)
from multimedia_search.sources.source_document import normalize_source_document
from multimedia_search.sources.topic_short_video import build_topic_short_video_documents
from multimedia_search.sources.wikipedia import fetch_wikipedia_documents
from multimedia_search.sources.youtube_rss import fetch_youtube_rss_short_video_documents
from multimedia_search.utils.exceptions import IndexNotFoundError
from multimedia_search.utils.file_utils import is_sidecar_txt
from multimedia_search.utils.query_assist import (
    build_did_you_mean,
    expand_ranked_query,
)
from multimedia_search.utils.query_explore import build_query_exploration_groups
from multimedia_search.video.metadata import (
    VIDEO_EXTENSIONS,
    is_video_file_type as is_supported_video_file_type,
)
from multimedia_search.vision.enrichment import enrich_image_raw_text
from multimedia_search.vision.similarity import find_similar_images
from multimedia_search.web.crawler import crawl_urls
from multimedia_search.web.ingester import ingest_urls
from multimedia_search.web.url_utils import normalize_url


_BOOLEAN_PATTERN = re.compile(r"\b(AND|OR|NOT)\b")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")

_IMAGE_TYPES = {"jpg", "jpeg", "png", "webp"}
_AUDIO_TYPES = set(AUDIO_EXTENSIONS)
_VIDEO_TYPES = set(VIDEO_EXTENSIONS)


def _safe_text(value: Any) -> str:
    """Return a clean string."""
    return str(value or "").strip()


def _coerce_list(value: Any) -> List[str]:
    """Convert metadata values such as hashtags/tags into a display list."""
    if value is None:
        return []

    if isinstance(value, list):
        return [_safe_text(item).lstrip("#") for item in value if _safe_text(item)]

    if isinstance(value, (tuple, set)):
        return [_safe_text(item).lstrip("#") for item in value if _safe_text(item)]

    text = _safe_text(value)
    if not text:
        return []

    if "," in text:
        return [part.strip().lstrip("#") for part in text.split(",") if part.strip()]

    return [text.lstrip("#")]


def _normalize_requested_media_type(media_type: str) -> str:
    """Normalize UI/API media-filter aliases."""
    requested = str(media_type or "all").lower().replace("-", "_").strip()

    aliases = {
        "images": "image",
        "image_only": "image",
        "audio_only": "audio",
        "videos": "video",
        "video_only": "video",
        "short": "short_video",
        "shorts": "short_video",
        "short_videos": "short_video",
        "reels": "short_video",
        "news": "news_article",
        "news_articles": "news_article",
    }

    return aliases.get(requested, requested)


def _is_image_file_type(file_type: str) -> bool:
    """Return True if file type is a supported image type."""
    return str(file_type).lower().lstrip(".") in _IMAGE_TYPES


def _is_video_file_type(file_type: str) -> bool:
    """Return True if file type is a supported video type."""
    return is_supported_video_file_type(file_type)


def _is_audio_file_type(file_type: str) -> bool:
    """Return True if file type is a supported audio type."""
    return (
        is_supported_audio_file_type(file_type)
        and not _is_video_file_type(file_type)
    )


def _get_type_label(file_type: str) -> str:
    """Convert raw file type to human-readable label."""
    ft = str(file_type).lower().lstrip(".")

    if ft == "short_video":
        return "Short video"

    if ft == "news_article":
        return "News article"

    if ft in _IMAGE_TYPES:
        return f"Image ({ft})"

    if ft in _VIDEO_TYPES:
        return f"Video ({ft})"

    if ft in _AUDIO_TYPES:
        return f"Audio ({ft})"

    if ft == "html":
        return "Web page"

    if ft:
        return ft.upper()

    return "Document"


def _resolved_local_path(path_value) -> str:
    """Return the resolved local path to store/display."""
    return str(Path(path_value).expanduser().resolve())


def _normalize_local_path(path_value) -> str:
    """Return a canonical local path key for dedup/merge checks."""
    return normcase(_resolved_local_path(path_value))


def _augment_raw_text_for_indexing(path: Path, raw_text: str) -> str:
    """Apply extra enrichment for image files only."""
    suffix = path.suffix.lower().lstrip(".")
    if suffix in _IMAGE_TYPES:
        return enrich_image_raw_text(path, raw_text)
    return raw_text


def _validate_single_directory_input(directory: str) -> Optional[str]:
    """Validate that the website input contains exactly one directory path."""
    value = str(directory).strip()

    if not value:
        return "Please provide a directory path."

    non_empty_lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(non_empty_lines) > 1:
        return "Only one directory path is supported per request."

    if ";" in value:
        return "Only one directory path is supported per request."

    directory_path = Path(value).expanduser()
    if not directory_path.exists() or not directory_path.is_dir():
        return "Directory not found or not a directory."

    return None


def _rebuild_documents_from_reader(
    reader: IndexReader,
    preprocessor: Preprocessor,
) -> List[Document]:
    """Rebuild searchable documents from persisted metadata."""
    docs: List[Document] = []

    for doc_id in sorted(reader.doc_metadata.keys()):
        meta = reader.get_doc_metadata(doc_id)
        raw_text = str(meta.get("raw_text", "") or "")
        path = str(meta.get("path", ""))
        file_type = str(meta.get("file_type", ""))

        metadata = {
            key: value
            for key, value in meta.items()
            if key not in {"path", "file_type", "num_tokens", "norm", "raw_text"}
        }

        if "://" in path:
            stored_path = path
        else:
            stored_path = _resolved_local_path(path)

        docs.append(
            Document(
                doc_id=doc_id,
                path=stored_path,
                file_type=file_type,
                raw_text=raw_text,
                tokens=preprocessor.process(raw_text),
                metadata=metadata,
            )
        )

    return docs


def _clean_title_text(text: str) -> str:
    """Make paths/titles more readable for display and suggestions."""
    cleaned = str(text).strip()
    if not cleaned:
        return ""

    if cleaned.startswith(("http://", "https://")):
        parsed = urlparse(cleaned)
        host = parsed.netloc
        path = parsed.path.strip("/")
        if path:
            return f"{host} {path.replace('-', ' ').replace('_', ' ')}".strip()
        return host or cleaned

    stem = Path(cleaned).stem
    return stem.replace("_", " ").replace("-", " ").strip() or Path(cleaned).name


def _get_result_title(
    path: str,
    file_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a display title for a result based on metadata or path."""
    metadata = metadata or {}

    title = _safe_text(metadata.get("title", ""))
    if title:
        return title

    if str(file_type).lower() == "html" or str(path).startswith(("http://", "https://")):
        return str(path)

    return Path(str(path)).name


def _media_type_for_document(
    path: str,
    file_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Classify one indexed document for API filtering."""
    metadata = metadata or {}
    path_str = str(path)
    file_type_str = str(file_type).lower().lstrip(".")
    metadata_media_type = _normalize_requested_media_type(
        str(metadata.get("media_type", "") or "")
    )

    if metadata_media_type in {"short_video", "news_article"}:
        return metadata_media_type

    if file_type_str == "short_video":
        return "short_video"

    if file_type_str == "news_article":
        return "news_article"

    if _is_image_file_type(file_type_str):
        return "image"

    if _is_video_file_type(file_type_str):
        return "video"

    if _is_audio_file_type(file_type_str):
        return "audio"

    if path_str.startswith(("http://", "https://")) or file_type_str == "html":
        return "web"

    if metadata_media_type in {"web", "text"}:
        return metadata_media_type

    return "text"


def _build_common_result(
    doc_id: int,
    path: str,
    file_type: str,
    raw_text: str = "",
    score: Optional[float] = None,
    snippet: str = "",
    matched_terms: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one consistent result dict for the website."""
    path_str = str(path)
    file_type_str = str(file_type).lower().lstrip(".")
    matched_terms = matched_terms or []
    metadata = metadata or {}
    word_count = len(raw_text.split()) if raw_text else 0

    media_type = _media_type_for_document(path_str, file_type_str, metadata)

    is_short_video = media_type == "short_video"
    is_news_article = media_type == "news_article"
    is_image = media_type == "image" or _is_image_file_type(file_type_str)
    is_video = media_type == "video" or _is_video_file_type(file_type_str)
    is_audio = media_type == "audio" or _is_audio_file_type(file_type_str)
    is_web = media_type == "web" or path_str.startswith(("http://", "https://"))

    is_local_file = "://" not in path_str and Path(path_str).exists()

    audio_sections = extract_audio_sections(raw_text) if (is_audio or is_video) else {}

    source_url = _safe_text(metadata.get("url", metadata.get("source_url", "")))
    if not source_url and path_str.startswith(("http://", "https://")):
        source_url = path_str

    return {
        "doc_id": doc_id,
        "title": _get_result_title(path_str, file_type_str, metadata),
        "path": path_str,
        "file_type": file_type_str,
        "type_label": _get_type_label(file_type_str),
        "media_type": media_type,
        "is_web": is_web,
        "is_image": is_image,
        "is_audio": is_audio,
        "is_video": is_video,
        "is_short_video": is_short_video,
        "is_news_article": is_news_article,
        "has_local_image_preview": is_image and is_local_file,
        "has_local_audio_preview": is_audio and is_local_file,
        "has_local_video_preview": is_video and is_local_file,
        "source_name": _safe_text(metadata.get("source_name", metadata.get("source", ""))),
        "source_url": source_url,
        "thumbnail_url": _safe_text(metadata.get("thumbnail_url", metadata.get("thumbnail", ""))),
        "published_at": _safe_text(metadata.get("published_at", metadata.get("publish_date", ""))),
        "creator": _safe_text(metadata.get("creator", metadata.get("channel", metadata.get("author", "")))),
        "duration": _safe_text(metadata.get("duration", metadata.get("duration_seconds", ""))),
        "hashtags": _coerce_list(metadata.get("hashtags", metadata.get("tags", []))),
        "score": score,
        "snippet": snippet,
        "matched_terms": matched_terms,
        "word_count": word_count,
        "audio_transcript": audio_sections.get("transcript", ""),
        "audio_summary": audio_sections.get("summary", ""),
        "audio_conclusion": audio_sections.get("conclusion", ""),
        "audio_action_items": audio_sections.get("action_items", []),
        "audio_keywords": audio_sections.get("keywords", []),
        "audio_mentioned_people": audio_sections.get("mentioned_people", []),
        "audio_mentioned_places": audio_sections.get("mentioned_places", []),
        "audio_mentioned_organizations": audio_sections.get("mentioned_organizations", []),
    }


def _load_reader() -> Optional[IndexReader]:
    """Load saved index if present."""
    try:
        return IndexPersistence.load(INDEX_FILE)
    except IndexNotFoundError:
        return None


def get_local_image_path(doc_id: int):
    """Return local image path for a stored image document."""
    reader = _load_reader()
    if not reader:
        return None

    try:
        meta = reader.get_doc_metadata(doc_id)
    except Exception:
        return None

    file_type = str(meta.get("file_type", "")).lower()
    path = str(meta.get("path", ""))

    if not _is_image_file_type(file_type):
        return None

    if "://" in path:
        return None

    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        return None

    return image_path


def get_local_audio_path(doc_id: int):
    """Return local audio path for a stored audio document."""
    reader = _load_reader()
    if not reader:
        return None

    try:
        meta = reader.get_doc_metadata(doc_id)
    except Exception:
        return None

    file_type = str(meta.get("file_type", "")).lower()
    path = str(meta.get("path", ""))

    if not _is_audio_file_type(file_type):
        return None

    if "://" in path:
        return None

    audio_path = Path(path)
    if not audio_path.exists() or not audio_path.is_file():
        return None

    return audio_path


def get_local_video_path(doc_id: int):
    """Return local video path for a stored video document."""
    reader = _load_reader()
    if not reader:
        return None

    try:
        meta = reader.get_doc_metadata(doc_id)
    except Exception:
        return None

    file_type = str(meta.get("file_type", "")).lower()
    path = str(meta.get("path", ""))

    if not _is_video_file_type(file_type):
        return None

    if "://" in path:
        return None

    video_path = Path(path)
    if not video_path.exists() or not video_path.is_file():
        return None

    return video_path


def get_index_stats() -> Dict[str, int]:
    """Return statistics about the current index."""
    stats = {
        "total_docs": 0,
        "local_files": 0,
        "web_pages": 0,
        "images": 0,
        "audio": 0,
        "video": 0,
        "short_videos": 0,
        "news_articles": 0,
    }

    if not INDEX_FILE.exists():
        return stats

    try:
        reader = IndexPersistence.load(INDEX_FILE)
        stats["total_docs"] = reader.get_doc_count()

        for doc_id in sorted(reader.doc_metadata.keys()):
            meta = reader.get_doc_metadata(doc_id)
            path = str(meta.get("path", ""))
            file_type = str(meta.get("file_type", "")).lower()
            media_type = _media_type_for_document(path, file_type, meta)

            if media_type == "web":
                stats["web_pages"] += 1
            elif "://" not in path:
                stats["local_files"] += 1

            if media_type == "image":
                stats["images"] += 1

            if media_type == "audio":
                stats["audio"] += 1

            if media_type == "video":
                stats["video"] += 1

            if media_type == "short_video":
                stats["short_videos"] += 1

            if media_type == "news_article":
                stats["news_articles"] += 1

        return stats
    except Exception:
        return stats


def _is_local_path_inside_directory(path_value, directory_value) -> bool:
    """Return True if a local path is inside the given directory."""
    path_key = _normalize_local_path(path_value)
    directory_key = _normalize_local_path(directory_value)

    try:
        return commonpath([directory_key, path_key]) == directory_key
    except ValueError:
        return False


def index_local_directory(
    directory: str,
    replace_directory: bool = False,
) -> Tuple[bool, str, int]:
    """Index one local directory, merging safely with the existing index."""
    validation_error = _validate_single_directory_input(directory)
    if validation_error:
        return False, validation_error, 0

    scanner = FileScanner()
    factory = ParserFactory()
    preproc = Preprocessor()
    directory_path = Path(directory).expanduser()

    new_docs_raw = []
    errors = []

    try:
        for path in scanner.scan(directory_path):
            if is_sidecar_txt(path):
                continue

            try:
                parser = factory.get_parser(path.suffix.lower())
                raw = parser.parse(path)
                raw = _augment_raw_text_for_indexing(path, raw)
                tokens = preproc.process(raw)
                stored_path = _resolved_local_path(path)
                compare_key = _normalize_local_path(path)
                suffix = path.suffix.lower().lstrip(".")
                new_docs_raw.append((stored_path, compare_key, raw, tokens, suffix))
            except Exception as e:
                errors.append(f"{path.name}: {e}")
    except Exception as e:
        return False, f"Error scanning directory: {e}", 0

    if not new_docs_raw:
        msg = "No supported files found to index."
        if errors:
            msg += f" Warnings: {'; '.join(errors)}"
        return False, msg, 0

    existing_docs: List[Document] = []

    if INDEX_FILE.exists():
        try:
            reader = IndexPersistence.load(INDEX_FILE)
            existing_docs = _rebuild_documents_from_reader(reader, preproc)
        except Exception as e:
            return False, f"Failed to load existing index: {e}", 0

    new_local_compare_keys = {compare_key for _, compare_key, _, _, _ in new_docs_raw}
    merged_docs: List[Document] = []

    for doc in existing_docs:
        doc_path = str(doc.path)
        is_web = doc_path.startswith(("http://", "https://"))

        if is_web:
            merged_docs.append(doc)
            continue

        if replace_directory:
            if not _is_local_path_inside_directory(doc_path, directory_path):
                merged_docs.append(doc)
            continue

        existing_compare_key = _normalize_local_path(doc_path)
        if existing_compare_key not in new_local_compare_keys:
            merged_docs.append(doc)

    for stored_path, _compare_key, raw, tokens, suffix in new_docs_raw:
        merged_docs.append(
            Document(
                doc_id=0,
                path=stored_path,
                file_type=suffix,
                raw_text=raw,
                tokens=tokens,
            )
        )

    for new_id, doc in enumerate(merged_docs):
        doc.doc_id = new_id

    try:
        builder = IndexBuilder()
        builder.build(merged_docs)
        IndexPersistence.save(builder, INDEX_FILE)

        added_count = len(new_docs_raw)
        msg = f"Indexed/updated {added_count} document(s). Total documents: {len(merged_docs)}."
        if errors:
            msg += f" Warnings: {'; '.join(errors)}"
        return True, msg, added_count
    except Exception as e:
        return False, f"Failed to build/save index: {e}", 0


def index_web_urls(urls: List[str]) -> Tuple[bool, str, int]:
    """Index web URLs, skipping already indexed normalized-equivalent URLs."""
    index_path = INDEX_FILE
    existing_urls = set()

    if index_path.exists():
        try:
            reader = IndexPersistence.load(index_path)
            for _, meta in reader.doc_metadata.items():
                stored_path = meta.get("path", "")
                if isinstance(stored_path, str) and stored_path.startswith(("http://", "https://")):
                    existing_urls.add(normalize_url(stored_path))
        except Exception as e:
            return False, f"Failed to load existing index: {e}", 0

    if index_path.exists():
        try:
            reader = IndexPersistence.load(index_path)
            builder = IndexBuilder.from_existing(reader.get_data())
            next_id = max(builder.doc_metadata.keys(), default=-1) + 1
        except Exception as e:
            return False, f"Failed to load existing index: {e}", 0
    else:
        builder = IndexBuilder()
        next_id = 0

    preprocessor = Preprocessor()
    all_docs = ingest_urls(urls, preprocessor)

    new_docs = []
    for doc in all_docs:
        normalized = normalize_url(str(doc.path))
        if normalized in existing_urls:
            continue

        doc.path = normalized
        new_docs.append(doc)
        existing_urls.add(normalized)

    if not new_docs:
        return True, "No new URLs to add (all already indexed or failed).", 0

    for i, doc in enumerate(new_docs):
        doc.doc_id = next_id + i

    try:
        builder.add_documents(new_docs)
        IndexPersistence.save(builder, index_path)
        return True, f"Added {len(new_docs)} new web page(s).", len(new_docs)
    except Exception as e:
        return False, f"Failed to save web pages: {e}", 0


def crawl_and_index_web(
    seed_urls: List[str],
    max_pages: int = 25,
    max_depth: int = 1,
    same_domain: bool = True,
    respect_robots: bool = True,
) -> Tuple[bool, str, int, Dict[str, Any]]:
    """Crawl seed URLs, discover pages, and index discovered URLs."""
    cleaned_seeds = [str(url).strip() for url in seed_urls if str(url).strip()]

    if not cleaned_seeds:
        return False, "Please provide at least one seed URL.", 0, {
            "discovered_urls": [],
            "visited_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

    try:
        crawl_result = crawl_urls(
            cleaned_seeds,
            max_pages=max_pages,
            max_depth=max_depth,
            same_domain=same_domain,
            respect_robots=respect_robots,
        )
    except Exception as exc:
        return False, f"Crawl failed: {exc}", 0, {
            "discovered_urls": [],
            "visited_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "errors": [str(exc)],
        }

    metadata = {
        "discovered_urls": crawl_result.urls,
        "visited_count": crawl_result.visited_count,
        "failed_count": crawl_result.failed_count,
        "skipped_count": crawl_result.skipped_count,
        "errors": crawl_result.errors,
    }

    if not crawl_result.urls:
        return False, "Crawler did not discover any indexable pages.", 0, metadata

    success, message, indexed_count = index_web_urls(crawl_result.urls)
    final_message = f"Crawled {len(crawl_result.urls)} page(s). {message}"

    return success, final_message, indexed_count, metadata


def _looks_like_wikipedia_document(source_doc) -> bool:
    """Return True for Wikipedia connector records."""
    source_name = _safe_text(source_doc.source_name).lower()
    path = _safe_text(source_doc.path).lower()
    url = _safe_text(source_doc.url).lower()

    return (
        "wikipedia" in source_name
        or "wikipedia.org" in path
        or "wikipedia.org" in url
    )


def import_source_documents(
    source_documents: List[Dict[str, Any]],
) -> Tuple[bool, str, int]:
    """Import external API/source documents into the local index."""
    if not source_documents:
        return False, "No source documents to import.", 0

    preprocessor = Preprocessor()
    existing_docs: List[Document] = []

    if INDEX_FILE.exists():
        try:
            reader = IndexPersistence.load(INDEX_FILE)
            existing_docs = _rebuild_documents_from_reader(reader, preprocessor)
        except Exception as e:
            return False, f"Failed to load existing index: {e}", 0

    existing_paths = {str(doc.path) for doc in existing_docs}
    new_docs: List[Document] = []

    for item in source_documents:
        try:
            source_doc = normalize_source_document(item)
        except (TypeError, ValueError):
            continue

        path = source_doc.path.strip()
        file_type = source_doc.file_type.strip().lower().lstrip(".")
        raw_text = source_doc.raw_text.strip()

        if not path or not raw_text:
            continue

        metadata = dict(source_doc.metadata or {})
        metadata.update(
            {
                "source_name": source_doc.source_name,
                "media_type": source_doc.media_type,
                "title": source_doc.title,
                "url": source_doc.url,
                "thumbnail_url": source_doc.thumbnail_url,
                "published_at": source_doc.published_at,
            }
        )

        if not metadata.get("url") and path.startswith(("http://", "https://")):
            metadata["url"] = path

        if _looks_like_wikipedia_document(source_doc):
            file_type = "html"
            metadata["media_type"] = "web"
            metadata["source_name"] = metadata.get("source_name") or "wikipedia"
            if not metadata.get("url") and path.startswith(("http://", "https://")):
                metadata["url"] = path

        if path in existing_paths:
            continue

        new_docs.append(
            Document(
                doc_id=0,
                path=path,
                file_type=file_type,
                raw_text=raw_text,
                tokens=preprocessor.process(raw_text),
                metadata=metadata,
            )
        )
        existing_paths.add(path)

    if not new_docs:
        return True, "No new external documents to import.", 0

    merged_docs = existing_docs + new_docs

    for new_id, doc in enumerate(merged_docs):
        doc.doc_id = new_id

    try:
        builder = IndexBuilder()
        builder.build(merged_docs)
        IndexPersistence.save(builder, INDEX_FILE)

        return (
            True,
            f"Imported {len(new_docs)} external document(s). Total documents: {len(merged_docs)}.",
            len(new_docs),
        )
    except Exception as e:
        return False, f"Failed to import external documents: {e}", 0


def import_wikipedia_data(query: str, limit: int = 10) -> Tuple[bool, str, int]:
    """Import Wikipedia text pages for a query."""
    try:
        docs = fetch_wikipedia_documents(query, limit=limit)
    except Exception as e:
        return False, f"Wikipedia import failed: {e}", 0

    return import_source_documents(docs)


def import_openverse_image_data(query: str, limit: int = 20) -> Tuple[bool, str, int]:
    """Import Openverse image metadata for a query."""
    try:
        docs = fetch_openverse_images(query, limit=limit)
    except Exception as e:
        return False, f"Openverse image import failed: {e}", 0

    return import_source_documents(docs)


def import_openverse_audio_data(query: str, limit: int = 20) -> Tuple[bool, str, int]:
    """Import Openverse audio metadata for a query."""
    try:
        docs = fetch_openverse_audio(query, limit=limit)
    except Exception as e:
        return False, f"Openverse audio import failed: {e}", 0

    return import_source_documents(docs)


def import_internet_archive_video_data(query: str, limit: int = 10) -> Tuple[bool, str, int]:
    """Import Internet Archive video metadata for a query."""
    try:
        docs = fetch_internet_archive_videos(query, limit=limit)
    except Exception as e:
        return False, f"Internet Archive video import failed: {e}", 0

    return import_source_documents(docs)


def import_smart_topic_data(
    topics: List[str],
    limit: int = 10,
    short_video_platform: str = "none",
    youtube_rss_feeds: Optional[List[str]] = None,
) -> Tuple[bool, str, int, Dict[str, Any]]:
    """Import all supported external data types from topics.

    Imports:
    - Wikipedia web/text pages
    - Openverse images
    - Openverse audio
    - Internet Archive videos
    - GDELT news
    - Topic short-video candidates from public video metadata
    - Optional YouTube channel RSS short-video metadata
    """
    cleaned_topics = [str(topic).strip() for topic in topics if str(topic).strip()]
    safe_limit = max(1, min(int(limit), 20))
    platform = str(short_video_platform or "none").strip().lower()
    feeds = [str(feed).strip() for feed in (youtube_rss_feeds or []) if str(feed).strip()]

    if not cleaned_topics:
        return False, "Please provide at least one topic.", 0, {
            "topics": [],
            "warnings": [],
            "details": [],
        }

    all_docs: List[Dict[str, Any]] = []
    warnings: List[str] = []
    details: List[Dict[str, Any]] = []

    for topic in cleaned_topics:
        topic_detail = {
            "topic": topic,
            "wikipedia": 0,
            "openverse_images": 0,
            "openverse_audio": 0,
            "internet_archive_videos": 0,
            "gdelt_news": 0,
            "topic_short_videos": 0,
            "youtube_rss_short_videos": 0,
            "warnings": [],
        }

        try:
            docs = fetch_wikipedia_documents(topic, limit=safe_limit)
            topic_detail["wikipedia"] = len(docs)
            all_docs.extend(docs)
        except Exception as e:
            msg = f"Wikipedia failed for '{topic}': {e}"
            topic_detail["warnings"].append(msg)
            warnings.append(msg)

        try:
            docs = fetch_openverse_images(topic, limit=safe_limit)
            topic_detail["openverse_images"] = len(docs)
            all_docs.extend(docs)
        except Exception as e:
            msg = f"Openverse images failed for '{topic}': {e}"
            topic_detail["warnings"].append(msg)
            warnings.append(msg)

        try:
            docs = fetch_openverse_audio(topic, limit=safe_limit)
            topic_detail["openverse_audio"] = len(docs)
            all_docs.extend(docs)
        except Exception as e:
            msg = f"Openverse audio failed for '{topic}': {e}"
            topic_detail["warnings"].append(msg)
            warnings.append(msg)

        try:
            video_docs = fetch_internet_archive_videos(topic, limit=safe_limit)
            topic_detail["internet_archive_videos"] = len(video_docs)
            all_docs.extend(video_docs)

            short_docs = build_topic_short_video_documents(
                video_documents=video_docs,
                topic=topic,
                limit=safe_limit,
            )
            topic_detail["topic_short_videos"] = len(short_docs)
            all_docs.extend(short_docs)
        except Exception as e:
            msg = f"Internet Archive videos failed for '{topic}': {e}"
            topic_detail["warnings"].append(msg)
            warnings.append(msg)

        try:
            from multimedia_search.sources.gdelt_news import fetch_gdelt_news_documents

            docs = fetch_gdelt_news_documents(topic, limit=safe_limit)
            topic_detail["gdelt_news"] = len(docs)
            all_docs.extend(docs)
        except Exception as e:
            msg = f"GDELT news skipped for '{topic}': {e}"
            topic_detail["warnings"].append(msg)
            warnings.append(msg)

        details.append(topic_detail)

    if platform == "youtube_rss":
        if not feeds:
            msg = "YouTube RSS selected, but no YouTube channel RSS feed URLs were provided."
            warnings.append(msg)
            for detail in details:
                detail["warnings"].append(msg)
        else:
            try:
                docs = fetch_youtube_rss_short_video_documents(
                    feed_urls=feeds,
                    topics=cleaned_topics,
                    limit=safe_limit,
                    require_short_marker=False,
                )
                all_docs.extend(docs)

                for detail in details:
                    detail["youtube_rss_short_videos"] = len(docs)
            except Exception as e:
                msg = f"YouTube RSS short-video import failed: {e}"
                warnings.append(msg)
                for detail in details:
                    detail["warnings"].append(msg)

    elif platform in {"none", "off", "disabled", ""}:
        pass
    else:
        msg = f"Short-video platform '{platform}' is not supported without an official API."
        warnings.append(msg)
        for detail in details:
            detail["warnings"].append(msg)

    success, message, imported_count = import_source_documents(all_docs)

    if warnings:
        message = f"{message} Warnings: {'; '.join(warnings[:8])}"
        if len(warnings) > 8:
            message += f" ... and {len(warnings) - 8} more warning(s)."

    return success, message, imported_count, {
        "topics": cleaned_topics,
        "limit": safe_limit,
        "short_video_platform": platform,
        "youtube_rss_feeds": feeds,
        "warnings": warnings,
        "details": details,
        "fetched_count": len(all_docs),
    }


def import_news_rss_data(feed_urls: List[str], limit: int = 20) -> Tuple[bool, str, int]:
    """Import news articles from one or more RSS/Atom feeds."""
    cleaned_urls = [str(url).strip() for url in feed_urls if str(url).strip()]

    if not cleaned_urls:
        return False, "Please provide at least one RSS feed URL.", 0

    docs: List[Dict[str, Any]] = []
    errors: List[str] = []

    for feed_url in cleaned_urls:
        try:
            docs.extend(fetch_news_rss_documents(feed_url, limit=limit))
        except Exception as e:
            errors.append(f"{feed_url}: {e}")

    success, message, count = import_source_documents(docs)

    if errors:
        message = f"{message} Warnings: {'; '.join(errors)}"

    return success, message, count


def import_short_video_metadata(
    items: List[Dict[str, Any]],
    platform: str = "",
) -> Tuple[bool, str, int]:
    """Import user-provided short-video metadata records."""
    docs = build_short_video_documents(items, platform=platform)
    return import_source_documents(docs)


def import_short_video_metadata_file(
    file_path: str,
    platform: str = "",
) -> Tuple[bool, str, int]:
    """Import short-video metadata from a local JSON or CSV file."""
    try:
        items = load_short_video_metadata_file(file_path)
    except Exception as e:
        return False, f"Short-video metadata import failed: {e}", 0

    return import_short_video_metadata(items, platform=platform)


def reset_index() -> Tuple[bool, str]:
    """Delete the saved index file."""
    if INDEX_FILE.exists():
        try:
            INDEX_FILE.unlink()
            return True, "Index deleted successfully."
        except Exception as e:
            return False, f"Failed to delete index: {e}"

    return True, "No index file found (already empty)."


def _document_matches_media_type(result: Dict[str, Any], media_type: str) -> bool:
    """Return True if a result dict belongs to the requested media type."""
    requested = _normalize_requested_media_type(media_type)

    if requested == "all":
        return True

    if requested == "image":
        return bool(result.get("is_image"))

    if requested == "audio":
        return bool(result.get("is_audio"))

    if requested == "video":
        return bool(result.get("is_video"))

    if requested == "web":
        return bool(result.get("is_web"))

    if requested == "short_video":
        return bool(result.get("is_short_video"))

    if requested == "news_article":
        return bool(result.get("is_news_article"))

    if requested == "text":
        return not (
            result.get("is_web")
            or result.get("is_image")
            or result.get("is_audio")
            or result.get("is_video")
            or result.get("is_short_video")
            or result.get("is_news_article")
        )

    return False


def filter_results_by_media_type(
    results: List[Dict[str, Any]],
    media_type: str = "all",
) -> List[Dict[str, Any]]:
    """Filter shaped result dictionaries for API clients."""
    return [
        result
        for result in results
        if _document_matches_media_type(result, media_type)
    ]


def _effective_media_filter(image_only: bool = False, media_type: str = "all") -> str:
    """Keep old image_only behavior while supporting new media filters."""
    if image_only:
        return "image"
    return _normalize_requested_media_type(media_type)


def list_documents(
    media_type: str = "all",
    limit: int = 50,
    offset: int = 0,
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """List indexed document metadata for the JSON API."""
    reader = _load_reader()

    if not reader:
        return [], ""

    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    requested_media_type = _normalize_requested_media_type(media_type)

    documents: List[Dict[str, Any]] = []

    for doc_id in sorted(reader.doc_metadata.keys()):
        meta = reader.get_doc_metadata(doc_id)
        path = str(meta.get("path", ""))
        file_type = str(meta.get("file_type", "unknown")).lower()
        raw_text = str(meta.get("raw_text", "") or "")

        item = _build_common_result(
            doc_id=doc_id,
            path=path,
            file_type=file_type,
            raw_text=raw_text,
            snippet=raw_text[:240],
            matched_terms=[],
            metadata=meta,
        )

        if requested_media_type != "all" and not _document_matches_media_type(item, requested_media_type):
            continue

        item["num_tokens"] = int(meta.get("num_tokens", 0) or 0)
        item["raw_text_preview"] = raw_text[:300]

        documents.append(item)

    return documents[safe_offset:safe_offset + safe_limit], ""


def get_document_detail(doc_id: int) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return one indexed document with full stored raw text."""
    reader = _load_reader()

    if not reader:
        return None, "No index found."

    meta = reader.get_doc_metadata(doc_id)

    if not meta:
        return None, "Document not found."

    path = str(meta.get("path", ""))
    file_type = str(meta.get("file_type", "unknown")).lower()
    raw_text = str(meta.get("raw_text", "") or "")

    result = _build_common_result(
        doc_id=doc_id,
        path=path,
        file_type=file_type,
        raw_text=raw_text,
        snippet=raw_text[:240],
        matched_terms=[],
        metadata=meta,
    )

    result["num_tokens"] = int(meta.get("num_tokens", 0) or 0)
    result["raw_text"] = raw_text

    return result, ""


def _has_balanced_quotes(query: str) -> bool:
    """Return True only if double quotes are balanced."""
    return query.count('"') >= 2 and query.count('"') % 2 == 0


def _has_real_phrase(query: str) -> bool:
    """Return True if the query contains a non-empty balanced quoted phrase."""
    if not _has_balanced_quotes(query):
        return False

    matches = re.findall(r'"([^"]+)"', query)
    return any(part.strip() for part in matches)


def _has_explicit_boolean(query: str) -> bool:
    """Return True only for explicit Boolean intent."""
    if "(" in query or ")" in query:
        return True

    return bool(_BOOLEAN_PATTERN.search(query))


def detect_search_mode(query: str) -> str:
    """Detect intended search mode safely."""
    q = " ".join(query.strip().split())
    if not q:
        return "ranked"

    if _has_explicit_boolean(q):
        return "boolean"

    if _has_real_phrase(q):
        return "phrase"

    return "ranked"


def autocomplete(query: str, limit: int = 8) -> List[str]:
    """Return prefix autocomplete suggestions based on indexed vocabulary."""
    reader = _load_reader()
    if not reader:
        return []

    q = " ".join(query.strip().split()).lower()
    if not q:
        return []

    token_matches = _TOKEN_PATTERN.findall(q)
    if not token_matches:
        return []

    last_token = token_matches[-1]
    prefix_before = (
        q[:-len(token_matches[-1])].rstrip()
        if q.endswith(token_matches[-1])
        else " ".join(q.split()[:-1])
    )

    terms = list(getattr(reader, "term_to_postings", {}).keys())
    if not terms:
        return []

    ranked_terms = []
    for term in terms:
        if not isinstance(term, str):
            continue

        term_lower = term.lower()
        if not term_lower.startswith(last_token):
            continue

        df = len(reader.get_postings(term))
        ranked_terms.append((term_lower, df))

    ranked_terms.sort(key=lambda item: (-item[1], item[0]))

    suggestions = []
    seen = set()

    for term_lower, _df in ranked_terms:
        suggestion = f"{prefix_before} {term_lower}".strip()
        if suggestion not in seen:
            suggestions.append(suggestion)
            seen.add(suggestion)

        if len(suggestions) >= limit:
            break

    return suggestions


def get_related_searches(query: str) -> List[Dict[str, List[str]]]:
    """Return grouped related-search suggestions for the website UI."""
    return build_query_exploration_groups(query)


def _suggest_query(reader: IndexReader, query: str) -> Optional[str]:
    """Return one did-you-mean suggestion for ranked search."""
    return build_did_you_mean(reader, query, Preprocessor())


def search_ranked(
    query: str,
    top_k: int,
    image_only: bool = False,
    media_type: str = "all",
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Run ranked retrieval and shape results for the website."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    if not query.strip():
        return None, "Empty query."

    requested_media_type = _effective_media_filter(image_only=image_only, media_type=media_type)

    preprocessor = Preprocessor()
    retriever = RankedRetriever(reader, preprocessor)

    expanded_query = expand_ranked_query(query, reader, preprocessor)

    fetch_k = top_k
    if requested_media_type != "all":
        fetch_k = max(top_k, reader.get_doc_count())

    raw_results = retriever.search(expanded_query, fetch_k)
    if raw_results is None:
        return [], ""

    results = []
    for doc_id, score, path, snippet, matched_terms in raw_results:
        meta = reader.get_doc_metadata(doc_id)
        file_type = str(meta.get("file_type", "unknown")).lower()
        raw_text = str(meta.get("raw_text", ""))

        result = _build_common_result(
            doc_id=doc_id,
            path=path,
            file_type=file_type,
            raw_text=raw_text,
            score=score,
            snippet=snippet,
            matched_terms=list(matched_terms) if matched_terms else [],
            metadata=meta,
        )

        if requested_media_type != "all" and not _document_matches_media_type(result, requested_media_type):
            continue

        results.append(result)

        if len(results) >= top_k:
            break

    return results[:top_k], ""


def search_boolean(
    query: str,
    image_only: bool = False,
    media_type: str = "all",
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Run Boolean retrieval and shape results for the website."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    if not query.strip():
        return None, "Empty query."

    requested_media_type = _effective_media_filter(image_only=image_only, media_type=media_type)
    retriever = BooleanRetriever(reader, Preprocessor())

    try:
        doc_ids = retriever.evaluate(query)
    except BooleanQueryError as e:
        return None, f"Invalid Boolean query: {e}"
    except Exception as e:
        return None, f"Boolean search failed: {e}"

    results = []
    for doc_id in sorted(doc_ids):
        meta = reader.get_doc_metadata(doc_id)
        path = str(meta.get("path", ""))
        file_type = str(meta.get("file_type", "unknown")).lower()
        raw_text = str(meta.get("raw_text", ""))

        result = _build_common_result(
            doc_id=doc_id,
            path=path,
            file_type=file_type,
            raw_text=raw_text,
            snippet="",
            matched_terms=[],
            metadata=meta,
        )

        if requested_media_type != "all" and not _document_matches_media_type(result, requested_media_type):
            continue

        results.append(result)

    return results, ""


def search_phrase(
    query: str,
    image_only: bool = False,
    media_type: str = "all",
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Run phrase retrieval and shape results for the website."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    if not query.strip():
        return None, "Empty query."

    requested_media_type = _effective_media_filter(image_only=image_only, media_type=media_type)
    phrase_searcher = PhraseSearcher(reader, Preprocessor())

    try:
        doc_ids = phrase_searcher.search(query)
    except Exception as e:
        return None, f"Phrase search failed: {e}"

    results = []
    for doc_id in sorted(doc_ids):
        meta = reader.get_doc_metadata(doc_id)
        path = str(meta.get("path", ""))
        file_type = str(meta.get("file_type", "unknown")).lower()
        raw_text = str(meta.get("raw_text", ""))

        result = _build_common_result(
            doc_id=doc_id,
            path=path,
            file_type=file_type,
            raw_text=raw_text,
            snippet="",
            matched_terms=[],
            metadata=meta,
        )

        if requested_media_type != "all" and not _document_matches_media_type(result, requested_media_type):
            continue

        results.append(result)

    return results, ""


def search_auto(
    query: str,
    top_k: int,
    image_only: bool = False,
    media_type: str = "all",
) -> Tuple[Optional[List[Dict[str, Any]]], str, str, Optional[str]]:
    """Auto-detect the search mode and run the appropriate search."""
    reader = _load_reader()
    if not reader:
        return None, "No index found.", "ranked", None

    if not query.strip():
        return None, "Empty query.", "ranked", None

    detected_mode = detect_search_mode(query)

    if detected_mode == "phrase":
        results, error = search_phrase(query, image_only=image_only, media_type=media_type)
    elif detected_mode == "boolean":
        results, error = search_boolean(query, image_only=image_only, media_type=media_type)
    else:
        results, error = search_ranked(query, top_k, image_only=image_only, media_type=media_type)

    suggestion = None

    if not error and detected_mode == "ranked":
        no_results = results is not None and len(results) == 0
        if no_results:
            suggestion = _suggest_query(reader, query)

    return results, error, detected_mode, suggestion


def search_similar_images(
    query_image_path: str,
    top_k: int = 5,
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Find indexed local images visually and object-similar to a query image path."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    query_path = str(query_image_path).strip()
    if not query_path:
        return None, "Please provide an image path."

    if top_k <= 0:
        top_k = 5

    try:
        raw_results = find_similar_images(
            query_image_path=query_path,
            reader=reader,
            top_k=top_k,
            exclude_query_path=True,
        )
    except ValueError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Similar image search failed: {e}"

    results: List[Dict[str, Any]] = []

    for item in raw_results:
        doc_id = int(item["doc_id"])
        meta = reader.get_doc_metadata(doc_id)

        path = str(meta.get("path", item.get("path", "")))
        file_type = str(meta.get("file_type", item.get("file_type", "unknown"))).lower()
        raw_text = str(meta.get("raw_text", ""))

        result = _build_common_result(
            doc_id=doc_id,
            path=path,
            file_type=file_type,
            raw_text=raw_text,
            score=float(item.get("score", 0.0)),
            snippet="Object-aware visual similarity match",
            matched_terms=[],
            metadata=meta,
        )

        result["visual_score"] = float(item.get("visual_score", 0.0))
        result["object_score"] = float(item.get("object_score", 0.0))
        result["text_score"] = float(item.get("text_score", 0.0))

        results.append(result)

    return results, ""


def document_info(doc_id: int, top_n: int = 10) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return document analytics for one document."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    try:
        info = get_document_info(reader, doc_id, top_n=top_n)
        return info, ""
    except Exception as e:
        return None, f"Document info failed: {e}"


def term_info(term: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return term analytics for one term."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    try:
        info = get_term_info(reader, term, Preprocessor())
        return info, ""
    except Exception as e:
        return None, f"Term info failed: {e}"