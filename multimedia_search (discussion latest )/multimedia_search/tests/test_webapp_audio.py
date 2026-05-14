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


AUDIO_RAW_TEXT = """
Audio file: voice_note.mp3
Audio metadata terms: audio voice note speech recording transcript summary conclusion

AUDIO_TRANSCRIPT:
We need to finish the project deadline before Thursday. Mohamed Salah was mentioned.

AUDIO_SUMMARY:
The voice note discusses a project deadline.

AUDIO_CONCLUSION:
The main takeaway is to finish before Thursday.

AUDIO_ACTION_ITEMS:
Run tests, Prepare demo

AUDIO_KEYWORDS:
project, deadline, tests

AUDIO_MENTIONED_PEOPLE:
Mohamed Salah

AUDIO_MENTIONED_PLACES:
Egypt

AUDIO_MENTIONED_ORGANIZATIONS:
MIU
""".strip()


class TestWebAppAudio(unittest.TestCase):
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

    def _save_audio_doc(self):
        audio_path = self.root / "voice_note.mp3"
        audio_path.write_bytes(b"fake audio content for route test")

        preprocessor = Preprocessor()
        doc = Document(
            doc_id=0,
            path=str(audio_path.resolve()),
            file_type="mp3",
            raw_text=AUDIO_RAW_TEXT,
            tokens=preprocessor.process(AUDIO_RAW_TEXT),
        )

        builder = IndexBuilder()
        builder.build([doc])
        IndexPersistence.save(builder, services.INDEX_FILE)

        return audio_path

    def test_ranked_search_renders_audio_analysis_card(self):
        audio_path = self._save_audio_doc()

        response = self.client.post(
            "/",
            data={
                "action": "search",
                "query": "deadline",
                "top_k": "10",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Audio (mp3)", response.data)
        self.assertIn(b"Audio content", response.data)
        self.assertIn(b"Transcript-based, not voice identity recognition", response.data)
        self.assertIn(b"The voice note discusses a project deadline.", response.data)
        self.assertIn(b"The main takeaway is to finish before Thursday.", response.data)
        self.assertIn(str(audio_path.resolve()).encode(), response.data)
        self.assertIn(b"/audio/0", response.data)
        
        self.assertIn(b"See full transcript", response.data)
        self.assertIn(b"Full transcript:", response.data)
        self.assertIn(b"We need to finish the project deadline before Thursday.", response.data)

    def test_audio_preview_route_returns_audio_content(self):
        self._save_audio_doc()

        response = self.client.get("/audio/0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"fake audio content for route test")

    def test_audio_preview_route_404_for_non_audio_doc(self):
        text_path = self.root / "note.txt"
        text_path.write_text("deadline text", encoding="utf-8")

        doc = Document(
            doc_id=0,
            path=str(text_path.resolve()),
            file_type="txt",
            raw_text="deadline text",
            tokens=["deadline", "text"],
        )

        builder = IndexBuilder()
        builder.build([doc])
        IndexPersistence.save(builder, services.INDEX_FILE)

        response = self.client.get("/audio/0")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()