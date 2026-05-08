"""Index building and reading."""

import math
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from multimedia_search.core.document import Document


class IndexBuilder:
    """Builds inverted index, positional index, and computes tf-idf norms."""

    def __init__(self):
        self.term_to_postings: Dict[str, List[Tuple[int, List[int]]]] = defaultdict(list)
        self.doc_metadata: Dict[int, Dict] = {}
        self.idf: Dict[str, float] = {}
        self.doc_count: int = 0

    @classmethod
    def from_existing(cls, data: dict) -> 'IndexBuilder':
        """Create an IndexBuilder instance from previously saved data."""
        builder = cls()
        builder.doc_metadata = data["doc_metadata"]
        builder.term_to_postings = defaultdict(list, data["term_to_postings"])
        builder.idf = data["idf"]
        builder.doc_count = data["doc_count"]
        return builder

    def build(self, docs: List[Document]) -> None:
        """
        Build all index structures from a list of Documents.
        Assumes each Document has its tokens already set.
        """
        self.term_to_postings = defaultdict(list)
        self.doc_metadata = {}
        self.idf = {}
        self.doc_count = len(docs)
    
        for doc in docs:
            doc_id = doc.doc_id
            self.doc_metadata[doc_id] = {
                "path": str(doc.path),
                "file_type": doc.file_type,
                "num_tokens": len(doc.tokens),
                "norm": 0.0,
                "raw_text": doc.raw_text,
            }
    
            for pos, term in enumerate(doc.tokens):
                postings = self.term_to_postings[term]
                if postings and postings[-1][0] == doc_id:
                    postings[-1][1].append(pos)
                else:
                    postings.append((doc_id, [pos]))
    
        self._compute_idf()
        self._compute_doc_norms()

    def add_documents(self, docs: List[Document]) -> None:
        """
        Add new documents to the index and recompute idf and norms.
        Assumes doc_ids are already assigned and sequential.
        """
        for doc in docs:
            doc_id = doc.doc_id
            self.doc_metadata[doc_id] = {
                "path": str(doc.path),
                "file_type": doc.file_type,
                "num_tokens": len(doc.tokens),
                "norm": 0.0,
                "raw_text": doc.raw_text,          # <-- added
            }
            for pos, term in enumerate(doc.tokens):
                postings = self.term_to_postings[term]
                if postings and postings[-1][0] == doc_id:
                    postings[-1][1].append(pos)
                else:
                    postings.append((doc_id, [pos]))

        self.doc_count = len(self.doc_metadata)
        self._compute_idf()
        self._compute_doc_norms()

    def _compute_idf(self) -> None:
        """Compute inverse document frequency for each term."""
        n_docs = self.doc_count
        for term, postings in self.term_to_postings.items():
            df = len(postings)
            self.idf[term] = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)

    def _compute_doc_norms(self) -> None:
        """Compute Euclidean norm of tf-idf vector for each document."""
        for doc_id in self.doc_metadata:
            self.doc_metadata[doc_id]["norm"] = 0.0

        for term, postings in self.term_to_postings.items():
            idf = self.idf[term]
            for doc_id, positions in postings:
                tf = len(positions)
                weight = tf * idf
                self.doc_metadata[doc_id]["norm"] += weight * weight

        for doc_id in self.doc_metadata:
            self.doc_metadata[doc_id]["norm"] = math.sqrt(self.doc_metadata[doc_id]["norm"])

    def get_data(self) -> dict:
        """Return all index data for persistence."""
        return {
            "version": "1.0",
            "doc_metadata": self.doc_metadata,
            "term_to_postings": dict(self.term_to_postings),
            "idf": self.idf,
            "doc_count": self.doc_count,
        }


class IndexReader:
    """Read-only interface to the index."""

    def __init__(self, data: dict):
        self.doc_metadata = data["doc_metadata"]
        self.term_to_postings = data["term_to_postings"]
        self.idf = data["idf"]
        self.doc_count = data["doc_count"]

    def get_postings(self, term: str) -> List[Tuple[int, List[int]]]:
        """Return list of (doc_id, positions) for the term."""
        return self.term_to_postings.get(term, [])

    def get_doc_metadata(self, doc_id: int) -> dict:
        """Return metadata for one document."""
        return self.doc_metadata.get(doc_id, {})

    def get_idf(self, term: str) -> float:
        """Return idf for a term, or 0.0 if missing."""
        return self.idf.get(term, 0.0)

    def get_doc_count(self) -> int:
        """Return total number of indexed documents."""
        return self.doc_count

    def get_term_docids(self, term: str) -> Set[int]:
        """Return doc IDs containing the term."""
        return {doc_id for doc_id, _ in self.get_postings(term)}

    def get_data(self) -> dict:
        """Return the raw index data (for rebuilding)."""
        return {
            "doc_metadata": self.doc_metadata,
            "term_to_postings": self.term_to_postings,
            "idf": self.idf,
            "doc_count": self.doc_count,
        }