import tempfile
import unittest
from pathlib import Path

import multimedia_search.config as config
import multimedia_search.webapp.app as webapp_module
import multimedia_search.webapp.services as services
from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.core.preprocessor import Preprocessor


class TestWebAppRelatedSearches(unittest.TestCase):
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

    def _save_text_doc(self, text: str):
        preprocessor = Preprocessor()
        doc = Document(
            doc_id=0,
            path=str(self.root / "dog_note.txt"),
            file_type="txt",
            raw_text=text,
            tokens=preprocessor.process(text),
        )

        builder = IndexBuilder()
        builder.build([doc])
        IndexPersistence.save(builder, services.INDEX_FILE)

    def test_ranked_search_renders_related_search_chips_for_dog(self):
        self._save_text_doc("dog park face golden retriever")

        response = self.client.post(
            "/",
            data={
                "action": "search",
                "query": "dog",
                "top_k": "10",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Explore related searches", response.data)
        self.assertIn(b"golden retriever dog", response.data)
        self.assertIn(b"labrador dog", response.data)
        self.assertIn(b"dog in park", response.data)
        self.assertIn(b"dog in home", response.data)
        self.assertIn(b"dog face", response.data)
        self.assertIn(b"dog ears", response.data)

    def test_related_search_chip_preserves_image_only_filter(self):
        self._save_text_doc("dog park face golden retriever")

        response = self.client.post(
            "/",
            data={
                "action": "search",
                "query": "dog",
                "top_k": "10",
                "image_only": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Explore related searches", response.data)
        self.assertIn(b'name="image_only" value="1"', response.data)


if __name__ == "__main__":
    unittest.main()