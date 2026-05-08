"""Analytics for documents and terms."""

from collections import Counter
from typing import Dict, List, Tuple, Optional

from multimedia_search.core.index import IndexReader
from multimedia_search.core.preprocessor import Preprocessor


def get_document_info(
    doc_id: int,
    reader: IndexReader,
    preprocessor: Preprocessor,
    top_n: int = 10
) -> Dict:
    """
    Return detailed analytics for a single document.

    Args:
        doc_id: document identifier.
        reader: IndexReader instance.
        preprocessor: Preprocessor for token normalization.
        top_n: number of top frequent terms to return.

    Returns:
        Dictionary with keys:
            doc_id, path, source_type, raw_word_count, processed_token_count,
            unique_term_count, top_terms (list of (term, count)), focus_summary.
    """
    meta = reader.get_doc_metadata(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found.")

    path = meta.get("path", "")
    file_type = meta.get("file_type", "")
    raw_text = meta.get("raw_text", "")
    processed_token_count = meta.get("num_tokens", 0)

    # Raw word count: split raw_text by whitespace (simple estimate)
    raw_word_count = len(raw_text.split()) if raw_text else 0

    # Compute term frequencies for this document from the index
    term_freq = Counter()
    for term, postings in reader.term_to_postings.items():
        for d_id, positions in postings:
            if d_id == doc_id:
                term_freq[term] = len(positions)
                break

    unique_term_count = len(term_freq)

    # Get top terms
    top_terms = term_freq.most_common(top_n)

    # Generate focus summary
    if top_terms:
        focus_words = [term for term, _ in top_terms[:5]]
        focus_summary = f"This document mainly focuses on: {', '.join(focus_words)}."
    else:
        focus_summary = "No terms found."

    return {
        "doc_id": doc_id,
        "path": path,
        "source_type": file_type,
        "raw_word_count": raw_word_count,
        "processed_token_count": processed_token_count,
        "unique_term_count": unique_term_count,
        "top_terms": top_terms,
        "focus_summary": focus_summary,
    }


def get_term_info(
    term: str,
    reader: IndexReader,
    preprocessor: Preprocessor
) -> Dict:
    """
    Return detailed statistics for a single term.

    Args:
        term: raw query term (will be preprocessed).
        reader: IndexReader instance.
        preprocessor: Preprocessor for normalizing the term.

    Returns:
        Dictionary with keys:
            normalized_term, document_frequency, total_occurrences,
            per_document (list of (path, count)).
    """
    # Normalize term using the same pipeline as indexing
    normalized = preprocessor.process(term)
    if not normalized:
        raise ValueError(f"Term '{term}' produced no normalized tokens.")
    # Use the first token (Boolean queries use single terms)
    norm_term = normalized[0]

    postings = reader.get_postings(norm_term)
    df = len(postings)
    total_occurrences = sum(len(positions) for _, positions in postings)

    per_doc = []
    for doc_id, positions in postings:
        meta = reader.get_doc_metadata(doc_id)
        path = meta.get("path", f"doc_{doc_id}")
        count = len(positions)
        per_doc.append((path, count))

    return {
        "normalized_term": norm_term,
        "document_frequency": df,
        "total_occurrences": total_occurrences,
        "per_document": per_doc,
    }