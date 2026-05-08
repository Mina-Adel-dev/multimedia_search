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
from multimedia_search.webapp import services

BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static",
)

_ALLOWED_QUERY_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


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

    saved_path = upload_dir / f"{uuid4().hex}{suffix}"
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


@app.route("/", methods=["GET", "POST"])
def home():
    """Main page for indexing, search, and analytics."""
    context = {
        "stats": services.get_index_stats(),
        "query": "",
        "top_k": 10,
        "image_only": False,
        "results": None,
        "similar_results": None,
        "similar_image_path": "",
        "similar_top_k": 5,
        "related_searches": [],
    }

    if request.method == "POST":
        action = request.form.get("action")

        # --- Local indexing ---
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

        # --- Web indexing ---
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

        # --- Reset index ---
        elif action == "reset_index":
            success, msg = services.reset_index()
            context["message"] = msg
            context["message_type"] = "success" if success else "error"
            context["stats"] = services.get_index_stats()

            if success:
                _clear_indexed_directory_registry()

        # --- Search ---
        elif action == "search":
            query = request.form.get("query", "").strip()
            top_k_str = request.form.get("top_k", "10")
            image_only = request.form.get("image_only") == "1"

            try:
                top_k = int(top_k_str)
            except ValueError:
                top_k = 10

            context["query"] = query
            context["top_k"] = top_k
            context["image_only"] = image_only

            if not query:
                context["message"] = "Empty query."
                context["message_type"] = "error"
            else:
                results, error, detected_mode, suggestion = services.search_auto(
                    query,
                    top_k,
                    image_only=image_only,
                )

                if error:
                    context["message"] = error
                    context["message_type"] = "error"
                else:
                    context["results"] = results if results is not None else []
                    context["detected_mode"] = detected_mode

                    if detected_mode == "ranked":
                        context["related_searches"] = services.get_related_searches(query)
                    if suggestion:
                        context["suggestion"] = suggestion

        # --- Similar image search ---
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

        # --- Document info ---
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

        # --- Term info ---
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