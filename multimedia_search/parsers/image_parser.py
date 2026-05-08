from pathlib import Path

from PIL import Image, UnidentifiedImageError, ExifTags

from multimedia_search.parsers.base import BaseParser


class ImageParser(BaseParser):
    """
    Parser for image files.

    Returns searchable text built from:
    - nearest parent folder names
    - filename stem
    - normalized stem variants
    - optional sidecar .txt content with the same stem
    - verified image metadata extracted from the actual file content
      (format, width, height, mode, selected EXIF fields)

    Important:
    - routing may still begin by extension in ParserFactory
    - but this parser verifies the file is a real image by content
    """

    _SAFE_EXIF_FIELDS = {
        "Make",
        "Model",
        "DateTime",
        "DateTimeOriginal",
        "Software",
        "Artist",
        "ImageDescription",
    }

    def parse(self, file_path: Path) -> str:
        """
        Parse an image file into searchable text.

        Raises:
            ValueError: if the file is not a valid image or cannot be read
        """
        file_path = Path(file_path)

        path_text = self._build_path_text(file_path)
        sidecar_text = self._read_sidecar_text(file_path)
        image_metadata_text = self._extract_image_metadata_text(file_path)

        parts = [
            path_text,
            image_metadata_text,
            sidecar_text,
        ]

        return " ".join(part for part in parts if part).strip()

    def _build_path_text(self, file_path: Path) -> str:
        """Build searchable text from nearby folders and filename."""
        parent_parts = [
            part for part in file_path.parent.parts
            if part and part not in ("/", "\\")
        ]
        folder_parts = parent_parts[-3:]  # keep nearest 3 folders only

        stem = file_path.stem.strip()
        normalized_stem = stem.replace("_", " ").replace("-", " ").strip()

        path_text_parts = folder_parts + [stem]
        if normalized_stem and normalized_stem != stem:
            path_text_parts.append(normalized_stem)

        return " ".join(part for part in path_text_parts if part).strip()

    def _read_sidecar_text(self, file_path: Path) -> str:
        """Read optional same-stem .txt caption/description file."""
        sidecar_path = file_path.with_suffix(".txt")
        if not sidecar_path.exists() or not sidecar_path.is_file():
            return ""

        try:
            return sidecar_path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return ""

    def _extract_image_metadata_text(self, file_path: Path) -> str:
        """
        Verify the file is a real image and extract safe searchable metadata.

        Uses Pillow to open and identify the image from file content.
        """
        try:
            with Image.open(file_path) as verify_img:
                verify_img.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(f"Invalid or unreadable image file: {file_path}") from exc

        try:
            with Image.open(file_path) as img:
                metadata_parts = []

                image_format = (img.format or "").strip().lower()
                if image_format:
                    metadata_parts.append(f"format {image_format}")

                width, height = img.size
                metadata_parts.append(f"width {width}")
                metadata_parts.append(f"height {height}")

                mode = (img.mode or "").strip().lower()
                if mode:
                    metadata_parts.append(f"mode {mode}")

                exif = self._extract_safe_exif(img)
                if exif:
                    metadata_parts.append(exif)

                return " ".join(metadata_parts).strip()

        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(f"Failed to read image metadata: {file_path}") from exc

    def _extract_safe_exif(self, img: Image.Image) -> str:
        """Extract only a small safe subset of EXIF fields."""
        try:
            exif = img.getexif()
        except Exception:
            return ""

        if not exif:
            return ""

        parts = []

        for tag_id, value in exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            if tag_name not in self._SAFE_EXIF_FIELDS:
                continue

            normalized_value = self._normalize_exif_value(value)
            if not normalized_value:
                continue

            parts.append(f"{tag_name.lower()} {normalized_value}")

        return " ".join(parts).strip()

    def _normalize_exif_value(self, value) -> str:
        """Convert EXIF values into compact searchable text."""
        if value is None:
            return ""

        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8", errors="ignore")
            except Exception:
                return ""

        text = str(value).strip()
        if not text:
            return ""

        text = text.replace(":", " ")
        text = text.replace("_", " ")
        text = text.replace("-", " ")
        return " ".join(text.split())