"""Configuration settings for the search engine."""

from pathlib import Path
import os
# File extensions to index
SUPPORTED_EXTENSIONS = {
    ".txt", ".pdf", ".docx", ".csv", ".json", ".md",
    ".jpg", ".jpeg", ".png", ".webp",
    ".mp3", ".wav", ".m4a", ".ogg", ".webm", ".mp4", ".mpeg", ".mpga", ".flac",
    ".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".mpg", ".mpeg", ".wmv",
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were",
    "will", "with"
}

IMAGE_OBJECT_DETECTION_ENABLED = True
IMAGE_OBJECT_DETECTION_MODEL = "yolo26n.pt"
IMAGE_OBJECT_DETECTION_CONFIDENCE = 0.35
IMAGE_OBJECT_DETECTION_MAX_LABELS = 8

IMAGE_OBJECT_DETECTION_USE_TILES = True
IMAGE_OBJECT_DETECTION_TILE_GRID = (2, 2)
IMAGE_OBJECT_DETECTION_TILE_OVERLAP = 0.20
IMAGE_OBJECT_DETECTION_TILE_MIN_SIZE = 160


AUDIO_TRANSCRIPTION_MODEL = os.getenv(
    "OPENAI_AUDIO_TRANSCRIPTION_MODEL",
    "gpt-4o-mini-transcribe",
)

AUDIO_ANALYSIS_MODEL = os.getenv(
    "OPENAI_AUDIO_ANALYSIS_MODEL",
    "gpt-5.1",
)

AUDIO_ANALYSIS_ENABLED = True
AUDIO_CACHE_ENABLED = True

VIDEO_CACHE_ENABLED = True
VIDEO_TRANSCRIPTION_ENABLED = True

SPELL_SUGGESTION_ENABLED = True
SPELL_SUGGESTION_CUTOFF = 0.82

SOUNDEX_SUGGESTION_ENABLED = True
SOUNDEX_MAX_CANDIDATES = 8

SYNONYM_EXPANSION_ENABLED = True
MAX_SYNONYMS_PER_TERM = 3

USE_STEMMING = False

INDEX_FILE = Path("index.pkl")
DATABASE_FILE = Path("multimedia_search.sqlite3")

SNIPPET_LENGTH = 150