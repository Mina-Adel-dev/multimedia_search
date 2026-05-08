import tempfile
import unittest
from pathlib import Path

from PIL import Image

from multimedia_search.core.boolean import BooleanRetriever
from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder, IndexReader
from multimedia_search.core.phrase import PhraseSearcher
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.core.retrieval import RankedRetriever
from multimedia_search.parsers.parser_factory import ParserFactory
from multimedia_search.scanner.file_scanner import FileScanner


class TestImageRetrieval(unittest.TestCase):
    """End-to-end tests for image metadata retrieval."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        cats_dir = self.root / "animals" / "cats"
        cats_dir.mkdir(parents=True)
        self._make_image(cats_dir / "black_cat.jpg", image_format="JPEG", size=(120, 80), color="black")
        (cats_dir / "black_cat.txt").write_text(
            "black cat sleeping on sofa indoor pet",
            encoding="utf-8",
        )

        dogs_dir = self.root / "animals" / "dogs"
        dogs_dir.mkdir(parents=True)
        self._make_image(dogs_dir / "golden_dog.png", image_format="PNG", size=(90, 50), color="gold")
        (dogs_dir / "golden_dog.txt").write_text(
            "golden dog running outside park",
            encoding="utf-8",
        )

        self.index = self._build_index()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _make_image(self, path: Path, image_format: str, size=(100, 60), color="blue") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", size, color=color)
        img.save(path, format=image_format)

    def _build_index(self) -> IndexReader:
        scanner = FileScanner()
        factory = ParserFactory()
        preprocessor = Preprocessor()

        docs = []
        doc_id = 0

        for file_path in scanner.scan(self.root):
            parser = factory.get_parser(file_path.suffix.lower())
            raw_text = parser.parse(file_path)
            tokens = preprocessor.process(raw_text)

            doc = Document(
                doc_id=doc_id,
                path=str(file_path.resolve()),
                file_type=file_path.suffix[1:],
                raw_text=raw_text,
                tokens=tokens,
            )
            docs.append(doc)
            doc_id += 1

        builder = IndexBuilder()
        builder.build(docs)
        return IndexReader(builder.get_data())

    # ---------- Ranked retrieval tests ----------
    def test_ranked_search_by_sidecar_term(self):
        retriever = RankedRetriever(self.index, Preprocessor())

        results = retriever.search("black", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

        results = retriever.search("sofa")
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

        results = retriever.search("golden", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

        results = retriever.search("park", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

    def test_ranked_search_by_folder_name(self):
        retriever = RankedRetriever(self.index, Preprocessor())

        results = retriever.search("cats", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

        results = retriever.search("dogs", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

    def test_ranked_search_by_filename_stem(self):
        retriever = RankedRetriever(self.index, Preprocessor())

        results = retriever.search("black_cat", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

        results = retriever.search("golden_dog", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

        results = retriever.search("black cat", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

    def test_ranked_search_by_image_metadata_terms(self):
        retriever = RankedRetriever(self.index, Preprocessor())

        results = retriever.search("jpeg rgb", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

        results = retriever.search("png rgb", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

        results = retriever.search("width 120", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

        results = retriever.search("height 50", top_k=5)
        paths = [r[2] for r in results]
        self.assertIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

    # ---------- Boolean retrieval tests ----------
    def test_boolean_and(self):
        retriever = BooleanRetriever(self.index, Preprocessor())

        doc_ids = retriever.evaluate("black AND sofa")
        paths = [self.index.get_doc_metadata(did)["path"] for did in doc_ids]
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

        doc_ids = retriever.evaluate("golden AND park")
        paths = [self.index.get_doc_metadata(did)["path"] for did in doc_ids]
        self.assertIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

        doc_ids = retriever.evaluate("black AND park")
        self.assertEqual(len(doc_ids), 0)

    def test_boolean_or(self):
        retriever = BooleanRetriever(self.index, Preprocessor())

        doc_ids = retriever.evaluate("black OR golden")
        paths = {self.index.get_doc_metadata(did)["path"] for did in doc_ids}
        expected = {
            str((self.root / "animals/cats/black_cat.jpg").resolve()),
            str((self.root / "animals/dogs/golden_dog.png").resolve()),
        }
        self.assertEqual(paths, expected)

    def test_boolean_not(self):
        retriever = BooleanRetriever(self.index, Preprocessor())

        doc_ids = retriever.evaluate("cats AND NOT dogs")
        paths = {self.index.get_doc_metadata(did)["path"] for did in doc_ids}
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)
        self.assertNotIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

    # ---------- Phrase retrieval tests ----------
    def test_phrase_search(self):
        searcher = PhraseSearcher(self.index, Preprocessor())

        doc_ids = searcher.search("sleeping on sofa")
        paths = {self.index.get_doc_metadata(did)["path"] for did in doc_ids}
        self.assertIn(str((self.root / "animals/cats/black_cat.jpg").resolve()), paths)

        doc_ids = searcher.search("running outside park")
        paths = {self.index.get_doc_metadata(did)["path"] for did in doc_ids}
        self.assertIn(str((self.root / "animals/dogs/golden_dog.png").resolve()), paths)

        doc_ids = searcher.search("cat running")
        self.assertEqual(len(doc_ids), 0)


if __name__ == "__main__":
    unittest.main()