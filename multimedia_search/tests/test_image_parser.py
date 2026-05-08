import tempfile
import unittest
from pathlib import Path

from PIL import Image

from multimedia_search.parsers.image_parser import ImageParser


class TestImageParser(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.parser = ImageParser()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _make_image(self, path: Path, image_format: str, size=(100, 60), color="blue") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", size, color=color)
        img.save(path, format=image_format)

    def test_parse_without_sidecar(self):
        image_path = self.root / "animals" / "cats" / "black_cat.jpg"
        self._make_image(image_path, image_format="JPEG", size=(120, 80), color="black")

        text = self.parser.parse(image_path).lower()

        self.assertIn("animals", text)
        self.assertIn("cats", text)
        self.assertIn("black_cat", text)
        self.assertIn("black cat", text)
        self.assertIn("format jpeg", text)
        self.assertIn("width 120", text)
        self.assertIn("height 80", text)
        self.assertIn("mode rgb", text)

    def test_parse_with_sidecar(self):
        image_path = self.root / "animals" / "dogs" / "brown_dog.png"
        sidecar_path = image_path.with_suffix(".txt")

        self._make_image(image_path, image_format="PNG", size=(90, 50), color="brown")
        sidecar_path.write_text("friendly brown dog running in park", encoding="utf-8")

        text = self.parser.parse(image_path).lower()

        self.assertIn("animals", text)
        self.assertIn("dogs", text)
        self.assertIn("brown_dog", text)
        self.assertIn("brown dog", text)
        self.assertIn("friendly brown dog running in park", text)
        self.assertIn("format png", text)
        self.assertIn("width 90", text)
        self.assertIn("height 50", text)
        self.assertIn("mode rgb", text)

    def test_parse_with_numeric_folder_names(self):
        image_path = self.root / "2025" / "photos" / "img_001.jpg"
        self._make_image(image_path, image_format="JPEG", size=(64, 64), color="green")

        text = self.parser.parse(image_path).lower()

        self.assertIn("2025", text)
        self.assertIn("photos", text)
        self.assertIn("img_001", text)
        self.assertIn("img 001", text)
        self.assertIn("format jpeg", text)
        self.assertIn("width 64", text)
        self.assertIn("height 64", text)

    def test_fake_image_with_image_extension_is_rejected(self):
        fake_image_path = self.root / "broken" / "not_really_image.jpg"
        fake_image_path.parent.mkdir(parents=True, exist_ok=True)
        fake_image_path.write_text("this is plain text, not a real image", encoding="utf-8")

        with self.assertRaises(ValueError):
            self.parser.parse(fake_image_path)


if __name__ == "__main__":
    unittest.main()