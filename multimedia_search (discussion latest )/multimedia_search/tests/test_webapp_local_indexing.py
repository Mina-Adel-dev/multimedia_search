import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from unittest.mock import patch

import multimedia_search.config as config
import multimedia_search.webapp.services as services

from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.core.preprocessor import Preprocessor


class TestWebAppLocalIndexing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.temp_index = self.root / "test_index.pkl"

        self.original_config_index = config.INDEX_FILE
        self.original_services_index = services.INDEX_FILE
        self.original_cwd = Path.cwd()

        config.INDEX_FILE = self.temp_index
        services.INDEX_FILE = self.temp_index

    def tearDown(self):
        os.chdir(self.original_cwd)
        config.INDEX_FILE = self.original_config_index
        services.INDEX_FILE = self.original_services_index
        self.temp_dir.cleanup()

    def _make_image(self, path: Path, image_format: str, size=(100, 60), color="blue") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", size, color=color)
        img.save(path, format=image_format)

    def test_index_folder_a_then_b_keeps_both_searchable(self):
        folder_a = self.root / "A"
        folder_b = self.root / "B"
        folder_a.mkdir()
        folder_b.mkdir()

        (folder_a / "a.txt").write_text("alpha uniqueapple", encoding="utf-8")
        (folder_b / "b.txt").write_text("beta uniquebanana", encoding="utf-8")

        success_a, msg_a, count_a = services.index_local_directory(str(folder_a))
        self.assertTrue(success_a, msg_a)
        self.assertEqual(count_a, 1)

        success_b, msg_b, count_b = services.index_local_directory(str(folder_b))
        self.assertTrue(success_b, msg_b)
        self.assertEqual(count_b, 1)

        reader = IndexPersistence.load(self.temp_index)
        paths = {meta["path"] for meta in reader.doc_metadata.values()}
        self.assertIn(str((folder_a / "a.txt").resolve()), paths)
        self.assertIn(str((folder_b / "b.txt").resolve()), paths)
        self.assertEqual(len(paths), 2)

        apple_results, apple_error = services.search_ranked("uniqueapple", top_k=10)
        banana_results, banana_error = services.search_ranked("uniquebanana", top_k=10)

        self.assertEqual(apple_error, "")
        self.assertEqual(banana_error, "")
        self.assertEqual(len(apple_results), 1)
        self.assertEqual(len(banana_results), 1)
        self.assertEqual(apple_results[0]["path"], str((folder_a / "a.txt").resolve()))
        self.assertEqual(banana_results[0]["path"], str((folder_b / "b.txt").resolve()))

    def test_reindex_same_folder_refreshes_by_normalized_path(self):
        folder = self.root / "A"
        folder.mkdir()
        file_path = folder / "a.txt"
        file_path.write_text("version one", encoding="utf-8")

        os.chdir(self.root)
        success_1, msg_1, count_1 = services.index_local_directory("A")
        self.assertTrue(success_1, msg_1)
        self.assertEqual(count_1, 1)

        file_path.write_text("version two refreshed", encoding="utf-8")
        success_2, msg_2, count_2 = services.index_local_directory(str(folder.resolve()))
        self.assertTrue(success_2, msg_2)
        self.assertEqual(count_2, 1)

        reader = IndexPersistence.load(self.temp_index)
        matching = [
            doc_id
            for doc_id, meta in reader.doc_metadata.items()
            if meta["path"] == str(file_path.resolve())
        ]
        self.assertEqual(len(matching), 1)
        self.assertIn("version two refreshed", reader.get_doc_metadata(matching[0]).get("raw_text", ""))

        results, error = services.search_ranked("refreshed", top_k=10)
        self.assertEqual(error, "")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], str(file_path.resolve()))

    def test_invalid_multi_directory_input_is_rejected(self):
        folder_a = self.root / "A"
        folder_b = self.root / "B"
        folder_a.mkdir()
        folder_b.mkdir()

        success, msg, count = services.index_local_directory(f"{folder_a}\n{folder_b}")
        self.assertFalse(success)
        self.assertEqual(count, 0)
        self.assertIn("Only one directory path is supported", msg)

    def test_local_reindex_preserves_existing_web_doc_searchability(self):
        web_doc = Document(
            doc_id=0,
            path="https://example.com",
            file_type="html",
            raw_text="example domain uniquewebterm",
            tokens=Preprocessor().process("example domain uniquewebterm"),
        )
        builder = IndexBuilder()
        builder.build([web_doc])
        IndexPersistence.save(builder, self.temp_index)

        folder = self.root / "A"
        folder.mkdir()
        (folder / "a.txt").write_text("local alpha", encoding="utf-8")

        success, msg, count = services.index_local_directory(str(folder))
        self.assertTrue(success, msg)
        self.assertEqual(count, 1)

        results, error = services.search_ranked("uniquewebterm", top_k=10)
        self.assertEqual(error, "")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], "https://example.com")
        
        
        
        
        @patch("multimedia_search.webapp.services.enrich_image_raw_text")
        def test_local_index_real_image_becomes_searchable_by_detected_label(self, mock_enrich):
            folder = self.root / "detected"
            folder.mkdir()
        
            image_path = folder / "m.jpg"
            self._make_image(image_path, image_format="JPEG", size=(80, 50), color="black")
        
            base_raw_text = "detected m format jpeg width 80 height 50 mode rgb"
            mock_enrich.return_value = f"{base_raw_text} dog animal pet"
        
            success, msg, count = services.index_local_directory(str(folder))
            self.assertTrue(success, msg)
            self.assertEqual(count, 1)
        
            results, error = services.search_ranked("dog", top_k=10, image_only=True)
            self.assertEqual(error, "")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["path"], str(image_path.resolve()))
            self.assertTrue(results[0]["is_image"])
        
            reader = IndexPersistence.load(self.temp_index)
            stored_raw_texts = [meta.get("raw_text", "") for meta in reader.doc_metadata.values()]
            self.assertTrue(any("dog" in text.lower() for text in stored_raw_texts))

    def test_local_index_real_image_is_searchable_by_sidecar_and_metadata(self):
        folder = self.root / "images"
        folder.mkdir()

        image_path = folder / "brown_dog.png"
        self._make_image(image_path, image_format="PNG", size=(90, 50), color="brown")
        image_path.with_suffix(".txt").write_text(
            "friendly brown dog running in park",
            encoding="utf-8",
        )

        success, msg, count = services.index_local_directory(str(folder))
        self.assertTrue(success, msg)
        self.assertEqual(count, 1)

        by_sidecar, error1 = services.search_ranked("friendly park", top_k=10)
        by_meta, error2 = services.search_ranked("png rgb", top_k=10)
        by_size, error3 = services.search_ranked("height 50", top_k=10)

        self.assertEqual(error1, "")
        self.assertEqual(error2, "")
        self.assertEqual(error3, "")

        self.assertEqual(len(by_sidecar), 1)
        self.assertEqual(len(by_meta), 1)
        self.assertEqual(len(by_size), 1)

        self.assertEqual(by_sidecar[0]["path"], str(image_path.resolve()))
        self.assertEqual(by_meta[0]["path"], str(image_path.resolve()))
        self.assertEqual(by_size[0]["path"], str(image_path.resolve()))
        self.assertTrue(by_sidecar[0]["is_image"])
        self.assertEqual(by_sidecar[0]["file_type"], "png")

    def test_search_ranked_image_only_filters_non_images(self):
        folder = self.root / "mixed"
        folder.mkdir()

        image_path = folder / "sleeping_cat.jpg"
        self._make_image(image_path, image_format="JPEG", size=(120, 80), color="gray")
        image_path.with_suffix(".txt").write_text(
            "sleeping cat on sofa",
            encoding="utf-8",
        )

        (folder / "notes.txt").write_text(
            "sleeping cat care guide",
            encoding="utf-8",
        )

        success, msg, count = services.index_local_directory(str(folder))
        self.assertTrue(success, msg)
        self.assertEqual(count, 2)

        all_results, error_all = services.search_ranked("sleeping cat", top_k=10, image_only=False)
        image_results, error_img = services.search_ranked("sleeping cat", top_k=10, image_only=True)

        self.assertEqual(error_all, "")
        self.assertEqual(error_img, "")
        self.assertGreaterEqual(len(all_results), 2)
        self.assertEqual(len(image_results), 1)
        self.assertEqual(image_results[0]["path"], str(image_path.resolve()))
        self.assertTrue(image_results[0]["is_image"])

    def test_local_index_skips_invalid_fake_image_with_warning(self):
        folder = self.root / "broken_images"
        folder.mkdir()

        valid_image = folder / "real_cat.jpg"
        self._make_image(valid_image, image_format="JPEG", size=(64, 64), color="black")
        valid_image.with_suffix(".txt").write_text(
            "real cat image",
            encoding="utf-8",
        )

        fake_image = folder / "fake_dog.jpg"
        fake_image.write_text("this is not a real image", encoding="utf-8")

        success, msg, count = services.index_local_directory(str(folder))
        self.assertTrue(success, msg)
        self.assertEqual(count, 1)
        self.assertIn("Warnings:", msg)
        self.assertIn("fake_dog.jpg", msg)

        results, error = services.search_ranked("real cat", top_k=10, image_only=True)
        self.assertEqual(error, "")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], str(valid_image.resolve()))

    def test_local_index_only_fake_images_fails_cleanly(self):
        folder = self.root / "only_fake"
        folder.mkdir()

        fake_image = folder / "fake_only.png"
        fake_image.write_text("not a real image", encoding="utf-8")

        success, msg, count = services.index_local_directory(str(folder))
        self.assertFalse(success)
        self.assertEqual(count, 0)
        self.assertIn("No supported files found to index.", msg)
        self.assertIn("fake_only.png", msg)


if __name__ == "__main__":
    unittest.main()