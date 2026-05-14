"""Did-you-mean and ranked synonym expansion helpers."""

from __future__ import annotations

import re
from difflib import get_close_matches
from typing import List, Optional, Set

import multimedia_search.config as config
from multimedia_search.core.index import IndexReader
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.utils.phonetics import build_soundex_buckets, soundex
from multimedia_search.utils.thesaurus import expand_terms_with_synonyms


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _normalize_single_term(text: str, preprocessor: Preprocessor) -> str:
    tokens = preprocessor.process(text)
    if len(tokens) != 1:
        return ""
    return tokens[0]


def extract_query_terms(query: str, preprocessor: Preprocessor) -> List[str]:
    return preprocessor.process(query)


def expand_ranked_query(
    query: str,
    reader: IndexReader,
    preprocessor: Preprocessor,
) -> str:
    """
    Expand ranked queries only.
    """
    terms = extract_query_terms(query, preprocessor)
    if not terms:
        return query

    vocabulary = {
        term for term in getattr(reader, "term_to_postings", {}).keys()
        if isinstance(term, str)
    }
    expanded_terms = expand_terms_with_synonyms(terms, vocabulary, preprocessor)

    if not expanded_terms:
        return query

    return " ".join(expanded_terms)


def _get_spelling_candidate(
    normalized_term: str,
    vocabulary: List[str],
) -> Optional[str]:
    direct = get_close_matches(
        normalized_term,
        vocabulary,
        n=1,
        cutoff=config.SPELL_SUGGESTION_CUTOFF,
    )
    if direct:
        return direct[0]

    if not config.SOUNDEX_SUGGESTION_ENABLED:
        return None

    buckets = build_soundex_buckets(vocabulary)
    code = soundex(normalized_term)
    if not code:
        return None

    candidates = buckets.get(code, [])
    if not candidates:
        return None

    narrowed = get_close_matches(normalized_term, candidates, n=1, cutoff=0.55)
    if narrowed:
        return narrowed[0]

    return candidates[0] if candidates else None


def build_did_you_mean(
    reader: IndexReader,
    query: str,
    preprocessor: Preprocessor,
) -> Optional[str]:
    """
    Build one conservative did-you-mean suggestion.

    Rules:
    - keep known terms unchanged
    - replace only unknown normalized terms
    - use spelling similarity first, then soundex fallback
    """
    if not config.SPELL_SUGGESTION_ENABLED:
        return None

    raw_tokens = _TOKEN_PATTERN.findall(query)
    if not raw_tokens:
        return None

    vocabulary = sorted(
        term for term in getattr(reader, "term_to_postings", {}).keys()
        if isinstance(term, str)
    )
    if not vocabulary:
        return None

    vocab_set: Set[str] = set(vocabulary)

    suggested_tokens: List[str] = []
    changed = False

    for raw_token in raw_tokens:
        normalized = _normalize_single_term(raw_token, preprocessor)

        if not normalized:
            suggested_tokens.append(raw_token)
            continue

        if normalized in vocab_set:
            suggested_tokens.append(normalized)
            continue

        candidate = _get_spelling_candidate(normalized, vocabulary)
        if candidate:
            suggested_tokens.append(candidate)
            changed = True
        else:
            suggested_tokens.append(normalized)

    if not changed:
        return None

    suggestion = " ".join(suggested_tokens).strip()
    if not suggestion:
        return None

    if suggestion.lower() == query.strip().lower():
        return None

    return suggestion

