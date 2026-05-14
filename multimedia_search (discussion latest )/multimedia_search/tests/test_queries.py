import unittest

from multimedia_search.core.boolean import BooleanQueryError, BooleanRetriever
from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder, IndexReader
from multimedia_search.core.phrase import PhraseSearcher
from multimedia_search.core.preprocessor import Preprocessor


class QueryTestBase(unittest.TestCase):
    def setUp(self):
        self.preprocessor = Preprocessor(stopwords=set(), use_stemming=False)

        docs = [
            Document(0, "doc1.txt", "txt", "python search engine", ["python", "search", "engine"]),
            Document(1, "doc2.txt", "txt", "java search system", ["java", "search", "system"]),
            Document(2, "doc3.txt", "txt", "python and java together", ["python", "and", "java", "together"]),
            Document(3, "doc4.txt", "txt", "exact phrase match here", ["exact", "phrase", "match", "here"]),
        ]

        builder = IndexBuilder()
        builder.build(docs)
        self.reader = IndexReader(builder.get_data())


class TestBooleanQueries(QueryTestBase):
    def test_valid_boolean_and(self):
        retriever = BooleanRetriever(self.reader, self.preprocessor)
        results = retriever.evaluate("python AND search")
        self.assertEqual(results, {0})

    def test_valid_boolean_or(self):
        retriever = BooleanRetriever(self.reader, self.preprocessor)
        results = retriever.evaluate("python OR java")
        self.assertEqual(results, {0, 1, 2})

    def test_valid_boolean_not(self):
        retriever = BooleanRetriever(self.reader, self.preprocessor)
        results = retriever.evaluate("python AND NOT java")
        self.assertEqual(results, {0})

    def test_empty_boolean_query_raises(self):
        retriever = BooleanRetriever(self.reader, self.preprocessor)
        with self.assertRaises(BooleanQueryError):
            retriever.evaluate("")

    def test_boolean_query_ending_with_operator_raises(self):
        retriever = BooleanRetriever(self.reader, self.preprocessor)
        with self.assertRaises(BooleanQueryError):
            retriever.evaluate("python AND")

    def test_boolean_query_with_unmatched_parenthesis_raises(self):
        retriever = BooleanRetriever(self.reader, self.preprocessor)
        with self.assertRaises(BooleanQueryError):
            retriever.evaluate("( python AND java")

    def test_boolean_query_with_missing_operator_raises(self):
        retriever = BooleanRetriever(self.reader, self.preprocessor)
        with self.assertRaises(BooleanQueryError):
            retriever.evaluate("python java")

    def test_boolean_query_with_empty_parentheses_raises(self):
        retriever = BooleanRetriever(self.reader, self.preprocessor)
        with self.assertRaises(BooleanQueryError):
            retriever.evaluate("python AND ()")


class TestPhraseQueries(QueryTestBase):
    def test_phrase_search_match(self):
        searcher = PhraseSearcher(self.reader, self.preprocessor)
        results = searcher.search("exact phrase")
        self.assertEqual(results, {3})

    def test_phrase_search_no_match(self):
        searcher = PhraseSearcher(self.reader, self.preprocessor)
        results = searcher.search("phrase exact")
        self.assertEqual(results, set())

    def test_phrase_search_empty_string(self):
        searcher = PhraseSearcher(self.reader, self.preprocessor)
        results = searcher.search("")
        self.assertEqual(results, set())

    def test_phrase_search_single_term(self):
        searcher = PhraseSearcher(self.reader, self.preprocessor)
        results = searcher.search("python")
        self.assertEqual(results, {0, 2})
