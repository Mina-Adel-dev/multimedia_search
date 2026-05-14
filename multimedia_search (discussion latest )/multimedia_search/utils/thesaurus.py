"""General synonym / thesaurus helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set

import multimedia_search.config as config
from multimedia_search.core.preprocessor import Preprocessor


_RESOURCE_FILE = (
    Path(__file__).resolve().parent.parent / "resources" / "synonyms.json"
)


@lru_cache(maxsize=1)
def _load_raw_synonyms() -> Dict[str, List[str]]:
    if not _RESOURCE_FILE.exists():
        return {}

    try:
        data = json.loads(_RESOURCE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    cleaned: Dict[str, List[str]] = {}
    for key, values in data.items():
        if not isinstance(key, str) or not isinstance(values, list):
            continue

        bucket: List[str] = []
        for value in values:
            if isinstance(value, str) and value.strip():
                bucket.append(value.strip())

        if bucket:
            cleaned[key.strip()] = bucket

    return cleaned


def _normalize_single_term(text: str, preprocessor: Preprocessor) -> str:
    tokens = preprocessor.process(text)
    if len(tokens) != 1:
        return ""
    return tokens[0]


@lru_cache(maxsize=8)
def _build_normalized_synonym_map_cached(
    stopwords_key: tuple,
    use_stemming: bool,
) -> Dict[str, List[str]]:
    preprocessor = Preprocessor(stopwords=set(stopwords_key), use_stemming=use_stemming)
    raw = _load_raw_synonyms()

    normalized: Dict[str, List[str]] = {}

    for key, values in raw.items():
        norm_key = _normalize_single_term(key, preprocessor)
        if not norm_key:
            continue

        bucket = normalized.setdefault(norm_key, [])

        for value in values:
            norm_value = _normalize_single_term(value, preprocessor)
            if not norm_value or norm_value == norm_key:
                continue
            if norm_value not in bucket:
                bucket.append(norm_value)

    return normalized


def build_normalized_synonym_map(preprocessor: Preprocessor) -> Dict[str, List[str]]:
    stopwords_key = tuple(sorted(preprocessor.stopwords))
    return _build_normalized_synonym_map_cached(stopwords_key, preprocessor.use_stemming)


def get_synonyms_for_term(term: str, preprocessor: Preprocessor) -> List[str]:
    if not config.SYNONYM_EXPANSION_ENABLED:
        return []

    synonym_map = build_normalized_synonym_map(preprocessor)
    return list(synonym_map.get(term, []))


def expand_terms_with_synonyms(
    terms: List[str],
    vocabulary: Set[str],
    preprocessor: Preprocessor,
) -> List[str]:
    """
    Expand a ranked query with vocabulary-backed synonyms.

    Important:
    - only expands terms that are already normalized
    - only keeps synonyms that actually exist in the current vocabulary
    - caps the number of synonyms per term
    """
    expanded: List[str] = []
    seen: Set[str] = set()

    for term in terms:
        if term not in seen:
            expanded.append(term)
            seen.add(term)

        synonyms = get_synonyms_for_term(term, preprocessor)
        added = 0
        for synonym in synonyms:
            if synonym not in vocabulary:
                continue
            if synonym in seen:
                continue

            expanded.append(synonym)
            seen.add(synonym)
            added += 1

            if added >= config.MAX_SYNONYMS_PER_TERM:
                break

    return expanded