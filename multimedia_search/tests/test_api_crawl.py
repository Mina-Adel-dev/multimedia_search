import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import multimedia_search.config as config
from multimedia_search.db import database
import multimedia_search.webapp.app as webapp_module
import multimedia_search.webapp.services as services


class TestApiCrawl(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.temp_index = self.root / "test_index.pkl"
        self.temp_database = self.root / "test_api.sqlite3"

        self.original_config_index = config.INDEX_FILE
        self.original_services_index = services.INDEX_FILE
        self.original_config_database = config.DATABASE_FILE
        self.original_database_file = database.DATABASE_FILE

        config.INDEX_FILE = self.temp_index
        services.INDEX_FILE = self.temp_index
        config.DATABASE_FILE = self.temp_database
        database.DATABASE_FILE = self.temp_database

        webapp_module.app.testing = True
        self.client = webapp_module.app.test_client()

    def tearDown(self):
        config.INDEX_FILE = self.original_config_index
        services.INDEX_FILE = self.original_services_index
        config.DATABASE_FILE = self.original_config_database
        database.DATABASE_FILE = self.original_database_file
        self.temp_dir.cleanup()

    @patch("multimedia_search.webapp.app.services.crawl_and_index_web")
    def test_api_crawl_web_calls_service_and_tracks_sources(self, mock_crawl):
        mock_crawl.return_value = (
            True,
            "Crawled 2 page(s). Added 2 new web page(s).",
            2,
            {
                "discovered_urls": [
                    "https://example.com",
                    "https://example.com/about",
                ],
                "visited_count": 2,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            },
        )

        response = self.client.post(
            "/api/crawl/web",
            json={
                "seed_urls": ["https://example.com"],
                "max_pages": 2,
                "max_depth": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["indexed_count"], 2)
        self.assertEqual(payload["crawl"]["visited_count"], 2)
        mock_crawl.assert_called_once()

        sources_response = self.client.get("/api/sources")
        sources_payload = sources_response.get_json()
        source_types = {source["source_type"] for source in sources_payload["sources"]}
        self.assertIn("web_crawl", source_types)
        self.assertIn("web_url", source_types)

    def test_api_crawl_web_requires_seed_urls(self):
        response = self.client.post("/api/crawl/web", json={})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertIn("seed_urls", payload["error"])


if __name__ == "__main__":
    unittest.main()