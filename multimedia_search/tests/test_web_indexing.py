import unittest
from unittest.mock import patch

from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.web.ingester import ingest_urls
from multimedia_search.web.url_utils import normalize_url


class TestUrlNormalization(unittest.TestCase):
    def test_normalize_root_url(self):
        self.assertEqual(
            normalize_url("https://EXAMPLE.com"),
            "https://example.com"
        )

    def test_remove_fragment(self):
        self.assertEqual(
            normalize_url("https://example.com/page#section1"),
            "https://example.com/page"
        )

    def test_remove_trailing_slash(self):
        self.assertEqual(
            normalize_url("https://example.com/page/"),
            "https://example.com/page"
        )

    def test_preserve_query_order(self):
        self.assertEqual(
            normalize_url("https://EXAMPLE.com/search?b=2&a=1#frag"),
            "https://example.com/search?b=2&a=1"
        )


class TestWebIngestion(unittest.TestCase):
    @patch("multimedia_search.web.ingester.extract")
    @patch("multimedia_search.web.ingester.fetch")
    def test_ingest_urls_skips_duplicate_inputs(self, mock_fetch, mock_extract):
        mock_fetch.return_value = "<html><title>Test</title><body>Hello world</body></html>"
        mock_extract.return_value = {"title": "Test", "text": "Hello world"}

        preprocessor = Preprocessor(stopwords=set(), use_stemming=False)

        docs = ingest_urls(
            [
                "https://EXAMPLE.com/page/",
                "https://example.com/page",
                "https://example.com/page#top",
            ],
            preprocessor,
        )

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].path, "https://example.com/page")
        self.assertGreater(len(docs[0].tokens), 0)


if __name__ == "__main__":
    unittest.main()
