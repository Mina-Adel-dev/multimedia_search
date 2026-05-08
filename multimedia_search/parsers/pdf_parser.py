"""Parser for PDF files using pypdf."""

from pathlib import Path
from pypdf import PdfReader
from .base import BaseParser

class PDFParser(BaseParser):
    """Extract text from PDF using pypdf."""

    def parse(self, file_path: Path) -> str:
        reader = PdfReader(str(file_path))
        text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
        return "\n".join(text)