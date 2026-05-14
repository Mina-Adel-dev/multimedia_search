"""Deterministic image feature extraction for visual similarity search."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError


@dataclass(frozen=True)
class ImageFeatures:
    """Small, deterministic visual feature bundle for one image."""

    average_rgb: Tuple[float, float, float]
    thumbnail: Tuple[float, ...]
    color_histogram: Tuple[float, ...]


def _get_resample_filter():
    """Return a Pillow resize filter compatible with older/newer Pillow versions."""
    resampling = getattr(Image, "Resampling", None)
    if resampling is not None:
        return resampling.BILINEAR
    return Image.BILINEAR


def extract_image_features(
    image_path: Path | str,
    thumbnail_size: tuple[int, int] = (8, 8),
    histogram_bins: int = 8,
) -> ImageFeatures:
    """
    Extract simple visual features from an image.

    The features are intentionally lightweight and deterministic:
    - average RGB color
    - small grayscale thumbnail vector
    - per-channel RGB color histogram

    Raises:
        ValueError: if the path is invalid or the image cannot be read.
    """
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"Image file not found: {path}")

    if thumbnail_size[0] <= 0 or thumbnail_size[1] <= 0:
        raise ValueError("thumbnail_size values must be positive")

    if histogram_bins <= 0 or 256 % histogram_bins != 0:
        raise ValueError("histogram_bins must be a positive divisor of 256")

    try:
        with Image.open(path) as img:
            rgb_image = img.convert("RGB")
            rgb_image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Invalid or unreadable image file: {path}") from exc

    average_rgb = _extract_average_rgb(rgb_image)
    thumbnail = _extract_thumbnail_vector(rgb_image, thumbnail_size)
    histogram = _extract_color_histogram(rgb_image, histogram_bins)

    return ImageFeatures(
        average_rgb=average_rgb,
        thumbnail=thumbnail,
        color_histogram=histogram,
    )


def compare_image_features(left: ImageFeatures, right: ImageFeatures) -> float:
    """
    Return a visual similarity score in the range [0, 1].

    1.0 means nearly identical according to these simple features.
    """
    average_score = _normalized_euclidean_similarity(left.average_rgb, right.average_rgb)
    thumbnail_score = _normalized_euclidean_similarity(left.thumbnail, right.thumbnail)
    histogram_score = _histogram_intersection(left.color_histogram, right.color_histogram)

    score = (0.45 * average_score) + (0.10 * thumbnail_score) + (0.45 * histogram_score)
    return max(0.0, min(1.0, score))


def _extract_average_rgb(image: Image.Image) -> Tuple[float, float, float]:
    """Return average RGB values normalized to [0, 1]."""
    stat = ImageStat.Stat(image)
    means = stat.mean[:3]
    return tuple(float(value) / 255.0 for value in means)  # type: ignore[return-value]


def _extract_thumbnail_vector(
    image: Image.Image,
    thumbnail_size: tuple[int, int],
) -> Tuple[float, ...]:
    """Return a normalized grayscale thumbnail vector."""
    gray = ImageOps.grayscale(image)
    thumb = gray.resize(thumbnail_size, _get_resample_filter())

    get_pixels = getattr(thumb, "get_flattened_data", None)
    pixels = get_pixels() if get_pixels is not None else thumb.getdata()

    return tuple(float(value) / 255.0 for value in pixels)


def _extract_color_histogram(image: Image.Image, bins: int) -> Tuple[float, ...]:
    """Return a normalized RGB histogram with `bins` buckets per channel."""
    step = 256 // bins
    values = []

    for channel in image.split():
        histogram = channel.histogram()
        total = float(sum(histogram)) or 1.0

        for start in range(0, 256, step):
            values.append(sum(histogram[start:start + step]) / total)

    return tuple(values)


def _normalized_euclidean_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    """Compute 1 - normalized Euclidean distance for vectors in [0, 1]."""
    left_values = tuple(float(value) for value in left)
    right_values = tuple(float(value) for value in right)

    if len(left_values) != len(right_values) or not left_values:
        return 0.0

    distance = math.sqrt(
        sum((l_value - r_value) ** 2 for l_value, r_value in zip(left_values, right_values))
    )

    max_distance = math.sqrt(len(left_values))
    if max_distance == 0:
        return 0.0

    return max(0.0, min(1.0, 1.0 - (distance / max_distance)))


def _histogram_intersection(left: Iterable[float], right: Iterable[float]) -> float:
    """Compute normalized histogram intersection for RGB channel histograms."""
    left_values = tuple(float(value) for value in left)
    right_values = tuple(float(value) for value in right)

    if len(left_values) != len(right_values) or not left_values:
        return 0.0

    # Each channel histogram is normalized to sum to 1.0, so RGB sums to 3.0.
    total = sum(left_values) or 1.0
    return max(0.0, min(1.0, sum(min(l, r) for l, r in zip(left_values, right_values)) / total))