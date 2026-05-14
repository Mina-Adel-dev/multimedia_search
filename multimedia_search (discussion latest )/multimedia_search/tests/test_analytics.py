import unittest
from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder, IndexReader
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.core.analytics import get_document_info, get_term_info


class TestAnalytics(unittest.TestCase):
    def setUp(self):
        # Create a small test index
        self.docs = [
            Document(
                doc_id=0,
                path="/test/doc1.txt",
                file_type="txt",
                raw_text="python is great python python",
                tokens=["python", "great", "python", "python"]  # after preprocessing (no stopwords)
            ),
            Document(
                doc_id=1,
                path="https://example.com",
                file_type="html",
                raw_text="example domain for illustrations",
                tokens=["example", "domain", "illustrations"]
            ),
        ]
        self.builder = IndexBuilder()
        self.builder.build(self.docs)
        self.reader = IndexReader(self.builder.get_data())
        self.preproc = Preprocessor(stopwords=set(), use_stemming=False)

    def test_document_info(self):
        info = get_document_info(0, self.reader, self.preproc, top_n=3)
        self.assertEqual(info["doc_id"], 0)
        self.assertEqual(info["path"], "/test/doc1.txt")
        self.assertEqual(info["source_type"], "txt")
        self.assertEqual(info["raw_word_count"], 5)  # "python is great python python" -> 5 words
        self.assertEqual(info["processed_token_count"], 4)
        self.assertEqual(info["unique_term_count"], 2)  # python, great
        top_terms = info["top_terms"]
        # python appears 3 times, great 1 time
        self.assertEqual(top_terms[0][0], "python")
        self.assertEqual(top_terms[0][1], 3)
        self.assertEqual(top_terms[1][0], "great")
        self.assertEqual(top_terms[1][1], 1)
        self.assertIn("python, great", info["focus_summary"])

    def test_term_info(self):
        info = get_term_info("python", self.reader, self.preproc)
        self.assertEqual(info["normalized_term"], "python")
        self.assertEqual(info["document_frequency"], 1)
        self.assertEqual(info["total_occurrences"], 3)
        self.assertEqual(len(info["per_document"]), 1)
        path, count = info["per_document"][0]
        self.assertEqual(path, "/test/doc1.txt")
        self.assertEqual(count, 3)

    def test_term_info_missing(self):
        info = get_term_info("nonexistent", self.reader, self.preproc)
        self.assertEqual(info["normalized_term"], "nonexistent")
        self.assertEqual(info["document_frequency"], 0)
        self.assertEqual(info["total_occurrences"], 0)
        self.assertEqual(info["per_document"], [])


if __name__ == "__main__":
    unittest.main()
