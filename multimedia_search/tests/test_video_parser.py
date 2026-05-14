import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from multimedia_search.parsers.video_parser import VideoParser


class TestVideoParser(unittest.TestCase):
    def test_video_parser_builds_searchable_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "demo_video.mp4"
            video_path.write_bytes(b"fake video bytes for patched transcriber")

            with patch(
                "multimedia_search.audio.transcriber.transcribe_audio_file",
                return_value="This is a demo video transcript about Python.",
            ), patch(
                "multimedia_search.audio.transcriber.analyze_audio_transcript",
                return_value={
                    "summary": "A demo video about Python.",
                    "conclusion": "The video was indexed.",
                    "action_items": [],
                    "keywords": ["python", "demo", "video"],
                    "mentioned_people": [],
                    "mentioned_places": [],
                    "mentioned_organizations": [],
                },
            ):
                text = VideoParser().parse(video_path)

            self.assertIn("Video file: demo_video.mp4", text)
            self.assertIn("AUDIO_TRANSCRIPT:", text)
            self.assertIn("demo video transcript", text)
            self.assertIn("AUDIO_SUMMARY:", text)


if __name__ == "__main__":
    unittest.main()