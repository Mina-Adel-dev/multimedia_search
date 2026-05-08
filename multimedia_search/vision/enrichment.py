from pathlib import Path

from multimedia_search.vision.object_detector import ObjectDetector

_DETECTOR = None


def _get_detector() -> ObjectDetector:
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = ObjectDetector()
    return _DETECTOR


def enrich_image_raw_text(file_path: Path, raw_text: str) -> str:
    """
    Append detected object labels to image raw_text.

    This keeps the rest of the system unchanged:
    parser -> raw_text -> tokens -> index
    """
    detector = _get_detector()
    detection_text = detector.build_detection_text(file_path)

    if not detection_text:
        return raw_text.strip()

    if not raw_text.strip():
        return detection_text

    return f"{raw_text.strip()} {detection_text}".strip()