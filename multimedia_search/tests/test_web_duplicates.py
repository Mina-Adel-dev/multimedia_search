import unittest
import tempfile
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch

from multimedia_search import config
from multimedia_search.core.document import Document
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.cli.search_cli import handle_web_index


class TestWebDuplicates(unittest.TestCase):
    def setUp(self):
        # Temporary index file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_index = Path(self.temp_dir.name) / "test_index.pkl"
        self.original_index = config.INDEX_FILE
        config.INDEX_FILE = self.temp_index

    def tearDown(self):
        config.INDEX_FILE = self.original_index
        self.temp_dir.cleanup()

    @patch("multimedia_search.cli.search_cli.ingest_urls")
    def test_exact_duplicate_url_in_same_batch(self, mock_ingest):
        # Mock ingest_urls to return two identical Documents
        doc1 = Document(-1, "http://example.com", "html", "content", ["example"])
        doc2 = Document(-1, "http://example.com", "html", "content", ["example"])
        mock_ingest.return_value = [doc1, doc2]

        args = Namespace(urls=["http://example.com", "http://example.com"], debug=False)
        handle_web_index(args)

        # Load the index and verify only one document was added
        reader = IndexPersistence.load(config.INDEX_FILE)
        self.assertEqual(reader.get_doc_count(), 1)

        # Check that the stored path is normalized (should be same)
        meta = reader.get_doc_metadata(0)
        self.assertEqual(meta["path"], "http://example.com")

    @patch("multimedia_search.cli.search_cli.ingest_urls")
    def test_equivalent_url_variants_in_same_batch(self, mock_ingest):
        # Variants that normalize to the same
        urls = [
            "http://EXAMPLE.COM",
            "http://example.com/",
            "http://example.com#frag",
            "http://example.com:80",
        ]
        docs = [Document(-1, url, "html", f"content{i}", ["example"]) for i, url in enumerate(urls)]
        mock_ingest.return_value = docs

        args = Namespace(urls=urls, debug=False)
        handle_web_index(args)

        reader = IndexPersistence.load(config.INDEX_FILE)
        self.assertEqual(reader.get_doc_count(), 1)  # only one unique normalized URL
        meta = reader.get_doc_metadata(0)
        self.assertEqual(meta["path"], "http://example.com")

    @patch("multimedia_search.cli.search_cli.ingest_urls")
    def test_existing_url_skipped(self, mock_ingest):
        # First, add a document
        doc1 = Document(-1, "http://example.com", "html", "content", ["example"])
        mock_ingest.return_value = [doc1]
        args = Namespace(urls=["http://example.com"], debug=False)
        handle_web_index(args)

        # Now try to add the same URL again (different variant)
        doc2 = Document(-1, "http://EXAMPLE.COM/", "html", "new content", ["example"])
        mock_ingest.return_value = [doc2]
        handle_web_index(args)

        reader = IndexPersistence.load(config.INDEX_FILE)
        self.assertEqual(reader.get_doc_count(), 1)  # still one
        # Verify content unchanged (still old content)
        meta = reader.get_doc_metadata(0)
        self.assertEqual(meta["raw_text"], "content")  # original content

    @patch("multimedia_search.cli.search_cli.ingest_urls")
    def test_different_urls_kept(self, mock_ingest):
        docs = [
            Document(-1, "http://example.com", "html", "content1", ["example"]),
            Document(-1, "http://python.org", "html", "content2", ["python"]),
        ]
        mock_ingest.return_value = docs
        args = Namespace(urls=["http://example.com", "http://python.org"], debug=False)
        handle_web_index(args)

        reader = IndexPersistence.load(config.INDEX_FILE)
        self.assertEqual(reader.get_doc_count(), 2)
        paths = {meta["path"] for meta in reader.doc_metadata.values()}
        self.assertIn("http://example.com", paths)
        self.assertIn("http://python.org", paths)

if __name__ == "__main__":
    unittest.main()