"""Parser for plain text files (.txt, .md)."""

from pathlib import Path
from .base import BaseParser

class TextParser(BaseParser):
    """Reads a text file as UTF-8."""

    def parse(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()