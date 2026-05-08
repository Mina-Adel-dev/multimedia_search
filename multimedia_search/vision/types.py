from dataclasses import dataclass


@dataclass(frozen=True)
class DetectedObject:
    """One detected object label with confidence."""
    label: str
    confidence: float