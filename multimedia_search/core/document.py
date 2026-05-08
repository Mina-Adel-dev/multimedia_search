"""Document data class."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class Document:
    """Represents a document to be indexed."""
    doc_id: int
    path: Path
    file_type: str
    raw_text: Optional[str] = None   # kept only for snippet generation
    tokens: Optional[List[str]] = None   # preprocessed tokens