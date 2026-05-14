import tempfile
import unittest
from pathlib import Path

import multimedia_search.config as config
import multimedia_search.webapp.app as webapp_module
import multimedia_search.webapp.services as services
from multimedia_search.core.persistence import IndexPersistence


class TestWebAppFolderRegistry(unittest.TestCase):
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

    def _make_text_folder(self, folder_name="docs"):
        folder = self.root / folder_name
        folder.mkdir()
        (folder / "note.txt").write_text(
            "alpha registry smoke test",
            encoding="utf-8",
        )
        return folder

    def _post_index_local(self, directory: Path):
        return self.client.post(
            "/",
            data={
                "action": "index_local",
                "directory": str(directory),
            },
        )

    def test_duplicate_folder_submission_warns_and_does_not_reindex(self):
        folder = self._make_text_folder()

        first_response = self._post_index_local(folder)
        self.assertEqual(first_response.status_code, 200)
        self.assertIn(b"Folder indexed successfully", first_response.data)

        reader_after_first = IndexPersistence.load(self.temp_index)
        self.assertEqual(len(reader_after_first.doc_metadata), 1)

        second_response = self._post_index_local(folder)
        self.assertEqual(second_response.status_code, 200)
        self.assertIn(b"This folder is already indexed", second_response.data)
        self.assertIn(b"No duplicate indexing was done", second_response.data)
        self.assertIn(b"toast-warning", second_response.data)

        reader_after_second = IndexPersistence.load(self.temp_index)
        self.assertEqual(len(reader_after_second.doc_metadata), 1)

    def test_duplicate_detection_works_when_registry_file_is_missing(self):
        folder = self._make_text_folder()

        first_response = self._post_index_local(folder)
        self.assertEqual(first_response.status_code, 200)
        self.assertIn(b"Folder indexed successfully", first_response.data)

        registry_path = webapp_module._folder_registry_path()
        self.assertTrue(registry_path.exists())
        registry_path.unlink()

        second_response = self._post_index_local(folder)
        self.assertEqual(second_response.status_code, 200)
        self.assertIn(b"This folder is already indexed", second_response.data)

        reader = IndexPersistence.load(self.temp_index)
        self.assertEqual(len(reader.doc_metadata), 1)
        
    def test_force_reindex_refreshes_folder_and_removes_stale_files(self):
            folder = self.root / "force_docs"
            folder.mkdir()
            keep_file = folder / "keep.txt"
            stale_file = folder / "stale.txt"
        
            keep_file.write_text("first version token", encoding="utf-8")
            stale_file.write_text("stale token", encoding="utf-8")
        
            first_response = self._post_index_local(folder)
            self.assertEqual(first_response.status_code, 200)
            self.assertIn(b"Folder indexed successfully", first_response.data)
            self.assertEqual(services.get_index_stats()["total_docs"], 2)
        
            keep_file.write_text("updatedtoken refreshed content", encoding="utf-8")
            stale_file.unlink()
        
            force_response = self.client.post(
                "/",
                data={
                    "action": "force_index_local",
                    "directory": str(folder),
                },
            )
        
            self.assertEqual(force_response.status_code, 200)
            self.assertIn(b"Folder force re-indexed successfully", force_response.data)
            self.assertIn(b"toast-success", force_response.data)
            self.assertEqual(services.get_index_stats()["total_docs"], 1)
        
            updated_results, updated_error = services.search_ranked("updatedtoken", 10)
            self.assertEqual(updated_error, "")
            self.assertEqual(len(updated_results), 1)
        
            stale_results, stale_error = services.search_ranked("stale", 10)
            self.assertEqual(stale_error, "")
            self.assertEqual(stale_results, [])

    def test_reset_index_clears_folder_registry(self):
        folder = self._make_text_folder()

        index_response = self._post_index_local(folder)
        self.assertEqual(index_response.status_code, 200)
        self.assertIn(b"Folder indexed successfully", index_response.data)

        registry_path = webapp_module._folder_registry_path()
        self.assertTrue(registry_path.exists())

        reset_response = self.client.post("/", data={"action": "reset_index"})
        self.assertEqual(reset_response.status_code, 200)
        self.assertFalse(self.temp_index.exists())
        self.assertFalse(registry_path.exists())

        reindex_response = self._post_index_local(folder)
        self.assertEqual(reindex_response.status_code, 200)
        self.assertIn(b"Folder indexed successfully", reindex_response.data)

    def test_error_message_renders_toast_popup(self):
        response = self.client.post(
            "/",
            data={
                "action": "index_local",
                "directory": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please provide a directory path.", response.data)
        self.assertIn(b'id="toast-popup"', response.data)
        self.assertIn(b"toast-error", response.data)
        self.assertIn(b"Action failed", response.data)


if __name__ == "__main__":
    unittest.main()