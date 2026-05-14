import unittest
import tempfile
from pathlib import Path

from multimedia_search.core.boolean import BooleanRetriever, BooleanQueryError
from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.core.preprocessor import Preprocessor


class TestBooleanMalformed(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.index_file = self.root / "test_boolean_index.pkl"

        preprocessor = Preprocessor()

        docs = [
            Document(
                doc_id=0,
                path="doc1.txt",
                file_type="txt",
                raw_text="cat dog",
                tokens=preprocessor.process("cat dog"),
            ),
            Document(
                doc_id=1,
                path="doc2.txt",
                file_type="txt",
                raw_text="dog fish",
                tokens=preprocessor.process("dog fish"),
            ),
        ]

        builder = IndexBuilder()
        builder.build(docs)
        IndexPersistence.save(builder, self.index_file)

        reader = IndexPersistence.load(self.index_file)
        self.retriever = BooleanRetriever(reader, preprocessor)

    def tearDown(self):
        self.temp_dir.cleanup()

    def assert_raises_boolean_error(self, query: str):
        with self.assertRaises(BooleanQueryError):
            self.retriever.evaluate(query)

    def test_empty_query(self):
        self.assert_raises_boolean_error("")

    def test_whitespace_query(self):
        self.assert_raises_boolean_error("   ")

    def test_trailing_operator(self):
        self.assert_raises_boolean_error("cat AND")

    def test_leading_binary_operator(self):
        self.assert_raises_boolean_error("AND cat")
        self.assert_raises_boolean_error("OR cat")

    def test_leading_not_is_valid(self):
        result = self.retriever.evaluate("NOT cat")
        self.assertIsInstance(result, set)

    def test_repeated_operators(self):
        self.assert_raises_boolean_error("cat AND OR dog")

    def test_unmatched_open_paren(self):
        self.assert_raises_boolean_error("(cat AND dog")

    def test_unmatched_close_paren(self):
        self.assert_raises_boolean_error("cat AND dog)")

    def test_operator_only_input(self):
        self.assert_raises_boolean_error("NOT")
        self.assert_raises_boolean_error("AND OR")

    def test_valid_boolean_query_still_works(self):
        result = self.retriever.evaluate("cat AND dog")
        self.assertEqual(result, {0})


if __name__ == "__main__":
    unittest.main()
