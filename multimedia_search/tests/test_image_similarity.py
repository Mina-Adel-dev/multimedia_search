import tempfile
import unittest
from pathlib import Path

from PIL import Image

from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder, IndexReader
from multimedia_search.vision.image_features import (
    compare_image_features,
    extract_image_features,
)
from multimedia_search.vision.similarity import find_similar_images


class TestImageSimilarity(unittest.TestCase):
    """Backend-only tests for query-by-image / similar image retrieval."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _make_image(self, path: Path, color: str, size=(64, 64)) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color=color).save(path, format="PNG")

    def _build_reader(self, paths: list[Path]) -> IndexReader:
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

        return IndexReader(builder.get_data())

    def test_identical_color_features_score_higher_than_different_color(self):
        red_a = self.root / "red_a.png"
        red_b = self.root / "red_b.png"
        blue = self.root / "blue.png"

        self._make_image(red_a, "red")
        self._make_image(red_b, "red")
        self._make_image(blue, "blue")

        red_a_features = extract_image_features(red_a)
        red_b_features = extract_image_features(red_b)
        blue_features = extract_image_features(blue)

        same_score = compare_image_features(red_a_features, red_b_features)
        different_score = compare_image_features(red_a_features, blue_features)

        self.assertGreater(same_score, different_score)
        self.assertAlmostEqual(same_score, 1.0, places=6)

    def test_similar_image_search_ranks_same_color_before_different_color(self):
        query = self.root / "query_red.png"
        red_candidate = self.root / "candidate_red.png"
        blue_candidate = self.root / "candidate_blue.png"
        green_candidate = self.root / "candidate_green.png"

        self._make_image(query, "red")
        self._make_image(red_candidate, "red")
        self._make_image(blue_candidate, "blue")
        self._make_image(green_candidate, "green")

        reader = self._build_reader([blue_candidate, red_candidate, green_candidate])
        results = find_similar_images(query, reader, top_k=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["path"], str(red_candidate.resolve()))
        self.assertGreater(results[0]["score"], results[1]["score"])

    def test_similar_image_search_ignores_non_images_and_web_entries(self):
        query = self.root / "query_red.png"
        red_candidate = self.root / "candidate_red.png"
        text_file = self.root / "notes.txt"

        self._make_image(query, "red")
        self._make_image(red_candidate, "red")
        text_file.write_text("not an image", encoding="utf-8")

        docs = [
            Document(
                doc_id=0,
                path=str(red_candidate.resolve()),
                file_type="png",
                raw_text="red",
                tokens=["red"],
            ),
            Document(
                doc_id=1,
                path=str(text_file.resolve()),
                file_type="txt",
                raw_text="notes",
                tokens=["notes"],
            ),
            Document(
                doc_id=2,
                path="https://example.com/image.png",
                file_type="png",
                raw_text="web image",
                tokens=["web", "image"],
            ),
        ]

        builder = IndexBuilder()
        builder.build(docs)
        reader = IndexReader(builder.get_data())

        results = find_similar_images(query, reader, top_k=10)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["doc_id"], 0)
        self.assertEqual(results[0]["path"], str(red_candidate.resolve()))

    def test_similar_image_search_can_exclude_query_path_when_indexed(self):
        query = self.root / "query_red.png"
        red_candidate = self.root / "candidate_red.png"

        self._make_image(query, "red")
        self._make_image(red_candidate, "red")

        reader = self._build_reader([query, red_candidate])
        results = find_similar_images(query, reader, top_k=10, exclude_query_path=True)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], str(red_candidate.resolve()))

    def test_top_k_zero_returns_empty_results(self):
        query = self.root / "query_red.png"
        red_candidate = self.root / "candidate_red.png"

        self._make_image(query, "red")
        self._make_image(red_candidate, "red")

        reader = self._build_reader([red_candidate])

        self.assertEqual(find_similar_images(query, reader, top_k=0), [])


if __name__ == "__main__":
    unittest.main()