import tempfile
import unittest
from pathlib import Path

from PIL import Image
from multimedia_search.core.preprocessor import Preprocessor

import multimedia_search.config as config
import multimedia_search.webapp.app as webapp_module
import multimedia_search.webapp.services as services

from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder
from multimedia_search.core.persistence import IndexPersistence


class TestWebApp(unittest.TestCase):
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

    def _make_image(self, path: Path, image_format: str, size=(100, 60), color="blue") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", size, color=color)
        img.save(path, format=image_format)

    def _post_search(self, query: str, top_k: str = "10", image_only: bool = False):
        data = {
            "action": "search",
            "query": query,
            "top_k": top_k,
        }
        if image_only:
            data["image_only"] = "1"
        return self.client.post("/", data=data)

    def _post_index_local(self, directory: Path):
        return self.client.post(
            "/",
            data={
                "action": "index_local",
                "directory": str(directory),
            },
        )

    # ---------- Stats tests ----------
    def test_get_index_stats_no_index(self):
        stats = services.get_index_stats()
        self.assertEqual(stats["total_docs"], 0)
        self.assertEqual(stats["local_files"], 0)
        self.assertEqual(stats["web_pages"], 0)

    def test_get_index_stats_with_docs(self):
        docs = [
            Document(
                doc_id=0,
                path="/fake/local/file.txt",
                file_type="txt",
                raw_text="test",
                tokens=["test"],
            ),
            Document(
                doc_id=1,
                path="https://example.com",
                file_type="html",
                raw_text="example",
                tokens=["example"],
            ),
        ]
        builder = IndexBuilder()
        builder.build(docs)
        IndexPersistence.save(builder, services.INDEX_FILE)

        stats = services.get_index_stats()
        self.assertEqual(stats["total_docs"], 2)
        self.assertEqual(stats["local_files"], 1)
        self.assertEqual(stats["web_pages"], 1)

    # ---------- Reset index tests ----------
    def test_reset_index_deletes_file(self):
        docs = [
            Document(
                doc_id=0,
                path="/fake/path.txt",
                file_type="txt",
                raw_text="test",
                tokens=["test"],
            )
        ]
        builder = IndexBuilder()
        builder.build(docs)
        IndexPersistence.save(builder, services.INDEX_FILE)

        self.assertTrue(services.INDEX_FILE.exists())

        success, msg = services.reset_index()
        self.assertTrue(success)
        self.assertFalse(services.INDEX_FILE.exists())
        self.assertIn("index", msg.lower())
        self.assertTrue("reset" in msg.lower() or "deleted" in msg.lower())

    def test_reset_index_no_file(self):
        if services.INDEX_FILE.exists():
            services.INDEX_FILE.unlink()

        success, msg = services.reset_index()
        self.assertTrue(success)
        self.assertIn("index", msg.lower())
        self.assertTrue("no index" in msg.lower() or "not found" in msg.lower())

    # ---------- Basic Flask route tests ----------
    def test_home_get(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Multimedia Search Engine", response.data)

    def test_home_contains_stats_block(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Index stats", response.data)

    def test_search_empty_query(self):
        response = self.client.post(
            "/",
            data={
                "action": "search",
                "query": "",
                "top_k": "10",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Empty query.", response.data)

    def test_malformed_boolean_query(self):
        builder = IndexBuilder()
        builder.build([])
        IndexPersistence.save(builder, services.INDEX_FILE)

        response = self.client.post(
            "/",
            data={
                "action": "search",
                "query": "cat AND",
                "top_k": "10",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid Boolean query", response.data)

    def test_ranked_search_with_results(self):
        docs = [
            Document(
                doc_id=0,
                path="/fake/local/doc.txt",
                file_type="txt",
                raw_text="hello world",
                tokens=["hello", "world"],
            )
        ]
        builder = IndexBuilder()
        builder.build(docs)
        IndexPersistence.save(builder, services.INDEX_FILE)

        response = self.client.post(
            "/",
            data={
                "action": "search",
                "query": "hello",
                "top_k": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/fake/local/doc.txt", response.data)

    def test_flask_reset_index(self):
        docs = [
            Document(
                doc_id=0,
                path="/fake/path.txt",
                file_type="txt",
                raw_text="test",
                tokens=["test"],
            )
        ]
        builder = IndexBuilder()
        builder.build(docs)
        IndexPersistence.save(builder, services.INDEX_FILE)
    
        response = self.client.post("/", data={"action": "reset_index"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Index", response.data)
        self.assertIn(b"deleted successfully", response.data.lower())
    
        stats = services.get_index_stats()
        self.assertEqual(stats["total_docs"], 0)
        self.assertEqual(stats["local_files"], 0)
        self.assertEqual(stats["web_pages"], 0)
    
        self.assertIn(b"Total documents", response.data)
        self.assertIn(b"Local files", response.data)
        self.assertIn(b"Web pages", response.data)
        
    # ---------- Route-level image indexing/search tests ----------
    def test_route_local_index_real_image_then_search_by_sidecar_and_metadata(self):
        folder = self.root / "images"
        folder.mkdir()

        image_path = folder / "brown_dog.png"
        self._make_image(image_path, image_format="PNG", size=(90, 50), color="brown")
        image_path.with_suffix(".txt").write_text(
            "friendly brown dog running in park",
            encoding="utf-8",
        )

        index_response = self._post_index_local(folder)
        self.assertEqual(index_response.status_code, 200)
        self.assertIn(b"Indexed/updated 1 document", index_response.data)

        search_sidecar = self._post_search("friendly park")
        self.assertEqual(search_sidecar.status_code, 200)
        self.assertIn(str(image_path.resolve()).encode(), search_sidecar.data)

        search_meta = self._post_search("png rgb")
        self.assertEqual(search_meta.status_code, 200)
        self.assertIn(str(image_path.resolve()).encode(), search_meta.data)

    def test_route_image_only_search_filters_out_text_docs(self):
        folder = self.root / "mixed"
        folder.mkdir()

        image_path = folder / "sleeping_cat.jpg"
        self._make_image(image_path, image_format="JPEG", size=(120, 80), color="gray")
        image_path.with_suffix(".txt").write_text(
            "sleeping cat on sofa",
            encoding="utf-8",
        )

        text_path = folder / "notes.txt"
        text_path.write_text("sleeping cat care guide", encoding="utf-8")

        index_response = self._post_index_local(folder)
        self.assertEqual(index_response.status_code, 200)
        self.assertIn(b"Indexed/updated 2 document", index_response.data)

        response = self._post_search("sleeping cat", image_only=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(image_path.resolve()).encode(), response.data)
        self.assertNotIn(str(text_path.resolve()).encode(), response.data)

    def test_route_local_index_mixed_valid_and_fake_images_shows_warning(self):
        folder = self.root / "broken_images"
        folder.mkdir()

        valid_image = folder / "real_cat.jpg"
        self._make_image(valid_image, image_format="JPEG", size=(64, 64), color="black")
        valid_image.with_suffix(".txt").write_text("real cat image", encoding="utf-8")

        fake_image = folder / "fake_dog.jpg"
        fake_image.write_text("this is not a real image", encoding="utf-8")

        response = self._post_index_local(folder)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Warnings:", response.data)
        self.assertIn(b"fake_dog.jpg", response.data)

        search_response = self._post_search("real cat", image_only=True)
        self.assertEqual(search_response.status_code, 200)
        self.assertIn(str(valid_image.resolve()).encode(), search_response.data)

    def test_route_local_index_only_fake_images_fails_cleanly(self):
        folder = self.root / "only_fake"
        folder.mkdir()

        fake_image = folder / "fake_only.png"
        fake_image.write_text("not a real image", encoding="utf-8")

        response = self._post_index_local(folder)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No supported files found to index.", response.data)
        self.assertIn(b"fake_only.png", response.data)

    def test_image_preview_route_returns_image_content(self):
        folder = self.root / "preview"
        folder.mkdir()

        image_path = folder / "preview_cat.jpg"
        self._make_image(image_path, image_format="JPEG", size=(80, 40), color="black")
        image_path.with_suffix(".txt").write_text("preview cat", encoding="utf-8")

        index_response = self._post_index_local(folder)
        self.assertEqual(index_response.status_code, 200)

        reader = IndexPersistence.load(services.INDEX_FILE)
        target_doc_id = None
        for doc_id, meta in reader.doc_metadata.items():
            if meta.get("path") == str(image_path.resolve()):
                target_doc_id = doc_id
                break

        self.assertIsNotNone(target_doc_id)

        response = self.client.get(f"/image/{target_doc_id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith("image/"))
        
        
        try:
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content_type.startswith("image/"))
        finally:
            response.close()

    def test_image_preview_route_404_for_missing_doc(self):
        response = self.client.get("/image/9999")
        self.assertEqual(response.status_code, 404)
        
        def test_ranked_search_uses_synonym_expansion_car_to_automobile(self):
            docs = [
                Document(
                    doc_id=0,
                    path="/fake/local/auto.txt",
                    file_type="txt",
                    raw_text="automobile repair manual",
                    tokens=Preprocessor().process("automobile repair manual"),
                )
            ]
            builder = IndexBuilder()
            builder.build(docs)
            IndexPersistence.save(builder, services.INDEX_FILE)
        
            response = self.client.post(
                "/",
                data={
                    "action": "search",
                    "query": "car",
                    "top_k": "5",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"/fake/local/auto.txt", response.data)
        
        
        def test_search_auto_returns_did_you_mean_for_typo(self):
            docs = [
                Document(
                    doc_id=0,
                    path="/fake/local/auto.txt",
                    file_type="txt",
                    raw_text="automobile repair manual",
                    tokens=Preprocessor().process("automobile repair manual"),
                )
            ]
            builder = IndexBuilder()
            builder.build(docs)
            IndexPersistence.save(builder, services.INDEX_FILE)
        
            results, error, detected_mode, suggestion = services.search_auto(
                "automoblie",
                top_k=5,
                image_only=False,
            )
        
            self.assertEqual(error, "")
            self.assertEqual(detected_mode, "ranked")
            self.assertEqual(results, [])
            self.assertEqual(suggestion, "automobile")


if __name__ == "__main__":
    unittest.main()