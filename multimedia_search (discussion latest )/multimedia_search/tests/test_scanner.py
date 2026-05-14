import tempfile
import unittest
from pathlib import Path

from multimedia_search.scanner.file_scanner import FileScanner


class TestFileScanner(unittest.TestCase):
    def test_scanner_finds_supported_files(self):
        scanner = FileScanner()

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            supported_files = [
                "sample.txt",
                "sample.pdf",
                "sample.docx",
                "sample.csv",
                "sample.json",
                "sample.md",
                "image.jpg",
            ]

            for name in supported_files:
                (base / name).write_text("x", encoding="utf-8")

            # Sidecar for image.jpg -> should be skipped by scanner
            (base / "image.txt").write_text("sidecar caption", encoding="utf-8")

            # Unsupported file
            (base / "ignore.exe").write_text("x", encoding="utf-8")

            found_files = {p.name for p in scanner.scan(base)}

            expected_files = {
                "sample.txt",
                "sample.pdf",
                "sample.docx",
                "sample.csv",
                "sample.json",
                "sample.md",
                "image.jpg",
            }

            self.assertEqual(found_files, expected_files)
            self.assertNotIn("image.txt", found_files)
            self.assertNotIn("ignore.exe", found_files)
