"""Abstract base class for all parsers."""

from abc import ABC, abstractmethod
from pathlib import Path

class BaseParser(ABC):
    """All parsers must implement `parse` to extract text from a file."""

    @abstractmethod
    def parse(self, file_path: Path) -> str:
        """Extract and return raw text from the given file."""
        pass