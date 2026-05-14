"""Flask application for the multimedia search engine."""

import json
import mimetypes
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.db import database
from multimedia_search.web.url_utils import normalize_url
from multimedia_search.webapp import services


BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static",
)

_ALLOWED_QUERY_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

_VALID_MEDIA_TYPES = {
    "all",
    "text",
    "image",
    "audio",
    "video",
    "web",
    "short_video",
    "news_article",
}

_VALID_SEARCH_MODES = {"auto", "ranked", "boolean", "phrase"}


def _save_uploaded_query_image(uploaded_file):
    """Save an uploaded query image to a temporary local path."""
    filename = secure_filename(uploaded_file.filename or "")

    if not filename:
        return None, "Please choose an image file."

    suffix = Path(filename).suffix.lower()
    extension = suffix.lstrip(".")

    if extension not in _ALLOWED_QUERY_IMAGE_EXTENSIONS:
        return None, "Uploaded query image must be jpg, jpeg, png, or webp."

    upload_dir = Path(tempfile.gettempdir()) / "multimedia_search_query_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_path = upload_dir / f"{uuid4().hex}_{filename}"
    uploaded_file.save(saved_path)

    return saved_path, ""


def _parse_top_k(value, default=5, minimum=1, maximum=50):
    """Parse and clamp a top-k value from form input."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed < minimum:
        return default

    return min(parsed, maximum)


def _normalize_directory_key(path_value):
    """Normalize a local folder path for duplicate-folder validation."""
    path = Path(path_value).expanduser()

    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()

    return os.path.normcase(os.path.normpath(str(resolved)))


def _folder_registry_path():
    """Return the sidecar file used to remember indexed local folders."""
    return Path(services.INDEX_FILE).with_suffix(".folders.json")


def _load_indexed_folder_keys():
    """Load remembered indexed folder keys."""
    registry_path = _folder_registry_path()

    if not registry_path.exists():
        return set()

    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    if not isinstance(data, list):
        return set()

    return {str(item) for item in data if item}


def _save_indexed_folder_keys(keys):
    """Save remembered indexed folder keys."""
    registry_path = _folder_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(sorted(keys), indent=2),
        encoding="utf-8",
    )


def _directory_contains_indexed_docs(directory):
    """Check older indexes by inspecting existing local document paths."""
    index_path = Path(services.INDEX_FILE)

    if not index_path.exists():
        return False

    try:
        reader = IndexPersistence.load(services.INDEX_FILE)
    except (OSError, EOFError, ValueError, AttributeError, TypeError):
        return False

    directory_key = _normalize_directory_key(directory)

    for meta in reader.doc_metadata.values():
        doc_path = str(meta.get("path", "")).strip()

        if not doc_path:
            continue

        if doc_path.startswith(("http://", "https://")):
            continue

        doc_key = _normalize_directory_key(doc_path)

        try:
            common_path = os.path.commonpath([directory_key, doc_key])
        except ValueError:
            continue

        if common_path == directory_key:
            return True

    return False


def _is_directory_already_indexed(directory):
    """Return True if the folder is already indexed."""
    index_path = Path(services.INDEX_FILE)

    if not index_path.exists():
        return False

    directory_key = _normalize_directory_key(directory)
    remembered_keys = _load_indexed_folder_keys()

    if directory_key in remembered_keys:
        return True

    return _directory_contains_indexed_docs(directory)


def _remember_indexed_directory(directory):
    """Remember a successfully indexed local folder."""
    keys = _load_indexed_folder_keys()
    keys.add(_normalize_directory_key(directory))
    _save_indexed_folder_keys(keys)


def _clear_indexed_directory_registry():
    """Remove indexed-folder memory when the index is reset."""
    registry_path = _folder_registry_path()

    try:
        registry_path.unlink(missing_ok=True)
    except OSError:
        pass


def _index_exists() -> bool:
    """Return True if the saved retrieval index currently exists."""
    return Path(services.INDEX_FILE).exists()


def _json_body():
    """Return a JSON object body or an empty dict."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _json_error(message: str, status_code: int = 400, **extra):
    """Return a consistent JSON API error response."""
    payload = {
        "ok": False,
        "error": message,
    }
    payload.update(extra)
    return jsonify(payload), status_code


