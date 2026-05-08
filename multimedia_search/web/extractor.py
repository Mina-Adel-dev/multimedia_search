"""Extract visible text and title from HTML."""

from html.parser import HTMLParser
from typing import Dict, List

class _TextExtractor(HTMLParser):
    """Simple HTML parser that collects visible text and title."""
    def __init__(self):
        super().__init__()
        self.text_parts: List[str] = []
        self.title = ""
        self.in_title = False
        self.in_script = False
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            if tag == 'script':
                self.in_script = True
            else:
                self.in_style = True
        elif tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            if tag == 'script':
                self.in_script = False
            else:
                self.in_style = False
        elif tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data.strip()
        elif not self.in_script and not self.in_style:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)

    def get_text(self) -> str:
        return ' '.join(self.text_parts)

def extract(html: str) -> Dict[str, str]:
    """
    Extract title and visible text from HTML.
    Returns dict with keys: 'title', 'text'.
    """
    parser = _TextExtractor()
    parser.feed(html)
    return {
        'title': parser.title,
        'text': parser.get_text()
    }