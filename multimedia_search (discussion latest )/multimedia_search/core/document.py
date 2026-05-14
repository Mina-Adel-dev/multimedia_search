"""Document data class."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Document:
    """Represents a document to be indexed."""

    doc_id: int
    path: Path
    file_type: str
    raw_text: Optional[str] = None
    tokens: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None