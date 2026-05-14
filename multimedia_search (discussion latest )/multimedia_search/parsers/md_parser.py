"""Parser for Markdown files (treated as plain text)."""

from pathlib import Path

from multimedia_search.parsers.text_parser import TextParser
class MarkdownParser(TextParser):
    """Markdown is handled as plain text."""
    pass