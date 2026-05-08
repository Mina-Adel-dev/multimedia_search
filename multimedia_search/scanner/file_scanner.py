"""Recursive file scanner with extension filtering."""

from pathlib import Path
from typing import Iterator, Optional, Set

from multimedia_search.config import SUPPORTED_EXTENSIONS


class FileScanner:
    """Scan directories recursively and yield files with supported extensions."""

    def __init__(self, extensions: Optional[Set[str]] = None):
        self.extensions = {ext.lower() for ext in (extensions or SUPPORTED_EXTENSIONS)}

    def is_image_sidecar(self, path: Path) -> bool:
        """
        Return True if this .txt file is a sidecar for an image with the same stem
        in the same directory.
        """
        if path.suffix.lower() != ".txt":
            return False

        image_exts = {".jpg", ".jpeg", ".png", ".webp"}
        for ext in image_exts:
            if path.with_suffix(ext).exists():
                return True
        return False

    def scan(self, directory: Path) -> Iterator[Path]:
        """
        Recursively walk directory and yield files with supported extensions.

        Skips:
        - temporary Office lock files like ~$file.docx
        - image sidecar .txt files like black_cat.txt when black_cat.jpg exists
        """
        if not directory.exists() or not directory.is_dir():
            return

        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith("~$"):
                continue
            if path.suffix.lower() not in self.extensions:
                continue
            if self.is_image_sidecar(path):
                continue
            yield path
