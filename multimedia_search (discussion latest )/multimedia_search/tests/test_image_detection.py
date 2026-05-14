import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from multimedia_search.vision.object_detector import ObjectDetector
from multimedia_search.vision.types import DetectedObject


class TestImageDetection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _make_image(self, path: Path, image_format: str = "JPEG", size=(400, 400), color="black") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", size, color=color)
        img.save(path, format=image_format)

    @patch.object(ObjectDetector, "_predict_source")
    def test_build_detection_text_empty_when_no_detections(self, mock_predict):
        image_path = self.root / "m.jpg"
        self._make_image(image_path)

        mock_predict.return_value = []

        detector = ObjectDetector(enabled=True, use_tiles=False)
        text = detector.build_detection_text(image_path)

        self.assertEqual(text, "")

    @patch.object(ObjectDetector, "_predict_source")
    def test_build_detection_text_uses_detected_labels(self, mock_predict):
        image_path = self.root / "m.jpg"
        self._make_image(image_path)

        mock_predict.return_value = [
            DetectedObject(label="dog", confidence=0.91),
            DetectedObject(label="sofa", confidence=0.72),
        ]

        detector = ObjectDetector(enabled=True, use_tiles=False)
        text = detector.build_detection_text(image_path)

        self.assertIn("dog", text)
        self.assertIn("sofa", text)

    @patch.object(ObjectDetector, "_predict_source")
    def test_tile_detection_can_add_small_background_object(self, mock_predict):
        image_path = self.root / "background_dog.jpg"
        self._make_image(image_path, size=(400, 400))

        def side_effect(source):
            # Full image misses the dog
            if isinstance(source, str):
                return []

            # One of the tiles sees the dog
            if hasattr(source, "size") and source.size[0] < 400:
                return [DetectedObject(label="dog", confidence=0.62)]

            return []

        mock_predict.side_effect = side_effect

        detector = ObjectDetector(
            enabled=True,
            use_tiles=True,
            tile_grid=(2, 2),
            tile_overlap=0.20,
        )
        text = detector.build_detection_text(image_path)

        self.assertIn("dog", text)

    @patch.object(ObjectDetector, "_predict_source")
    def test_merge_keeps_best_confidence_per_label(self, mock_predict):
        image_path = self.root / "dog.jpg"
        self._make_image(image_path, size=(400, 400))

        def side_effect(source):
            if isinstance(source, str):
                return [DetectedObject(label="dog", confidence=0.40)]
            return [
                DetectedObject(label="dog", confidence=0.73),
                DetectedObject(label="person", confidence=0.55),
            ]

        mock_predict.side_effect = side_effect

        detector = ObjectDetector(enabled=True, use_tiles=True)
        detections = detector.detect(image_path)

        labels = [item.label for item in detections]
        self.assertIn("dog", labels)
        self.assertIn("person", labels)

        dog_item = next(item for item in detections if item.label == "dog")
        self.assertEqual(dog_item.confidence, 0.73)