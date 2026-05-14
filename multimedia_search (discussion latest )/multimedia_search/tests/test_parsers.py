import unittest
from pathlib import Path
from multimedia_search.parsers.parser_factory import ParserFactory
from multimedia_search.utils.exceptions import UnsupportedFormatError

class TestParsers(unittest.TestCase):
    def setUp(self):
        self.test_data_dir = Path(__file__).parent / "test_data"
        self.factory = ParserFactory()

    def test_txt_parser_returns_text(self):
        parser = self.factory.get_parser(".txt")
        text = parser.parse(self.test_data_dir / "sample.txt")
        self.assertTrue(len(text) > 0)
        self.assertIn("Python", text)

    def test_pdf_parser_returns_text(self):
        parser = self.factory.get_parser(".pdf")
        text = parser.parse(self.test_data_dir / "sample.pdf")
        self.assertTrue(len(text) > 0)

    def test_docx_parser_returns_text(self):
        parser = self.factory.get_parser(".docx")
        text = parser.parse(self.test_data_dir / "sample.docx")
        self.assertTrue(len(text) > 0)

    def test_csv_parser_returns_text(self):
        parser = self.factory.get_parser(".csv")
        text = parser.parse(self.test_data_dir / "sample.csv")
        self.assertTrue(len(text) > 0)

    def test_json_parser_returns_text(self):
        parser = self.factory.get_parser(".json")
        text = parser.parse(self.test_data_dir / "sample.json")
        self.assertTrue(len(text) > 0)

    def test_md_parser_returns_text(self):
        parser = self.factory.get_parser(".md")
        text = parser.parse(self.test_data_dir / "sample.md")
        self.assertTrue(len(text) > 0)

    def test_unsupported_extension_raises(self):
        with self.assertRaises(UnsupportedFormatError):
            self.factory.get_parser(".xyz")