def _parse_bool(value) -> bool:
    """Parse common JSON/form boolean values safely."""
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    return False


def _parse_api_int(value, default: int, minimum: int, maximum: int) -> int:
    """Parse and clamp an integer from JSON/query values."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed < minimum:
        return default

    return min(parsed, maximum)


def _parse_media_type(value) -> str:
    """Normalize and validate an API media type filter."""
    media_type = str(value or "all").strip().lower().replace("-", "_")

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

    media_type = aliases.get(media_type, media_type)

    if media_type not in _VALID_MEDIA_TYPES:
        return ""

    return media_type


def _valid_media_error():
    """Return a consistent valid-media-types error."""
    return "media_type must be one of: all, text, image, audio, video, web, short_video, news_article"


def _source_status(success: bool) -> str:
    """Convert service success boolean into a database status string."""
    return "success" if success else "failed"


@app.route("/api/health", methods=["GET"])
def api_health():
    """Return JSON health information for API clients."""
    database_status = database.get_database_status()
    status_code = 200 if database_status.get("ok") else 500

    return jsonify(
        {
            "ok": bool(database_status.get("ok")),
            "api": "multimedia-search",
            "version": "0.1",
            "index_exists": _index_exists(),
            "database": database_status,
        }
    ), status_code


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Return index statistics as JSON for API clients."""
    return jsonify(
        {
            "ok": True,
            "index_exists": _index_exists(),
            "stats": services.get_index_stats(),
        }
    )


