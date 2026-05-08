"""Backend-only query-by-image similarity search."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from multimedia_search.core.index import IndexReader
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.vision.image_features import (
    compare_image_features,
    extract_image_features,
)

_IMAGE_TYPES = {"jpg", "jpeg", "png", "webp"}


def find_similar_images(
    query_image_path: Path | str,
    reader: IndexReader,
    top_k: int = 5,
    exclude_query_path: bool = True,
) -> List[Dict[str, Any]]:
    """
    Find indexed local images visually similar to a query image.

    This is intentionally separate from ranked/Boolean/phrase retrieval.
    It only compares visual features against already indexed local image documents.
    """
    if top_k <= 0:
        return []

    query_path = Path(query_image_path).expanduser()
    query_features = extract_image_features(query_path)
    query_resolved = _safe_resolve(query_path)

    results: List[Dict[str, Any]] = []

    for doc_id in sorted(reader.doc_metadata.keys()):
        meta = reader.get_doc_metadata(doc_id)

        file_type = str(meta.get("file_type", "")).lower()
        path_value = str(meta.get("path", ""))

        if not _is_local_indexed_image(path_value, file_type):
            continue

        candidate_path = Path(path_value).expanduser()
        candidate_resolved = _safe_resolve(candidate_path)

        if exclude_query_path and query_resolved and candidate_resolved == query_resolved:
            continue

        try:
            candidate_features = extract_image_features(candidate_path)
        except ValueError:
            continue

        score = compare_image_features(query_features, candidate_features)

        results.append(
            {
                "doc_id": doc_id,
                "score": score,
                "path": str(candidate_path),
                "file_type": file_type,
            }
        )

    results.sort(key=lambda item: (-float(item["score"]), str(item["path"]), int(item["doc_id"])))
    return results[:top_k]


def find_similar_images_from_index_file(
    query_image_path: Path | str,
    index_path: Path | str,
    top_k: int = 5,
    exclude_query_path: bool = True,
) -> List[Dict[str, Any]]:
    """Load an index file and find visually similar indexed images."""
    reader = IndexPersistence.load(Path(index_path))

    return find_similar_images(
        query_image_path=query_image_path,
        reader=reader,
        top_k=top_k,
        exclude_query_path=exclude_query_path,
    )


def _is_local_indexed_image(path_value: str, file_type: str) -> bool:
    """Return True only for supported local image metadata entries."""
    if file_type not in _IMAGE_TYPES:
        return False

    if path_value.startswith(("http://", "https://")):
        return False

    path = Path(path_value).expanduser()
    return path.exists() and path.is_file()


def _safe_resolve(path: Path) -> Optional[Path]:
    """Resolve a path without raising for unusual platform/path cases."""
    try:
        return path.resolve()
    except OSError:
        return None