import unittest

from multimedia_search.web.crawler import crawl_urls, extract_links


class TestWebCrawler(unittest.TestCase):
    def test_extract_links_normalizes_and_filters_non_pages(self):
        html = """
        <a href="/about/">About</a>
        <a href="https://example.com/file.pdf">PDF</a>
        <a href="mailto:test@example.com">Email</a>
        <a href="#local">Fragment</a>
        """

        links = extract_links(html, "https://example.com/start")

        self.assertIn("https://example.com/about", links)
        self.assertIn("https://example.com/start", links)
        self.assertNotIn("https://example.com/file.pdf", links)

    def test_crawl_urls_discovers_same_domain_pages_by_depth(self):
        pages = {
            "https://example.com": """
                <a href="/a">A</a>
                <a href="https://other.com/out">Out</a>
            """,
            "https://example.com/a": '<a href="/b">B</a>',
            "https://example.com/b": "<p>Done</p>",
        }

        def fake_fetch(url):
            return pages.get(url)

        result = crawl_urls(
            ["https://example.com"],
            max_pages=10,
            max_depth=2,
            same_domain=True,
            respect_robots=False,
            fetcher=fake_fetch,
        )

        self.assertEqual(
            result.urls,
            [
                "https://example.com",
                "https://example.com/a",
                "https://example.com/b",
            ],
        )
        self.assertGreaterEqual(result.skipped_count, 1)

    def test_crawl_urls_respects_max_pages(self):
        html = "".join(f'<a href="/p{i}">P{i}</a>' for i in range(20))

        def fake_fetch(url):
            return html

        result = crawl_urls(
            ["https://example.com"],
            max_pages=3,
            max_depth=1,
            respect_robots=False,
            fetcher=fake_fetch,
        )

        self.assertEqual(len(result.urls), 3)


if __name__ == "__main__":
    unittest.main()