@app.route("/api/index/local", methods=["POST"])
def api_index_local():
    """Index a local folder through JSON instead of the dashboard form."""
    body = _json_body()
    directory = str(body.get("directory", "")).strip()
    force = _parse_bool(body.get("force", False))

    if not directory:
        return _json_error("Missing required field: directory")

    if _is_directory_already_indexed(directory) and not force:
        message = "This folder is already indexed. Send force=true to refresh it."

        database.record_indexing_run(
            source_type="local_directory",
            source_value=directory,
            status="skipped",
            documents_count=0,
            message=message,
        )

        return _json_error(message, 409, duplicate=True)

    success, message, count = services.index_local_directory(
        directory,
        replace_directory=force,
    )

    database.record_indexing_run(
        source_type="local_directory",
        source_value=directory,
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    if success:
        _remember_indexed_directory(directory)

        database.upsert_indexed_source(
            source_type="local_directory",
            source_value=directory,
            normalized_key=_normalize_directory_key(directory),
            status="active",
            notes=message,
        )

    return jsonify(
        {
            "ok": success,
            "message": message,
            "indexed_count": count,
            "force": force,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/index/web", methods=["POST"])
def api_index_web():
    """Index one or more web URLs through JSON."""
    body = _json_body()
    raw_urls = body.get("urls", body.get("url", []))

    if isinstance(raw_urls, str):
        urls = [raw_urls.strip()] if raw_urls.strip() else []
    elif isinstance(raw_urls, list):
        urls = [str(url).strip() for url in raw_urls if str(url).strip()]
    else:
        urls = []

    if not urls:
        return _json_error("Missing required field: urls")

    success, message, count = services.index_web_urls(urls)

    database.record_indexing_run(
        source_type="web_url",
        source_value=" ".join(urls),
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    if success:
        for url in urls:
            database.upsert_indexed_source(
                source_type="web_url",
                source_value=url,
                normalized_key=normalize_url(url),
                status="active",
                notes=message,
            )

    return jsonify(
        {
            "ok": success,
            "message": message,
            "indexed_count": count,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/crawl", methods=["POST"])
@app.route("/api/crawl/web", methods=["POST"])
def api_crawl_web():
    """Crawl seed URLs, discover pages, and index discovered web pages."""
    body = _json_body()
    raw_seed_urls = body.get("seed_urls", body.get("urls", body.get("url", [])))

    if isinstance(raw_seed_urls, str):
        seed_urls = [raw_seed_urls.strip()] if raw_seed_urls.strip() else []
    elif isinstance(raw_seed_urls, list):
        seed_urls = [str(url).strip() for url in raw_seed_urls if str(url).strip()]
    else:
        seed_urls = []

    if not seed_urls:
        return _json_error("Missing required field: seed_urls")

    max_pages = _parse_api_int(
        body.get("max_pages", 25),
        default=25,
        minimum=1,
        maximum=500,
    )
    max_depth = _parse_api_int(
        body.get("max_depth", 1),
        default=1,
        minimum=0,
        maximum=5,
    )
    same_domain = _parse_bool(body.get("same_domain", True))
    respect_robots = _parse_bool(body.get("respect_robots", True))

    success, message, indexed_count, crawl = services.crawl_and_index_web(
        seed_urls=seed_urls,
        max_pages=max_pages,
        max_depth=max_depth,
        same_domain=same_domain,
        respect_robots=respect_robots,
    )

    source_value = " ".join(seed_urls)

    database.record_indexing_run(
        source_type="web_crawl",
        source_value=source_value,
        status=_source_status(success),
        documents_count=indexed_count,
        message=message,
    )

    if success:
        database.upsert_indexed_source(
            source_type="web_crawl",
            source_value=source_value,
            normalized_key="|".join(normalize_url(url) for url in seed_urls),
            status="active",
            notes=message,
        )

        for discovered_url in crawl.get("discovered_urls", []):
            database.upsert_indexed_source(
                source_type="web_url",
                source_value=discovered_url,
                normalized_key=normalize_url(discovered_url),
                status="active",
                notes="Discovered by crawler.",
            )

    return jsonify(
        {
            "ok": success,
            "message": message,
            "seed_urls": seed_urls,
            "max_pages": max_pages,
            "max_depth": max_depth,
            "same_domain": same_domain,
            "respect_robots": respect_robots,
            "indexed_count": indexed_count,
            "crawl": crawl,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/search/web", methods=["POST"])
def api_search_web_live():
    """Crawl seed URLs, index discovered pages, then search web results."""
    body = _json_body()

    query = str(body.get("query", "")).strip()
    raw_seed_urls = body.get("seed_urls", body.get("urls", body.get("url", [])))

    if isinstance(raw_seed_urls, str):
        seed_urls = [raw_seed_urls.strip()] if raw_seed_urls.strip() else []
    elif isinstance(raw_seed_urls, list):
        seed_urls = [str(url).strip() for url in raw_seed_urls if str(url).strip()]
    else:
        seed_urls = []

    if not query:
        return _json_error("Missing required field: query")

    if not seed_urls:
        return _json_error("Missing required field: seed_urls")

    top_k = _parse_api_int(
        body.get("top_k", 10),
        default=10,
        minimum=1,
        maximum=100,
    )
    max_pages = _parse_api_int(
        body.get("max_pages", 25),
        default=25,
        minimum=1,
        maximum=500,
    )
    max_depth = _parse_api_int(
        body.get("max_depth", 1),
        default=1,
        minimum=0,
        maximum=5,
    )

    same_domain = _parse_bool(body.get("same_domain", True))
    respect_robots = _parse_bool(body.get("respect_robots", True))

    crawl_success, crawl_message, indexed_count, crawl = services.crawl_and_index_web(
        seed_urls=seed_urls,
        max_pages=max_pages,
        max_depth=max_depth,
        same_domain=same_domain,
        respect_robots=respect_robots,
    )

    database.record_indexing_run(
        source_type="web_search_crawl",
        source_value=" ".join(seed_urls),
        status=_source_status(crawl_success),
        documents_count=indexed_count,
        message=crawl_message,
    )

    fetch_top_k = max(top_k, services.get_index_stats().get("total_docs", top_k))

    results, error = services.search_ranked(
        query=query,
        top_k=fetch_top_k,
        image_only=False,
        media_type="web",
    )

    if error:
        return _json_error(
            error,
            400,
            crawl={
                "ok": crawl_success,
                "message": crawl_message,
                **crawl,
            },
        )

    web_results = services.filter_results_by_media_type(results or [], "web")[:top_k]

    database.log_search(
        query=query,
        mode="ranked",
        top_k=top_k,
        image_only=False,
        media_type="web",
        results_count=len(web_results),
    )

    return jsonify(
        {
            "ok": True,
            "query": query,
            "seed_urls": seed_urls,
            "top_k": top_k,
            "crawl": {
                "ok": crawl_success,
                "message": crawl_message,
                "indexed_count": indexed_count,
                **crawl,
            },
            "count": len(web_results),
            "results": web_results,
            "stats": services.get_index_stats(),
        }
    )


@app.route("/api/import/wikipedia", methods=["POST"])
def api_import_wikipedia():
    """Import Wikipedia text data into the local index."""
    body = _json_body()
    query = str(body.get("query", "")).strip()
    limit = _parse_api_int(body.get("limit", 10), default=10, minimum=1, maximum=50)

    if not query:
        return _json_error("Missing required field: query")

    success, message, count = services.import_wikipedia_data(query, limit=limit)

    database.record_indexing_run(
        source_type="wikipedia_import",
        source_value=query,
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    return jsonify(
        {
            "ok": success,
            "source": "wikipedia",
            "query": query,
            "limit": limit,
            "imported_count": count,
            "message": message,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/import/openverse/images", methods=["POST"])
def api_import_openverse_images():
    """Import Openverse image metadata into the local index."""
    body = _json_body()
    query = str(body.get("query", "")).strip()
    limit = _parse_api_int(body.get("limit", 20), default=20, minimum=1, maximum=20)

    if not query:
        return _json_error("Missing required field: query")

    success, message, count = services.import_openverse_image_data(query, limit=limit)

    database.record_indexing_run(
        source_type="openverse_image_import",
        source_value=query,
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    return jsonify(
        {
            "ok": success,
            "source": "openverse_images",
            "query": query,
            "limit": limit,
            "imported_count": count,
            "message": message,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/import/openverse/audio", methods=["POST"])
def api_import_openverse_audio():
    """Import Openverse audio metadata into the local index."""
    body = _json_body()
    query = str(body.get("query", "")).strip()
    limit = _parse_api_int(body.get("limit", 20), default=20, minimum=1, maximum=20)

    if not query:
        return _json_error("Missing required field: query")

    success, message, count = services.import_openverse_audio_data(query, limit=limit)

    database.record_indexing_run(
        source_type="openverse_audio_import",
        source_value=query,
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    return jsonify(
        {
            "ok": success,
            "source": "openverse_audio",
            "query": query,
            "limit": limit,
            "imported_count": count,
            "message": message,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/import/internet-archive/videos", methods=["POST"])
@app.route("/api/import/videos", methods=["POST"])
def api_import_internet_archive_videos():
    """Import Internet Archive video metadata into the local index."""
    body = _json_body()
    query = str(body.get("query", "")).strip()
    limit = _parse_api_int(body.get("limit", 10), default=10, minimum=1, maximum=20)

    if not query:
        return _json_error("Missing required field: query")

    success, message, count = services.import_internet_archive_video_data(
        query,
        limit=limit,
    )

    database.record_indexing_run(
        source_type="internet_archive_video_import",
        source_value=query,
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    return jsonify(
        {
            "ok": success,
            "source": "internet_archive_videos",
            "query": query,
            "limit": limit,
            "imported_count": count,
            "message": message,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/import/news", methods=["POST"])
def api_import_news():
    """Import news articles from RSS/Atom feeds."""
    body = _json_body()
    raw_feeds = body.get("feed_urls", body.get("feeds", body.get("feed_url", [])))

    if isinstance(raw_feeds, str):
        feed_urls = [raw_feeds.strip()] if raw_feeds.strip() else []
    elif isinstance(raw_feeds, list):
        feed_urls = [str(url).strip() for url in raw_feeds if str(url).strip()]
    else:
        feed_urls = []

    limit = _parse_api_int(
        body.get("limit", 20),
        default=20,
        minimum=1,
        maximum=100,
    )

    if not feed_urls:
        return _json_error("Missing required field: feed_urls")

    success, message, count = services.import_news_rss_data(
        feed_urls,
        limit=limit,
    )

    database.record_indexing_run(
        source_type="news_rss_import",
        source_value=" ".join(feed_urls),
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    return jsonify(
        {
            "ok": success,
            "source": "news_rss",
            "feed_urls": feed_urls,
            "limit": limit,
            "imported_count": count,
            "message": message,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/import/short-videos", methods=["POST"])
def api_import_short_videos():
    """Import user-provided short-video metadata without scraping platforms."""
    body = _json_body()
    platform = str(body.get("platform", "")).strip()
    items = body.get("items", body.get("videos", body.get("short_videos", [])))
    metadata_file = str(body.get("metadata_file", "")).strip()

    if isinstance(items, dict):
        items = [items]

    if not isinstance(items, list):
        items = []

    if metadata_file:
        success, message, count = services.import_short_video_metadata_file(
            metadata_file,
            platform=platform,
        )
    else:
        cleaned_items = [item for item in items if isinstance(item, dict)]

        if not cleaned_items:
            return _json_error("Missing required field: items or metadata_file")

        success, message, count = services.import_short_video_metadata(
            cleaned_items,
            platform=platform,
        )

    database.record_indexing_run(
        source_type="short_video_metadata_import",
        source_value=platform or metadata_file or f"{len(items)} item(s)",
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    return jsonify(
        {
            "ok": success,
            "source": "short_video_metadata",
            "platform": platform,
            "imported_count": count,
            "message": message,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/import/all", methods=["POST"])
def api_import_all_sources():
    """Import data from Wikipedia, Openverse, and Internet Archive for one query."""
    body = _json_body()
    query = str(body.get("query", "")).strip()
    limit = _parse_api_int(body.get("limit", 10), default=10, minimum=1, maximum=20)

    if not query:
        return _json_error("Missing required field: query")

    results = {}

    wiki_success, wiki_message, wiki_count = services.import_wikipedia_data(
        query,
        limit=limit,
    )
    results["wikipedia"] = {
        "ok": wiki_success,
        "message": wiki_message,
        "imported_count": wiki_count,
    }

    image_success, image_message, image_count = services.import_openverse_image_data(
        query,
        limit=limit,
    )
    results["openverse_images"] = {
        "ok": image_success,
        "message": image_message,
        "imported_count": image_count,
    }

    audio_success, audio_message, audio_count = services.import_openverse_audio_data(
        query,
        limit=limit,
    )
    results["openverse_audio"] = {
        "ok": audio_success,
        "message": audio_message,
        "imported_count": audio_count,
    }

    video_success, video_message, video_count = services.import_internet_archive_video_data(
        query,
        limit=limit,
    )
    results["internet_archive_videos"] = {
        "ok": video_success,
        "message": video_message,
        "imported_count": video_count,
    }

    total_imported = wiki_count + image_count + audio_count + video_count
    overall_success = wiki_success or image_success or audio_success or video_success

    database.record_indexing_run(
        source_type="all_sources_import",
        source_value=query,
        status=_source_status(overall_success),
        documents_count=total_imported,
        message=f"Imported {total_imported} total external document(s).",
    )

    return jsonify(
        {
            "ok": overall_success,
            "query": query,
            "limit": limit,
            "total_imported": total_imported,
            "results": results,
            "stats": services.get_index_stats(),
        }
    ), 200 if overall_success else 400


@app.route("/api/import/smart", methods=["POST"])
def api_import_smart():
    """Import all supported external data for topics using one smart route."""
    body = _json_body()

    raw_topics = body.get("topics", body.get("topic", body.get("query", [])))

    if isinstance(raw_topics, str):
        topics = [
            line.strip()
            for line in raw_topics.splitlines()
            if line.strip()
        ]
    elif isinstance(raw_topics, list):
        topics = [str(topic).strip() for topic in raw_topics if str(topic).strip()]
    else:
        topics = []

    limit = _parse_api_int(
        body.get("limit", 10),
        default=10,
        minimum=1,
        maximum=20,
    )

    short_video_platform = str(
        body.get("short_video_platform", body.get("platform", "youtube"))
    ).strip().lower()

    if not topics:
        return _json_error("Missing required field: topics")

    success, message, count, metadata = services.import_smart_topic_data(
        topics=topics,
        limit=limit,
        short_video_platform=short_video_platform,
    )

    database.record_indexing_run(
        source_type="smart_topic_import",
        source_value=" | ".join(topics),
        status=_source_status(success),
        documents_count=count,
        message=message,
    )

    return jsonify(
        {
            "ok": success,
            "source": "smart_topic_import",
            "topics": topics,
            "limit": limit,
            "short_video_platform": short_video_platform,
            "imported_count": count,
            "message": message,
            "metadata": metadata,
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/api/search", methods=["POST"])
def api_search():
    """Search indexed text, image metadata, web pages, audio/video transcripts, short-video metadata, and news."""
    body = _json_body()

    query = str(body.get("query", "")).strip()
    requested_mode = str(body.get("mode", "auto")).strip().lower()
    media_type = _parse_media_type(body.get("media_type", "all"))
    top_k = _parse_api_int(
        body.get("top_k", 10),
        default=10,
        minimum=1,
        maximum=200,
    )

    if _parse_bool(body.get("image_only", False)):
        media_type = "image"

    if not query:
        return _json_error("Missing required field: query")

    if requested_mode not in _VALID_SEARCH_MODES:
        return _json_error("mode must be one of: auto, ranked, boolean, phrase")

    if not media_type:
        return _json_error(_valid_media_error())

    suggestion = None
    detected_mode = requested_mode

    if requested_mode == "auto":
        results, error, detected_mode, suggestion = services.search_auto(
            query,
            top_k,
            image_only=False,
            media_type=media_type,
        )
    elif requested_mode == "ranked":
        results, error = services.search_ranked(
            query,
            top_k,
            image_only=False,
            media_type=media_type,
        )
    elif requested_mode == "boolean":
        results, error = services.search_boolean(
            query,
            image_only=False,
            media_type=media_type,
        )
    else:
        results, error = services.search_phrase(
            query,
            image_only=False,
            media_type=media_type,
        )

    if error:
        status_code = 404 if "No index found" in error else 400

        database.log_search(
            query=query,
            mode=detected_mode,
            top_k=top_k,
            image_only=media_type == "image",
            media_type=media_type,
            results_count=0,
        )

        return _json_error(error, status_code, mode=detected_mode)

    limited_results = (results or [])[:top_k]

    database.log_search(
        query=query,
        mode=detected_mode,
        top_k=top_k,
        image_only=media_type == "image",
        media_type=media_type,
        results_count=len(limited_results),
    )

    return jsonify(
        {
            "ok": True,
            "query": query,
            "requested_mode": requested_mode,
            "mode": detected_mode,
            "media_type": media_type,
            "top_k": top_k,
            "count": len(limited_results),
            "suggestion": suggestion,
            "results": limited_results,
        }
    )


@app.route("/api/documents", methods=["GET"])
def api_documents():
    """List indexed documents by media type."""
    media_type = _parse_media_type(request.args.get("media_type", "all"))

    if not media_type:
        return _json_error(_valid_media_error())

    limit = _parse_api_int(
        request.args.get("limit", 50),
        default=50,
        minimum=1,
        maximum=200,
    )
    offset = _parse_api_int(
        request.args.get("offset", 0),
        default=0,
        minimum=0,
        maximum=100000,
    )

    documents, error = services.list_documents(
        media_type=media_type,
        limit=limit,
        offset=offset,
    )

    if error:
        return _json_error(error, 400)

    return jsonify(
        {
            "ok": True,
            "index_exists": _index_exists(),
            "media_type": media_type,
            "limit": limit,
            "offset": offset,
            "count": len(documents or []),
            "documents": documents or [],
        }
    )


@app.route("/api/documents/<int:doc_id>", methods=["GET"])
def api_document_detail(doc_id: int):
    """Return one indexed document by doc_id."""
    document, error = services.get_document_detail(doc_id)

    if error:
        status_code = 404 if (
            "not found" in error.lower()
            or "no index" in error.lower()
        ) else 400

        return _json_error(error, status_code)

    return jsonify(
        {
            "ok": True,
            "document": document,
        }
    )


@app.route("/api/sources", methods=["GET"])
def api_sources():
    """List database-tracked sources and recent indexing runs."""
    limit = _parse_api_int(
        request.args.get("limit", 50),
        default=50,
        minimum=1,
        maximum=200,
    )

    return jsonify(
        {
            "ok": True,
            "sources": database.list_indexed_sources(),
            "recent_runs": database.list_indexing_runs(limit=limit),
        }
    )


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset the saved index and API metadata. Source files are not deleted."""
    body = _json_body()
    clear_database = _parse_bool(body.get("clear_database", True))

    success, message = services.reset_index()

    if success:
        _clear_indexed_directory_registry()

        if clear_database:
            database.clear_api_records()

    return jsonify(
        {
            "ok": success,
            "message": message,
            "database_cleared": bool(success and clear_database),
            "stats": services.get_index_stats(),
        }
    ), 200 if success else 400


@app.route("/autocomplete", methods=["GET"])
def autocomplete():
    """Return live prefix autocomplete suggestions as JSON."""
    query = request.args.get("q", "").strip()
    suggestions = services.autocomplete(query, limit=8)
    return jsonify({"suggestions": suggestions})


@app.route("/image/<int:doc_id>", methods=["GET"])
def image_preview(doc_id: int):
    """Serve a local indexed image preview by doc_id."""
    image_path = services.get_local_image_path(doc_id)
    if image_path is None:
        abort(404)

    mime_type, _ = mimetypes.guess_type(str(image_path))
    return send_file(
        image_path,
        mimetype=mime_type or "application/octet-stream",
        conditional=True,
    )


@app.route("/audio/<int:doc_id>", methods=["GET"])
def audio_preview(doc_id: int):
    """Serve a local indexed audio file by doc_id."""
    audio_path = services.get_local_audio_path(doc_id)
    if audio_path is None:
        abort(404)

    mime_type, _ = mimetypes.guess_type(str(audio_path))
    return send_file(
        audio_path,
        mimetype=mime_type or "application/octet-stream",
        conditional=True,
    )


@app.route("/video/<int:doc_id>", methods=["GET"])
def video_preview(doc_id: int):
    """Serve a local indexed video file by doc_id."""
    video_path = services.get_local_video_path(doc_id)
    if video_path is None:
        abort(404)

    mime_type, _ = mimetypes.guess_type(str(video_path))
    return send_file(
        video_path,
        mimetype=mime_type or "application/octet-stream",
        conditional=True,
    )


@app.route("/", methods=["GET", "POST"])
def home():
    """Main page for indexing, search, and analytics."""
    context = {
        "stats": services.get_index_stats(),
        "query": "",
        "top_k": 10,
        "image_only": False,
        "media_filter": "all",
        "results": None,
        "similar_results": None,
        "similar_image_path": "",
        "similar_top_k": 5,
        "related_searches": [],
    }

    if request.method == "POST":
        action = request.form.get("action")

        if action in {"index_local", "force_index_local"}:
            directory = request.form.get("directory", "").strip()
            force_reindex = action == "force_index_local"

            if not directory:
                context["message"] = "Please provide a directory path."
                context["message_type"] = "error"
            elif _is_directory_already_indexed(directory) and not force_reindex:
                context["message"] = "This folder is already indexed. No duplicate indexing was done."
                context["message_type"] = "warning"
                context["stats"] = services.get_index_stats()
            else:
                success, msg, _count = services.index_local_directory(
                    directory,
                    replace_directory=force_reindex,
                )

                if success and force_reindex:
                    context["message"] = f"Folder force re-indexed successfully. {msg}"
                elif success:
                    context["message"] = f"Folder indexed successfully. {msg}"
                else:
                    context["message"] = msg

                context["message_type"] = "success" if success else "error"
                context["stats"] = services.get_index_stats()

                if success:
                    _remember_indexed_directory(directory)

        elif action == "index_web":
            urls_input = request.form.get("urls", "").strip()

            if not urls_input:
                context["message"] = "Please provide at least one URL."
                context["message_type"] = "error"
            else:
                urls = [u.strip() for u in urls_input.split() if u.strip()]
                success, msg, _count = services.index_web_urls(urls)
                context["message"] = msg
                context["message_type"] = "success" if success else "error"
                context["stats"] = services.get_index_stats()

        elif action == "reset_index":
            success, msg = services.reset_index()
            context["message"] = msg
            context["message_type"] = "success" if success else "error"
            context["stats"] = services.get_index_stats()

            if success:
                _clear_indexed_directory_registry()

        elif action == "search":
            query = request.form.get("query", "").strip()
            top_k_str = request.form.get("top_k", "10")
            media_filter = _parse_media_type(request.form.get("media_filter", "all"))

            if not media_filter:
                media_filter = "all"

            image_only = media_filter == "image"
            top_k = _parse_top_k(top_k_str, default=10, minimum=1, maximum=100)

            context["query"] = query
            context["top_k"] = top_k
            context["media_filter"] = media_filter
            context["image_only"] = image_only

            if not query:
                context["message"] = "Empty query."
                context["message_type"] = "error"
            else:
                results, error, detected_mode, suggestion = services.search_auto(
                    query,
                    top_k,
                    image_only=False,
                    media_type=media_filter,
                )

                if error:
                    context["message"] = error
                    context["message_type"] = "error"
                else:
                    context["results"] = (results or [])[:top_k]
                    context["detected_mode"] = detected_mode

                    if detected_mode == "ranked":
                        context["related_searches"] = services.get_related_searches(query)

                    if suggestion:
                        context["suggestion"] = suggestion

        elif action == "similar_image":
            image_path = request.form.get("similar_image_path", "").strip()
            top_k_str = request.form.get("similar_top_k", "5")
            uploaded_file = request.files.get("similar_image_file")

            top_k = _parse_top_k(top_k_str, default=5, minimum=1, maximum=50)

            context["similar_image_path"] = image_path
            context["similar_top_k"] = top_k
            context["results"] = None

            temp_query_path = None
            search_path = image_path

            if uploaded_file and uploaded_file.filename:
                temp_query_path, upload_error = _save_uploaded_query_image(uploaded_file)

                if upload_error:
                    context["message"] = upload_error
                    context["message_type"] = "error"
                    context["similar_results"] = None
                    return render_template("index.html", **context)

                search_path = str(temp_query_path)
                context["similar_image_path"] = uploaded_file.filename

            if not search_path:
                context["message"] = "Please provide an image path or upload an image."
                context["message_type"] = "error"
                context["similar_results"] = None
            else:
                try:
                    results, error = services.search_similar_images(search_path, top_k)
                finally:
                    if temp_query_path:
                        try:
                            temp_query_path.unlink(missing_ok=True)
                        except OSError:
                            pass

                if error:
                    context["message"] = error
                    context["message_type"] = "error"
                    context["similar_results"] = None
                else:
                    context["similar_results"] = results if results is not None else []

        elif action == "doc_info":
            doc_id_str = request.form.get("doc_id", "").strip()
            top_n_str = request.form.get("top_n", "10")

            try:
                doc_id = int(doc_id_str)
                top_n = int(top_n_str)
            except ValueError:
                context["message"] = "Invalid document ID or top-n."
                context["message_type"] = "error"
            else:
                info, error = services.document_info(doc_id, top_n)

                if error:
                    context["message"] = error
                    context["message_type"] = "error"
                else:
                    context["doc_info"] = info

        elif action == "term_info":
            term = request.form.get("term", "").strip()

            if not term:
                context["message"] = "Please provide a term."
                context["message_type"] = "error"
            else:
                info, error = services.term_info(term)

                if error:
                    context["message"] = error
                    context["message_type"] = "error"
                else:
                    context["term_info"] = info

    return render_template("index.html", **context)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False,
    )