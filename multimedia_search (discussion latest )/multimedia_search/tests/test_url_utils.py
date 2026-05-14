import unittest
from multimedia_search.web.url_utils import normalize_url


class TestUrlNormalization(unittest.TestCase):

    def test_lowercase_scheme_and_host(self):
        self.assertEqual(normalize_url("HTTP://EXAMPLE.COM"), "http://example.com")
        self.assertEqual(normalize_url("https://EXAMPLE.COM"), "https://example.com")

    def test_remove_default_ports(self):
        self.assertEqual(normalize_url("http://example.com:80"), "http://example.com")
        self.assertEqual(normalize_url("https://example.com:443"), "https://example.com")
        self.assertEqual(normalize_url("http://example.com:8080"), "http://example.com:8080")

    def test_remove_fragment(self):
        self.assertEqual(normalize_url("https://example.com/page#section"), "https://example.com/page")
        self.assertEqual(normalize_url("https://example.com/#top"), "https://example.com")

    def test_trailing_slash_normalization(self):
        self.assertEqual(normalize_url("https://example.com/"), "https://example.com")
        self.assertEqual(normalize_url("https://example.com/page/"), "https://example.com/page")
        self.assertEqual(normalize_url("https://example.com/page"), "https://example.com/page")

    def test_combined_equivalence(self):
        variants = [
            "https://EXAMPLE.COM",
            "https://example.com/",
            "https://example.com#frag",
            "https://example.com:443",
            "https://example.com/#frag",
        ]
        canonical = "https://example.com"
        for value in variants:
            self.assertEqual(normalize_url(value), canonical)

    def test_query_string_preserved(self):
        self.assertEqual(
            normalize_url("https://example.com/search?q=test"),
            "https://example.com/search?q=test",
        )
        self.assertEqual(
            normalize_url("https://example.com/?q=test"),
            "https://example.com?q=test",
        )

    def test_empty_url(self):
        self.assertEqual(normalize_url(""), "")


if __name__ == "__main__":
    unittest.main()
