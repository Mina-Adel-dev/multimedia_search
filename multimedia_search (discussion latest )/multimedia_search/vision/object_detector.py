from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from PIL import Image

from multimedia_search.config import (
    IMAGE_OBJECT_DETECTION_CONFIDENCE,
    IMAGE_OBJECT_DETECTION_ENABLED,
    IMAGE_OBJECT_DETECTION_MAX_LABELS,
    IMAGE_OBJECT_DETECTION_MODEL,
    IMAGE_OBJECT_DETECTION_TILE_GRID,
    IMAGE_OBJECT_DETECTION_TILE_MIN_SIZE,
    IMAGE_OBJECT_DETECTION_TILE_OVERLAP,
    IMAGE_OBJECT_DETECTION_USE_TILES,
)
from multimedia_search.vision.types import DetectedObject


class ObjectDetector:
    """
    Thin wrapper around a pretrained detector.

    Design:
    - detection happens at indexing time
    - full-image detection runs first
    - optional overlapping tile detection runs second
    - detected labels are merged and appended into raw_text
    """

    def __init__(
        self,
        enabled: bool = IMAGE_OBJECT_DETECTION_ENABLED,
        model_name: str = IMAGE_OBJECT_DETECTION_MODEL,
        confidence: float = IMAGE_OBJECT_DETECTION_CONFIDENCE,
        max_labels: int = IMAGE_OBJECT_DETECTION_MAX_LABELS,
        use_tiles: bool = IMAGE_OBJECT_DETECTION_USE_TILES,
        tile_grid: Tuple[int, int] = IMAGE_OBJECT_DETECTION_TILE_GRID,
        tile_overlap: float = IMAGE_OBJECT_DETECTION_TILE_OVERLAP,
        tile_min_size: int = IMAGE_OBJECT_DETECTION_TILE_MIN_SIZE,
    ) -> None:
        self.enabled = enabled
        self.model_name = model_name
        self.confidence = confidence
        self.max_labels = max_labels
        self.use_tiles = use_tiles
        self.tile_grid = tile_grid
        self.tile_overlap = tile_overlap
        self.tile_min_size = tile_min_size

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_model(model_name: str):
        from ultralytics import YOLO

        return YOLO(model_name)

    def detect(self, image_path: Path) -> List[DetectedObject]:
        """
        Run detection on the full image and optional overlapping tiles.

        Returns merged unique labels with best confidence per label.
        """
        if not self.enabled:
            return []

        image_path = Path(image_path)

        full_detections = self._predict_source(str(image_path))
        if not self.use_tiles:
            return self._merge_detections(full_detections)

        tile_detections: List[DetectedObject] = []
        try:
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                for tile in self._generate_tiles(image):
                    tile_detections.extend(self._predict_source(tile))
        except Exception:
            pass

        return self._merge_detections(full_detections + tile_detections)

    def build_detection_text(self, image_path: Path) -> str:
        """
        Convert detections into searchable text.
        Example: 'dog animal sofa'
        """
        detections = self.detect(image_path)
        if not detections:
            return ""

        return " ".join(item.label for item in detections).strip()

    def _predict_source(self, source) -> List[DetectedObject]:
        """
        Predict labels from either:
        - a file path string
        - a PIL image object
        """
        if not self.enabled:
            return []

        try:
            model = self._load_model(self.model_name)
        except Exception:
            return []

        try:
            results = model.predict(
                source=source,
                conf=self.confidence,
                verbose=False,
            )
        except Exception:
            return []

        if not results:
            return []

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        cls_values = getattr(boxes, "cls", None)
        conf_values = getattr(boxes, "conf", None)
        if cls_values is None or conf_values is None:
            return []

        if hasattr(cls_values, "tolist"):
            cls_values = cls_values.tolist()
        else:
            cls_values = list(cls_values)

        if hasattr(conf_values, "tolist"):
            conf_values = conf_values.tolist()
        else:
            conf_values = list(conf_values)

        names = getattr(result, "names", {}) or {}

        detections: List[DetectedObject] = []

        for cls_id, conf in zip(cls_values, conf_values):
            try:
                label = names.get(int(cls_id), str(int(cls_id)))
            except Exception:
                label = str(cls_id)

            normalized_label = self._normalize_label(label)
            if not normalized_label:
                continue

            detections.append(
                DetectedObject(
                    label=normalized_label,
                    confidence=float(conf),
                )
            )

        return detections

    def _merge_detections(self, detections: Iterable[DetectedObject]) -> List[DetectedObject]:
        """
        Keep only the best confidence per label.
        """
        best_by_label: Dict[str, float] = {}

        for item in detections:
            if not item.label:
                continue

            best = best_by_label.get(item.label)
            if best is None or item.confidence > best:
                best_by_label[item.label] = item.confidence

        merged = [
            DetectedObject(label=label, confidence=confidence)
            for label, confidence in best_by_label.items()
        ]
        merged.sort(key=lambda x: (-x.confidence, x.label))
        return merged[: self.max_labels]

    def _generate_tiles(self, image: Image.Image) -> List[Image.Image]:
        """
        Generate overlapping tiles from the image.

        Example:
        - grid (2, 2) gives 4 tiles
        - overlap 0.20 means 20% overlap between neighboring tiles
        """
        width, height = image.size
        rows, cols = self.tile_grid

        if rows <= 0 or cols <= 0:
            return []

        if width < self.tile_min_size or height < self.tile_min_size:
            return []

        base_tile_w = max(1, width // cols)
        base_tile_h = max(1, height // rows)

        overlap_w = int(base_tile_w * self.tile_overlap)
        overlap_h = int(base_tile_h * self.tile_overlap)

        tiles: List[Image.Image] = []

        for row in range(rows):
            for col in range(cols):
                left = max(0, col * base_tile_w - overlap_w)
                top = max(0, row * base_tile_h - overlap_h)

                right = min(width, (col + 1) * base_tile_w + overlap_w)
                bottom = min(height, (row + 1) * base_tile_h + overlap_h)

                if right <= left or bottom <= top:
                    continue

                tile = image.crop((left, top, right, bottom))
                tiles.append(tile)

        return tiles

    @staticmethod
    def _normalize_label(label: str) -> str:
        text = str(label).strip().lower()
        if not text:
            return ""

        text = text.replace("_", " ")
        text = text.replace("-", " ")
        return " ".join(text.split())