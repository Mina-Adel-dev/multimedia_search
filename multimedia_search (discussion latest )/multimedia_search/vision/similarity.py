"""Backend-only object-aware query-by-image similarity search."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from multimedia_search.core.index import IndexReader
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.vision.enrichment import enrich_image_raw_text
from multimedia_search.vision.image_features import (
    compare_image_features,
    extract_image_features,
)

_IMAGE_TYPES = {"jpg", "jpeg", "png", "webp"}

_GENERIC_TERMS = {
    "image",
    "img",
    "photo",
    "picture",
    "pic",
    "query",
    "upload",
    "uploaded",
    "file",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "copy",
    "screenshot",
    "openverse",
    "wikipedia",
    "wikimedia",
    "commons",
    "flickr",
    "https",
    "http",
    "www",
    "com",
    "org",
}

_OBJECT_GROUPS = [
    {"dog", "dogs", "puppy", "puppies", "canine", "retriever", "hound"},
    {"cat", "cats", "kitten", "kittens", "feline"},
    {"person", "people", "human", "humans", "man", "men", "woman", "women", "boy", "boys", "girl", "girls", "child", "children", "face", "portrait"},
    {"car", "cars", "vehicle", "vehicles", "auto", "automobile", "truck", "bus"},
    {"bird", "birds"},
    {"horse", "horses"},
    {"flower", "flowers", "plant", "plants", "tree", "trees"},
    {"building", "buildings", "house", "houses", "architecture"},
    {"computer", "laptop", "screen", "monitor", "keyboard"},
    {"food", "meal", "pizza", "burger", "cake", "bread"},
]


def find_similar_images(
    query_image_path: Path | str,
    reader: IndexReader,
    top_k: int = 5,
    exclude_query_path: bool = True,
) -> List[Dict[str, Any]]:
    """
    Find indexed local images similar to a query image.

    Object-aware scoring:
    - query image objects are extracted using image enrichment
    - candidate image objects/metadata come from indexed raw_text
    - visual similarity is used as a secondary signal
    """
    if top_k <= 0:
        return []

    query_path = Path(query_image_path).expanduser()
    query_features = extract_image_features(query_path)
    query_resolved = _safe_resolve(query_path)

    query_object_text = _extract_query_object_text(query_path)
    query_terms = _terms_from_text(query_object_text)
    query_groups = _matched_object_groups(query_terms)

    results: List[Dict[str, Any]] = []

    for doc_id in sorted(reader.doc_metadata.keys()):
        meta = reader.get_doc_metadata(doc_id)

        file_type = str(meta.get("file_type", "")).lower()
        path_value = str(meta.get("path", ""))
        raw_text = str(meta.get("raw_text", "") or "")

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

        candidate_terms = _terms_from_text(raw_text)
        candidate_groups = _matched_object_groups(candidate_terms)

        raw_visual_score = compare_image_features(query_features, candidate_features)
        visual_score = _calibrate_visual_score(raw_visual_score)

        object_score = _object_group_score(query_groups, candidate_groups)
        text_score = _text_overlap_score(query_terms, candidate_terms)

        final_score = _combine_scores(
            visual_score=visual_score,
            object_score=object_score,
            text_score=text_score,
            query_groups=query_groups,
            candidate_groups=candidate_groups,
        )

        if final_score < 0.18:
            continue

        results.append(
            {
                "doc_id": doc_id,
                "score": final_score,
                "visual_score": visual_score,
                "object_score": object_score,
                "text_score": text_score,
                "path": str(candidate_path),
                "file_type": file_type,
            }
        )

    results.sort(
        key=lambda item: (
            -float(item["score"]),
            -float(item.get("object_score", 0.0)),
            -float(item.get("text_score", 0.0)),
            -float(item.get("visual_score", 0.0)),
            str(item["path"]),
            int(item["doc_id"]),
        )
    )

    return results[:top_k]


def find_similar_images_from_index_file(
    query_image_path: Path | str,
    index_path: Path | str,
    top_k: int = 5,
    exclude_query_path: bool = True,
) -> List[Dict[str, Any]]:
    """Load an index file and find similar indexed images."""
    reader = IndexPersistence.load(Path(index_path))

    return find_similar_images(
        query_image_path=query_image_path,
        reader=reader,
        top_k=top_k,
        exclude_query_path=exclude_query_path,
    )


def _extract_query_object_text(query_path: Path) -> str:
    """Run the same image enrichment on the query image."""
    base_text = "query image object detection visual content"
    try:
        return enrich_image_raw_text(query_path, base_text)
    except Exception:
        return base_text


def _is_local_indexed_image(path_value: str, file_type: str) -> bool:
    """Return True only for supported local image metadata entries."""
    if file_type not in _IMAGE_TYPES:
        return False

    if path_value.startswith(("http://", "https://", "openverse-image:", "wikipedia-image:")):
        return False

    path = Path(path_value).expanduser()
    return path.exists() and path.is_file()


def _safe_resolve(path: Path) -> Optional[Path]:
    """Resolve a path without raising for unusual platform/path cases."""
    try:
        return path.resolve()
    except OSError:
        return None


def _terms_from_text(text: str) -> Set[str]:
    """Extract normalized useful terms from text."""
    raw_terms = re.findall(r"[a-zA-Z0-9]+", str(text).lower())

    terms = set()
    for term in raw_terms:
        if len(term) < 2:
            continue

        if term in _GENERIC_TERMS:
            continue

        terms.add(term)

        if term.endswith("s") and len(term) > 3:
            terms.add(term[:-1])

    return terms


def _matched_object_groups(terms: Set[str]) -> List[Set[str]]:
    """Return known object groups found in a term set."""
    matched = []

    for group in _OBJECT_GROUPS:
        if terms.intersection(group):
            matched.append(group)

    return matched


def _object_group_score(
    query_groups: List[Set[str]],
    candidate_groups: List[Set[str]],
) -> float:
    """Score object category overlap."""
    if not query_groups:
        return 0.0

    if not candidate_groups:
        return 0.0

    matches = 0

    for query_group in query_groups:
        for candidate_group in candidate_groups:
            if query_group is candidate_group:
                matches += 1
                break

    return min(1.0, matches / max(1, len(query_groups)))


def _text_overlap_score(query_terms: Set[str], candidate_terms: Set[str]) -> float:
    """Score exact term overlap."""
    if not query_terms or not candidate_terms:
        return 0.0

    overlap = query_terms.intersection(candidate_terms)

    if not overlap:
        return 0.0

    return min(1.0, len(overlap) / max(1, len(query_terms)))


def _calibrate_visual_score(score: float) -> float:
    """
    Reduce misleading visual similarity.

    Similar colors/backgrounds should not look like strong object matches.
    """
    safe_score = max(0.0, min(1.0, float(score)))
    return safe_score ** 2.6


def _combine_scores(
    visual_score: float,
    object_score: float,
    text_score: float,
    query_groups: List[Set[str]],
    candidate_groups: List[Set[str]],
) -> float:
    """Combine object, text, and visual scores."""
    has_query_object = bool(query_groups)

    if has_query_object:
        score = (
            0.65 * object_score
            + 0.20 * text_score
            + 0.15 * visual_score
        )

        if object_score == 0.0:
            score *= 0.25

        if _has_conflicting_object_group(query_groups, candidate_groups):
            score *= 0.20

        return max(0.0, min(1.0, score))

    score = (
        0.55 * text_score
        + 0.45 * visual_score
    )

    return max(0.0, min(1.0, score))


def _has_conflicting_object_group(
    query_groups: List[Set[str]],
    candidate_groups: List[Set[str]],
) -> bool:
    """Return True if candidate has another known object but not the query object."""
    if not query_groups or not candidate_groups:
        return False

    for query_group in query_groups:
        for candidate_group in candidate_groups:
            if query_group is candidate_group:
                return False

    return True