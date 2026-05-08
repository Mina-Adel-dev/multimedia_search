"""Ranked retrieval using tf-idf cosine similarity."""

from collections import defaultdict
from typing import List, Tuple

from multimedia_search.core.index import IndexReader
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.core.snippet import SnippetGenerator


class RankedRetriever:
    """Perform ranked search using cosine similarity."""

    def __init__(self, index_reader: IndexReader, preprocessor: Preprocessor):
        self.index = index_reader
        self.preprocessor = preprocessor
        self.snippet_gen = SnippetGenerator()

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float, str, str, List[str]]]:
        """
        Execute ranked query and return results with snippets.

        Returns:
            List of tuples (doc_id, score, file_path, snippet, matched_terms)
        """
        query_tokens = self.preprocessor.process(query)
        if not query_tokens:
            return []

        qtf = {}
        for token in query_tokens:
            qtf[token] = qtf.get(token, 0) + 1

        query_weights = {}
        candidate_docs = set()
        for term, tf in qtf.items():
            idf = self.index.get_idf(term)
            if idf == 0:
                continue
            query_weights[term] = tf * idf
            for doc_id, _ in self.index.get_postings(term):
                candidate_docs.add(doc_id)

        if not candidate_docs:
            return []

        scores = {}
        matched_terms_per_doc = defaultdict(list)

        for doc_id in candidate_docs:
            score = 0.0
            for term, qw in query_weights.items():
                postings = self.index.get_postings(term)
                for d_id, positions in postings:
                    if d_id == doc_id:
                        tf = len(positions)
                        doc_weight = tf * self.index.get_idf(term)
                        score += qw * doc_weight
                        matched_terms_per_doc[doc_id].append(term)
                        break

            norm = self.index.get_doc_metadata(doc_id).get("norm", 1.0)
            if norm > 0:
                score /= norm
            scores[doc_id] = score

        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Deduplicate by path/URL so duplicate indexed copies do not appear.
        seen_paths = set()
        results = []

        for doc_id, score in sorted_docs:
            meta = self.index.get_doc_metadata(doc_id)
            path = meta.get("path", "")
            if path in seen_paths:
                continue
            seen_paths.add(path)

            raw_text = meta.get("raw_text", "") or self._read_file(path)
            matched = list(dict.fromkeys(matched_terms_per_doc[doc_id]))
            snippet = self.snippet_gen.generate(raw_text, matched)
            results.append((doc_id, score, path, snippet, matched))

            if len(results) >= top_k:
                break

        return results

    def _read_file(self, path: str) -> str:
        """Fallback to read raw text for snippet generation."""
        if path.startswith("http://") or path.startswith("https://"):
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return ""
