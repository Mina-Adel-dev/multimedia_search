"""Parser for JSON files."""

import json
from pathlib import Path
from typing import Any
from .base import BaseParser

class JSONParser(BaseParser):
    """Flatten JSON recursively into a space-separated string."""

    def _flatten(self, obj: Any, path: str = "") -> str:
        if isinstance(obj, dict):
            parts = []
            for k, v in obj.items():
                parts.append(self._flatten(v, f"{path}.{k}" if path else k))
            return " ".join(parts)
        elif isinstance(obj, list):
            return " ".join(self._flatten(item, f"{path}[]") for item in obj)
        else:
            # Convert to string, ignore None
            return str(obj) if obj is not None else ""

    def parse(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        return self._flatten(data)