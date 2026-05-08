"""Factory to dispatch parsers based on file extension."""

from multimedia_search.parsers.base import BaseParser
from multimedia_search.parsers.csv_parser import CSVParser
from multimedia_search.parsers.docx_parser import DOCXParser
from multimedia_search.parsers.image_parser import ImageParser
from multimedia_search.parsers.json_parser import JSONParser
from multimedia_search.parsers.md_parser import MarkdownParser
from multimedia_search.parsers.pdf_parser import PDFParser
from multimedia_search.parsers.text_parser import TextParser
from multimedia_search.utils.exceptions import UnsupportedFormatError
from multimedia_search.parsers.audio_parser import AudioParser


class ParserFactory:
    """Return appropriate parser for a given file extension."""

    _parsers = {
        ".txt": TextParser,
        ".pdf": PDFParser,
        ".docx": DOCXParser,
        ".csv": CSVParser,
        ".json": JSONParser,
        ".md": MarkdownParser,
        ".jpg": ImageParser,
        ".jpeg": ImageParser,
        ".png": ImageParser,
        ".webp": ImageParser,
        
        ".mp3": AudioParser,
        ".wav": AudioParser,
        ".m4a": AudioParser,
        ".ogg": AudioParser,
        ".webm": AudioParser,
        ".mp4": AudioParser,
        ".mpeg": AudioParser,
        ".mpga": AudioParser,
        ".flac": AudioParser,
    }

    @classmethod
    def get_parser(cls, extension: str) -> BaseParser:
        """
        Args:
            extension: File extension including the dot, for example '.pdf'.

        Returns:
            An instance of the parser for that extension.

        Raises:
            UnsupportedFormatError: if the extension is not supported.
        """
        parser_class = cls._parsers.get(extension.lower())
        if parser_class is None:
            raise UnsupportedFormatError(f"Unsupported extension: {extension}")
        return parser_class()