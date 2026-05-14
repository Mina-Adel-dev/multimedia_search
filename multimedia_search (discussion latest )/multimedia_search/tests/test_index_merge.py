import unittest
import tempfile
from pathlib import Path
from argparse import Namespace

import multimedia_search.config as config
import multimedia_search.cli.search_cli as search_cli

from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.core.preprocessor import Preprocessor


class TestIndexMerge(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test files and index
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # Create a temporary index file path
        self.test_index = self.root / "test_index.pkl"

        # Save original config path and patch it
        self.original_config_index = config.INDEX_FILE
        config.INDEX_FILE = self.test_index

        # Create a dummy web document to seed the index
        self.web_doc = Document(
            doc_id=0,
            path="http://example.com",
            file_type="html",
            raw_text="Example Domain",
            tokens=Preprocessor().process("Example Domain"),
        )

        builder = IndexBuilder()
        builder.build([self.web_doc])
        IndexPersistence.save(builder, config.INDEX_FILE)

    def tearDown(self):
        # Restore original config INDEX_FILE
        config.INDEX_FILE = self.original_config_index
        self.temp_dir.cleanup()

    def _stored_path(self, path: Path) -> str:
        """Match the CLI local path storage policy."""
        return str(path.expanduser().resolve())

    def test_merge_preserves_web_doc(self):
        # Create a local file to index
        local_dir = self.root / "local"
        local_dir.mkdir()
        local_file = local_dir / "test.txt"
        local_file.write_text("hello world", encoding="utf-8")

        # Run local indexing
        args = Namespace(directory=str(local_dir))
        search_cli.handle_index(args)

        # Load the index
        reader = IndexPersistence.load(config.INDEX_FILE)

        # Check that both web doc and local doc exist
        paths = {meta["path"] for meta in reader.doc_metadata.values()}
        self.assertIn("http://example.com", paths)
        self.assertIn(self._stored_path(local_file), paths)
        self.assertEqual(len(reader.doc_metadata), 2)

    def test_rerun_local_index_replaces_old(self):
        # Create a local file
        local_dir = self.root / "local"
        local_dir.mkdir()
        local_file = local_dir / "test.txt"
        local_file.write_text("version 1", encoding="utf-8")

        # First index
        args = Namespace(directory=str(local_dir))
        search_cli.handle_index(args)

        # Modify the file
        local_file.write_text("version 2", encoding="utf-8")

        # Second index
        search_cli.handle_index(args)

        # Load index
        reader = IndexPersistence.load(config.INDEX_FILE)

        # Count documents with that path (should be exactly 1)
        matching = [
            doc_id
            for doc_id, meta in reader.doc_metadata.items()
            if meta["path"] == self._stored_path(local_file)
        ]
        self.assertEqual(len(matching), 1)

        # Check that the raw text was updated
        doc_id = matching[0]
        meta = reader.get_doc_metadata(doc_id)
        self.assertIn("version 2", meta.get("raw_text", ""))

    def test_web_doc_untouched_by_local_dedup(self):
        # Create two local files
        local_dir = self.root / "local"
        local_dir.mkdir()

        file1 = local_dir / "a.txt"
        file1.write_text("alpha", encoding="utf-8")

        file2 = local_dir / "b.txt"
        file2.write_text("beta", encoding="utf-8")

        # Index both
        args = Namespace(directory=str(local_dir))
        search_cli.handle_index(args)

        # Re-index same folder again; should keep both locals and web
        search_cli.handle_index(args)

        reader = IndexPersistence.load(config.INDEX_FILE)
        paths = {meta["path"] for meta in reader.doc_metadata.values()}

        self.assertIn("http://example.com", paths)
        self.assertIn(self._stored_path(file1), paths)
        self.assertIn(self._stored_path(file2), paths)
        self.assertEqual(len(reader.doc_metadata), 3)


if __name__ == "__main__":
    unittest.main()