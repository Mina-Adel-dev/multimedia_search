import unittest
from pathlib import Path
from unittest.mock import patch

from multimedia_search.core.document import Document
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.core.index import IndexBuilder, IndexReader
from multimedia_search.core.boolean import BooleanRetriever
from multimedia_search.core.phrase import PhraseSearcher
from multimedia_search.core.retrieval import RankedRetriever


class TestRetrievalCorrectness(unittest.TestCase):
    """Validate retrieval logic with a controlled mini-corpus."""

    def setUp(self):
        self.docs = [
            Document(0, Path("/dummy/doc0.txt"), "txt", "dummy raw",
                     tokens=["python", "programming", "language"]),
            Document(1, Path("/dummy/doc1.txt"), "txt", "dummy raw",
                     tokens=["java", "programming", "language"]),
            Document(2, Path("/dummy/doc2.txt"), "txt", "dummy raw",
                     tokens=["python", "machine", "learning"]),
            Document(3, Path("/dummy/doc3.txt"), "txt", "dummy raw",
                     tokens=["java", "machine", "learning"]),
            Document(4, Path("/dummy/doc4.txt"), "txt", "dummy raw",
                     tokens=["python", "java", "both"]),
            Document(5, Path("/dummy/doc5.txt"), "txt", "machine learning is fun",
                     tokens=["machine", "learning", "is", "fun"]),
            Document(6, Path("/dummy/doc6.txt"), "txt", "learning machine is confusing",
                     tokens=["learning", "machine", "is", "confusing"]),
        ]

        self.builder = IndexBuilder()
        self.builder.build(self.docs)
        self.reader = IndexReader(self.builder.get_data())
        self.preproc = Preprocessor(stopwords=set(), use_stemming=False)

    # ---------- Basic postings tests ----------
    def test_term_postings(self):
        """Known term should contain correct document IDs."""
        python_docs = {doc_id for doc_id, _ in self.reader.get_postings("python")}
        self.assertEqual(python_docs, {0, 2, 4})

        java_docs = {doc_id for doc_id, _ in self.reader.get_postings("java")}
        self.assertEqual(java_docs, {1, 3, 4})

    def test_positional_postings(self):
        """Positions stored correctly for a known document."""
        postings_machine = self.reader.get_postings("machine")
        for doc_id, positions in postings_machine:
            if doc_id == 5:
                self.assertEqual(positions, [0])
                break
        else:
            self.fail("doc5 not found for term 'machine'")

        postings_learning = self.reader.get_postings("learning")
        for doc_id, positions in postings_learning:
            if doc_id == 5:
                self.assertEqual(positions, [1])
                break
        else:
            self.fail("doc5 not found for term 'learning'")

    # ---------- Boolean tests ----------
    def test_boolean_and(self):
        retriever = BooleanRetriever(self.reader, self.preproc)
        result = retriever.evaluate("python AND java")
        self.assertEqual(result, {4})

    def test_boolean_or(self):
        retriever = BooleanRetriever(self.reader, self.preproc)
        result = retriever.evaluate("python OR java")
        self.assertEqual(result, {0, 1, 2, 3, 4})

    def test_boolean_not(self):
        retriever = BooleanRetriever(self.reader, self.preproc)
        result = retriever.evaluate("python AND NOT java")
        self.assertEqual(result, {0, 2})

    def test_boolean_parentheses(self):
        retriever = BooleanRetriever(self.reader, self.preproc)
        result = retriever.evaluate("(python OR java) AND NOT both")
        self.assertEqual(result, {0, 1, 2, 3})

    # ---------- Phrase tests ----------
    def test_phrase_match(self):
        searcher = PhraseSearcher(self.reader, self.preproc)
        result = searcher.search("machine learning")
        self.assertEqual(result, {2, 3, 5})

    def test_phrase_no_match(self):
        searcher = PhraseSearcher(self.reader, self.preproc)
        result = searcher.search("machine learning")
        self.assertNotIn(6, result)

    # ---------- Ranked retrieval tests ----------
    @patch.object(RankedRetriever, "_read_file", return_value="dummy snippet text")
    def test_ranked_ordering(self, mock_read):
        """Verify that the best matching document is ranked first."""
        retriever = RankedRetriever(self.reader, self.preproc)
        results = retriever.search("python programming", top_k=5)

        doc_ids = [r[0] for r in results]

        self.assertGreater(len(doc_ids), 0)
        self.assertEqual(doc_ids[0], 0)

        returned_set = set(doc_ids[:4])
        self.assertIn(2, returned_set)
        self.assertIn(4, returned_set)
        self.assertIn(1, returned_set)

        self.assertGreater(results[0][1], results[1][1])
