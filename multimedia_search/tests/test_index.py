import tempfile
import unittest
from pathlib import Path

from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.parsers.parser_factory import ParserFactory
from multimedia_search.scanner.file_scanner import FileScanner


class TestIndexing(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("multimedia_search/tests/test_data")
        self.temp_index = tempfile.NamedTemporaryFile(delete=False)
        self.temp_index.close()

    def test_index_build_and_load(self):
        scanner = FileScanner()
        factory = ParserFactory()
        preproc = Preprocessor()
        docs = []

        for i, path in enumerate(scanner.scan(self.test_dir)):
            parser = factory.get_parser(path.suffix)
            raw = parser.parse(path)
            tokens = preproc.process(raw)
            docs.append(Document(i, path, path.suffix[1:], raw, tokens))

        builder = IndexBuilder()
        builder.build(docs)

        IndexPersistence.save(builder, Path(self.temp_index.name))
        reader = IndexPersistence.load(Path(self.temp_index.name))

        self.assertEqual(reader.get_doc_count(), len(docs))

    def tearDown(self):
        Path(self.temp_index.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
