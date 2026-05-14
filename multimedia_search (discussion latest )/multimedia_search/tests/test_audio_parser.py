import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from multimedia_search.parsers.audio_parser import AudioParser
from multimedia_search.parsers.parser_factory import ParserFactory


class TestAudioParser(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _make_audio_file(self, name="voice_note.mp3") -> Path:
        path = self.root / name
        path.write_bytes(b"fake audio bytes for mocked transcription")
        return path

    def test_audio_parser_builds_searchable_transcript_text(self):
        audio_path = self._make_audio_file()

        with patch(
            "multimedia_search.parsers.audio_parser.transcriber.transcribe_audio_file",
            return_value="We need to finish the multimedia search project before Thursday.",
        ), patch(
            "multimedia_search.parsers.audio_parser.transcriber.analyze_audio_transcript",
            return_value={
                "summary": "The voice note discusses the project deadline.",
                "conclusion": "The team should finish before Thursday.",
                "action_items": ["Run tests", "Prepare demo"],
                "keywords": ["project", "deadline", "tests"],
                "mentioned_people": ["Mohamed Salah"],
                "mentioned_places": ["Egypt"],
                "mentioned_organizations": ["MIU"],
            },
        ):
            raw_text = AudioParser().parse(audio_path)

        self.assertIn("AUDIO_TRANSCRIPT:", raw_text)
        self.assertIn("finish the multimedia search project", raw_text)
        self.assertIn("AUDIO_SUMMARY:", raw_text)
        self.assertIn("project deadline", raw_text)
        self.assertIn("AUDIO_CONCLUSION:", raw_text)
        self.assertIn("Run tests", raw_text)
        self.assertIn("Mohamed Salah", raw_text)
        self.assertIn("Egypt", raw_text)
        self.assertIn("MIU", raw_text)

    def test_audio_parser_uses_cache_on_second_parse(self):
        audio_path = self._make_audio_file()

        with patch(
            "multimedia_search.parsers.audio_parser.transcriber.transcribe_audio_file",
            return_value="Cached transcript content.",
        ) as transcribe_mock, patch(
            "multimedia_search.parsers.audio_parser.transcriber.analyze_audio_transcript",
            return_value={
                "summary": "Cached summary.",
                "conclusion": "Cached conclusion.",
                "action_items": [],
                "keywords": ["cached"],
                "mentioned_people": [],
                "mentioned_places": [],
                "mentioned_organizations": [],
            },
        ):
            first_raw = AudioParser().parse(audio_path)
            second_raw = AudioParser().parse(audio_path)

        self.assertIn("Cached transcript content", first_raw)
        self.assertIn("Cached transcript content", second_raw)
        self.assertEqual(transcribe_mock.call_count, 1)
        self.assertTrue(Path(str(audio_path) + ".ms_audio_cache").exists())

    def test_parser_factory_returns_audio_parser_for_mp3(self):
        parser = ParserFactory.get_parser(".mp3")
        self.assertIsInstance(parser, AudioParser)

    def test_audio_parser_rejects_unsupported_audio_extension(self):
        path = self.root / "audio.exe"
        path.write_bytes(b"fake")

        with self.assertRaises(ValueError):
            AudioParser().parse(path)


if __name__ == "__main__":
    unittest.main()