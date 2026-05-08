import unittest
from pathlib import Path
from multimedia_search.core.document import Document
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.core.index import IndexBuilder

class TestPositionalIndex(unittest.TestCase):
    def setUp(self):
        self.preproc = Preprocessor()
        text = "python is python and python is great"
        tokens = self.preproc.process(text)  # stopwords removed → ["python","python","python","great"]
        self.doc = Document(0, Path("doc.txt"), "txt", text, tokens)
        self.builder = IndexBuilder()
        self.builder.build([self.doc])

    def test_positions_are_correct(self):
        postings = self.builder.term_to_postings.get("python", [])
        self.assertEqual(len(postings), 1)
        doc_id, positions = postings[0]
        self.assertEqual(doc_id, 0)
        self.assertEqual(positions, [0, 1, 2])   # after stopword removal, three consecutive positions