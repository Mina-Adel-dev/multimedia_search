"""Parser for DOCX files using python-docx."""

from pathlib import Path
from docx import Document
from .base import BaseParser

class DOCXParser(BaseParser):
    """Extract text from a Word document."""

    def parse(self, file_path: Path) -> str:
        doc = Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        return "\n".join(paragraphs)