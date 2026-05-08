import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

import multimedia_search.config as config
import multimedia_search.webapp.app as webapp_module
import multimedia_search.webapp.services as services
from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder
from multimedia_search.core.persistence import IndexPersistence


class TestWebAppSimilarImage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.temp_index = self.root / "test_index.pkl"

        self.original_config_index = config.INDEX_FILE
        self.original_services_index = services.INDEX_FILE

        config.INDEX_FILE = self.temp_index
        services.INDEX_FILE = self.temp_index

        webapp_module.app.testing = True
        self.client = webapp_module.app.test_client()

    def tearDown(self):
        config.INDEX_FILE = self.original_config_index
        services.INDEX_FILE = self.original_services_index
        self.temp_dir.cleanup()

    def _make_image(self, path: Path, color: str, image_format: str = "PNG") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 64), color=color).save(path, format=image_format)

    def _make_image_upload(self, color: str) -> BytesIO:
        image_bytes = BytesIO()
        Image.new("RGB", (64, 64), color=color).save(image_bytes, format="PNG")
        image_bytes.seek(0)
        return image_bytes

    def _save_indexed_images(self, paths: list[Path]) -> None:
        docs = []

        for doc_id, path in enumerate(paths):
            docs.append(
                Document(
                    doc_id=doc_id,
                    path=str(path.resolve()),
                    file_type=path.suffix.lstrip(".").lower(),
                    raw_text=path.stem,
                    tokens=[path.stem],
                )
            )

        builder = IndexBuilder()
        builder.build(docs)
        IndexPersistence.save(builder, services.INDEX_FILE)

    def test_service_similar_image_search_returns_indexed_image(self):
        query_image = self.root / "query_red.png"
        red_candidate = self.root / "candidate_red.png"
        blue_candidate = self.root / "candidate_blue.png"

        self._make_image(query_image, "red")
        self._make_image(red_candidate, "red")
        self._make_image(blue_candidate, "blue")
        self._save_indexed_images([blue_candidate, red_candidate])

        results, error = services.search_similar_images(str(query_image), top_k=2)

        self.assertEqual(error, "")
        self.assertIsNotNone(results)
        self.assertEqual(results[0]["path"], str(red_candidate.resolve()))
        self.assertGreater(results[0]["score"], results[1]["score"])

    def test_route_similar_image_search_renders_result(self):
        query_image = self.root / "query_red.png"
        red_candidate = self.root / "candidate_red.png"

        self._make_image(query_image, "red")
        self._make_image(red_candidate, "red")
        self._save_indexed_images([red_candidate])

        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_path": str(query_image),
                "similar_top_k": "5",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Similar Image Results", response.data)
        self.assertIn(str(red_candidate.resolve()).encode(), response.data)
        self.assertIn(b"Similarity:", response.data)
        self.assertIn(b"Visual feature match", response.data)
        self.assertIn(b"lightweight visual similarity", response.data)

    def test_route_similar_image_search_empty_path(self):
        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_path": "",
                "similar_top_k": "5",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Please provide an image path or upload an image.",
            response.data,
        )

    def test_route_similar_image_search_accepts_uploaded_query_image(self):
        red_candidate = self.root / "candidate_red.png"
        blue_candidate = self.root / "candidate_blue.png"

        self._make_image(red_candidate, "red")
        self._make_image(blue_candidate, "blue")
        self._save_indexed_images([blue_candidate, red_candidate])

        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_file": (
                    self._make_image_upload("red"),
                    "query_red.png",
                ),
                "similar_top_k": "5",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Similar Image Results", response.data)
        self.assertIn(str(red_candidate.resolve()).encode(), response.data)
        self.assertIn(b"Similarity:", response.data)
        self.assertIn(b"Selected upload preview", response.data)
        self.assertIn(b"query-image-preview-img", response.data)

    def test_route_similar_image_search_rejects_unsupported_upload_extension(self):
        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_file": (
                    BytesIO(b"not really an image"),
                    "query.gif",
                ),
                "similar_top_k": "5",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Uploaded query image must be jpg, jpeg, png, or webp.",
            response.data,
        )
        self.assertNotIn(b"Similar Image Results", response.data)

    def test_route_similar_image_upload_cleans_temp_query_file(self):
        red_candidate = self.root / "candidate_red.png"

        self._make_image(red_candidate, "red")
        self._save_indexed_images([red_candidate])

        upload_dir = Path(tempfile.gettempdir()) / "multimedia_search_query_uploads"
        before_files = set(upload_dir.iterdir()) if upload_dir.exists() else set()

        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_file": (
                    self._make_image_upload("red"),
                    "query_red.png",
                ),
                "similar_top_k": "5",
            },
            content_type="multipart/form-data",
        )

        after_files = set(upload_dir.iterdir()) if upload_dir.exists() else set()

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Similar Image Results", response.data)
        self.assertEqual(before_files, after_files)

    def test_route_similar_image_search_rejects_fake_uploaded_image_content(self):
        red_candidate = self.root / "candidate_red.png"

        self._make_image(red_candidate, "red")
        self._save_indexed_images([red_candidate])

        upload_dir = Path(tempfile.gettempdir()) / "multimedia_search_query_uploads"
        before_files = set(upload_dir.iterdir()) if upload_dir.exists() else set()

        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_file": (
                    BytesIO(b"not really an image"),
                    "fake_query.png",
                ),
                "similar_top_k": "5",
            },
            content_type="multipart/form-data",
        )

        after_files = set(upload_dir.iterdir()) if upload_dir.exists() else set()

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid or unreadable image file", response.data)
        self.assertNotIn(b"Similar Image Results", response.data)
        self.assertEqual(before_files, after_files)

    def test_route_similar_image_search_no_index_found(self):
        query_image = self.root / "query_red.png"
        self._make_image(query_image, "red")

        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_path": str(query_image),
                "similar_top_k": "5",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No index found.", response.data)
        self.assertNotIn(b"Similar Image Results", response.data)

    def test_route_similar_image_search_missing_query_image_path(self):
        red_candidate = self.root / "candidate_red.png"
        missing_query = self.root / "missing_query.png"

        self._make_image(red_candidate, "red")
        self._save_indexed_images([red_candidate])

        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_path": str(missing_query),
                "similar_top_k": "5",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Image file not found", response.data)
        self.assertNotIn(b"Similar Image Results", response.data)

    def test_route_similar_image_search_invalid_top_k_defaults_safely(self):
        query_image = self.root / "query_red.png"
        red_candidate = self.root / "candidate_red.png"

        self._make_image(query_image, "red")
        self._make_image(red_candidate, "red")
        self._save_indexed_images([red_candidate])

        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_path": str(query_image),
                "similar_top_k": "not-a-number",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Similar Image Results", response.data)
        self.assertIn(str(red_candidate.resolve()).encode(), response.data)

    def test_route_similar_image_search_zero_top_k_defaults_safely(self):
        query_image = self.root / "query_red.png"
        red_candidate = self.root / "candidate_red.png"

        self._make_image(query_image, "red")
        self._make_image(red_candidate, "red")
        self._save_indexed_images([red_candidate])

        response = self.client.post(
            "/",
            data={
                "action": "similar_image",
                "similar_image_path": str(query_image),
                "similar_top_k": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Similar Image Results", response.data)
        self.assertIn(str(red_candidate.resolve()).encode(), response.data)

    def test_route_renders_similar_image_ui_help_text(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Query by Image", response.data)
        self.assertIn(b"average color", response.data)
        self.assertIn(b"Not semantic AI matching", response.data)
        self.assertIn(b"query-image-preview", response.data)


if __name__ == "__main__":
    unittest.main()