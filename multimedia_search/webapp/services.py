"""Service layer for web interface – reuses core logic without printing."""

import re
from os.path import commonpath, normcase
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from multimedia_search.audio.metadata import (
    AUDIO_EXTENSIONS,
    extract_audio_sections,
    is_audio_file_type,
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
from multimedia_search.utils.exceptions import IndexNotFoundError
from multimedia_search.utils.file_utils import is_sidecar_txt
from multimedia_search.utils.query_assist import (
    build_did_you_mean,
    expand_ranked_query,
)
from multimedia_search.utils.query_explore import build_query_exploration_groups
from multimedia_search.vision.enrichment import enrich_image_raw_text
from multimedia_search.vision.similarity import find_similar_images
from multimedia_search.web.ingester import ingest_urls
from multimedia_search.web.url_utils import normalize_url


_BOOLEAN_PATTERN = re.compile(r"\b(AND|OR|NOT)\b")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
_IMAGE_TYPES = {"jpg", "jpeg", "png", "webp"}
_AUDIO_TYPES = set(AUDIO_EXTENSIONS)




def _is_image_file_type(file_type: str) -> bool:
    """Return True if file type is a supported image type."""
    return str(file_type).lower() in _IMAGE_TYPES

def _is_audio_file_type(file_type: str) -> bool:
    """Return True if file type is a supported audio type."""
    return is_audio_file_type(file_type)


def _get_type_label(file_type: str) -> str:
    """Convert raw file type to human-readable label."""
    ft = str(file_type).lower()
    if ft in _IMAGE_TYPES:
        return f"Image ({ft})"
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


def _rebuild_documents_from_reader(reader: IndexReader, preprocessor: Preprocessor) -> List[Document]:
    """Rebuild searchable documents from persisted metadata."""
    docs: List[Document] = []

    for doc_id in sorted(reader.doc_metadata.keys()):
        meta = reader.get_doc_metadata(doc_id)
        raw_text = str(meta.get("raw_text", "") or "")
        path = str(meta.get("path", ""))
        file_type = str(meta.get("file_type", ""))

        if path.startswith(("http://", "https://")):
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


def _get_result_title(path: str, file_type: str) -> str:
    """Generate a display title for a result based on its path."""
    if str(file_type).lower() == "html" or str(path).startswith(("http://", "https://")):
        return str(path)
    return Path(str(path)).name


def _build_common_result(
    doc_id: int,
    path: str,
    file_type: str,
    raw_text: str = "",
    score: Optional[float] = None,
    snippet: str = "",
    matched_terms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build one consistent result dict for the website."""
    path_str = str(path)
    file_type_str = str(file_type).lower()
    matched_terms = matched_terms or []
    word_count = len(raw_text.split()) if raw_text else 0
    is_image = _is_image_file_type(file_type_str)
    is_audio = _is_audio_file_type(file_type_str)
    audio_sections = extract_audio_sections(raw_text) if is_audio else {}
    return {
        "doc_id": doc_id,
        "title": _get_result_title(path_str, file_type_str),
        "path": path_str,
        "file_type": file_type_str,
        "type_label": _get_type_label(file_type_str),
        "is_web": path_str.startswith(("http://", "https://")),
        "is_image": is_image,
        "score": score,
        "snippet": snippet,
        "matched_terms": matched_terms,
        "word_count": word_count,
        
        
        "is_audio": is_audio,
        "audio_transcript": audio_sections.get("transcript", ""),
        "audio_summary": audio_sections.get("summary", ""),
        "audio_conclusion": audio_sections.get("conclusion", ""),
        "audio_action_items": audio_sections.get("action_items", []),
        "audio_keywords": audio_sections.get("keywords", []),
        "audio_mentioned_people": audio_sections.get("mentioned_people", []),
        "audio_mentioned_places": audio_sections.get("mentioned_places", []),
        "audio_mentioned_organizations": audio_sections.get("mentioned_organizations", []),
    }


def get_local_image_path(doc_id: int):
    reader = _load_reader()
    if not reader:
        return None

    try:
        meta = reader.get_doc_metadata(doc_id)
    except Exception:
        return None

    file_type = str(meta.get("file_type", "")).lower()
    path = str(meta.get("path", ""))

    if file_type not in _IMAGE_TYPES:
        return None
    if path.startswith(("http://", "https://")):
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
    if path.startswith(("http://", "https://")):
        return None

    audio_path = Path(path)
    if not audio_path.exists() or not audio_path.is_file():
        return None

    return audio_path

def get_index_stats() -> Dict[str, int]:
    """Return statistics about the current index."""
    stats = {"total_docs": 0, "local_files": 0, "web_pages": 0}
    if not INDEX_FILE.exists():
        return stats

    try:
        reader = IndexPersistence.load(INDEX_FILE)
        stats["total_docs"] = reader.get_doc_count()

        for doc_id in sorted(reader.doc_metadata.keys()):
            meta = reader.get_doc_metadata(doc_id)
            path = meta.get("path", "")
            if isinstance(path, str) and path.startswith(("http://", "https://")):
                stats["web_pages"] += 1
            else:
                stats["local_files"] += 1

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
    """Index one local directory, merging safely with the existing index.

    If replace_directory is True, existing local documents under that
    directory are removed first, then the current folder contents are indexed.
    """
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


def reset_index() -> Tuple[bool, str]:
    """Delete the saved index file."""
    if INDEX_FILE.exists():
        try:
            INDEX_FILE.unlink()
            return True, "Index deleted successfully."
        except Exception as e:
            return False, f"Failed to delete index: {e}"
    return True, "No index file found (already empty)."


def _load_reader() -> Optional[IndexReader]:
    """Load saved index if present."""
    try:
        return IndexPersistence.load(INDEX_FILE)
    except IndexNotFoundError:
        return None


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
    """
    Return True only for explicit Boolean intent.

    Rules:
    - uppercase AND/OR/NOT count
    - parentheses count
    - lowercase and/or/not do not count as Boolean
    """
    if "(" in query or ")" in query:
        return True
    return bool(_BOOLEAN_PATTERN.search(query))


def detect_search_mode(query: str) -> str:
    """
    Detect intended mode safely.

    Priority:
    - explicit Boolean syntax wins
    - balanced quoted phrases => phrase
    - malformed quotes => ranked fallback
    - normal language => ranked
    """
    q = " ".join(query.strip().split())
    if not q:
        return "ranked"

    if _has_explicit_boolean(q):
        return "boolean"

    if _has_real_phrase(q):
        return "phrase"

    return "ranked"


def autocomplete(query: str, limit: int = 8) -> List[str]:
    """
    Return prefix autocomplete suggestions based on indexed vocabulary first.

    Behavior:
    - type 'd'  -> dog, dig, data...
    - type 'do' -> dog, document...
    - type 'dog' -> dog, dogfood...
    - for multi-word query, only complete the last token
    """
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
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Run ranked retrieval and shape results for the website."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    if not query.strip():
        return None, "Empty query."

    preprocessor = Preprocessor()
    retriever = RankedRetriever(reader, preprocessor)

    expanded_query = expand_ranked_query(query, reader, preprocessor)

    fetch_k = top_k
    if image_only:
        fetch_k = max(top_k, reader.get_doc_count())

    raw_results = retriever.search(expanded_query, fetch_k)
    if raw_results is None:
        return [], ""

    results = []
    for doc_id, score, path, snippet, matched_terms in raw_results:
        meta = reader.get_doc_metadata(doc_id)
        file_type = str(meta.get("file_type", "unknown")).lower()
        raw_text = str(meta.get("raw_text", ""))

        if image_only and not _is_image_file_type(file_type):
            continue

        results.append(
            _build_common_result(
                doc_id=doc_id,
                path=path,
                file_type=file_type,
                raw_text=raw_text,
                score=score,
                snippet=snippet,
                matched_terms=list(matched_terms) if matched_terms else [],
            )
        )

        if len(results) >= top_k:
            break

    return results[:top_k], ""


def search_boolean(
    query: str,
    image_only: bool = False,
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Run Boolean retrieval and shape results for the website."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    if not query.strip():
        return None, "Empty query."

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

        if image_only and not _is_image_file_type(file_type):
            continue

        results.append(
            _build_common_result(
                doc_id=doc_id,
                path=path,
                file_type=file_type,
                raw_text=raw_text,
                snippet="",
                matched_terms=[],
            )
        )

    return results, ""

def search_phrase(
    query: str,
    image_only: bool = False,
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Run phrase retrieval and shape results for the website."""
    reader = _load_reader()
    if not reader:
        return None, "No index found."

    if not query.strip():
        return None, "Empty query."

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

        if image_only and not _is_image_file_type(file_type):
            continue

        results.append(
            _build_common_result(
                doc_id=doc_id,
                path=path,
                file_type=file_type,
                raw_text=raw_text,
                snippet="",
                matched_terms=[],
            )
        )

    return results, ""


def search_auto(
    query: str,
    top_k: int,
    image_only: bool = False,
) -> Tuple[Optional[List[Dict[str, Any]]], str, str, Optional[str]]:
    """
    Auto-detect the search mode and run the appropriate search.

    Returns:
        results, error, detected_mode, suggestion
    """
    reader = _load_reader()
    if not reader:
        return None, "No index found.", "ranked", None

    if not query.strip():
        return None, "Empty query.", "ranked", None

    detected_mode = detect_search_mode(query)

    if detected_mode == "phrase":
        results, error = search_phrase(query, image_only=image_only)
    elif detected_mode == "boolean":
        results, error = search_boolean(query, image_only=image_only)
    else:
        results, error = search_ranked(query, top_k, image_only=image_only)

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
    """Find indexed local images visually similar to a query image path."""
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

        results.append(
            _build_common_result(
                doc_id=doc_id,
                path=path,
                file_type=file_type,
                raw_text=raw_text,
                score=float(item.get("score", 0.0)),
                snippet="Visual similarity match",
                matched_terms=[],
            )
        )

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