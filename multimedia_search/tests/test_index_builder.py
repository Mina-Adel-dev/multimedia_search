import unittest
from pathlib import Path
from multimedia_search.core.document import Document
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.core.index import IndexBuilder

class TestIndexBuilder(unittest.TestCase):
    def setUp(self):
        self.preproc = Preprocessor()
        self.docs = [
            Document(0, Path("doc1.txt"), "txt", "python is great",
                     self.preproc.process("python is great")),
            Document(1, Path("doc2.txt"), "txt", "java is also great",
                     self.preproc.process("java is also great")),
            Document(2, Path("doc3.txt"), "txt", "python and java are both great",
                     self.preproc.process("python and java are both great")),
        ]
        self.builder = IndexBuilder()
        self.builder.build(self.docs)

    def test_term_to_postings_structure(self):
        postings = self.builder.term_to_postings.get("python", [])
        doc_ids = [doc_id for doc_id, _ in postings]
        self.assertIn(0, doc_ids)
        self.assertIn(2, doc_ids)
        self.assertNotIn(1, doc_ids)

    def test_postings_contain_positions(self):
        postings = self.builder.term_to_postings.get("python", [])
        for doc_id, positions in postings:
            if doc_id == 0:
                self.assertIn(0, positions)
                break
        else:
            self.fail("python not found in doc0")

    def test_idf_computation(self):
        idf_python = self.builder.idf.get("python", 0)
        idf_java = self.builder.idf.get("java", 0)
        self.assertGreater(idf_python, 0)
        self.assertAlmostEqual(idf_python, idf_java, places=5)

    def test_doc_norms_computed(self):
        for doc_id, meta in self.builder.doc_metadata.items():
            self.assertIn("norm", meta)
            self.assertGreater(meta["norm"], 0)