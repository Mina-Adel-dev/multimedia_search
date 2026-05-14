import io
import html
import hashlib
import json
import logging
import os
import pickle
import re
import socket
import subprocess
import sys
import threading
import time
import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from urllib.parse import quote_plus

import librosa
import numpy as np
import requests
import soundfile as sf
from flask import Flask, Response, jsonify, render_template, request
from werkzeug.utils import secure_filename

###############################################################################
# Configuration
###############################################################################

DEFAULT_SONGS_DIR = Path(r"D:\Music\new")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
FEATURE_CACHE_FILE = Path("feature_cache.pkl")
FEATURE_CACHE_VERSION = 6
LYRICS_OVERRIDE_FILE = Path("lyrics_overrides.json")
DEFAULT_SHAZAM_LYRICS_OVERRIDES = {
    "sandra haj yama nefsi haolak": (
        "https://www.shazam.com/song/1830970751/"
        "%D9%8A%D8%A7%D9%85%D8%A7-%D9%86%D9%81%D8%B3-%D8%A7%D9%82%D9%88%D9%84%D9%83"
    )
}

SAMPLE_RATE = 22050
N_MFCC = 13
N_CHROMA = 12
SEQUENCE_N_MFCC = 8
MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB upload limit

# Multi-window indexing for better coverage with practical indexing speed.
INDEX_AUDIO_DURATION_SECONDS: Optional[float] = None
QUERY_AUDIO_DURATION_SECONDS = 60
INDEX_WINDOW_SECONDS = 70.0
INDEX_MULTI_WINDOW_THRESHOLD_SECONDS = 160.0

# Segment matching improves robustness for partial queries.
SEGMENT_DURATION_SECONDS = 6
SEGMENT_HOP_SECONDS = 3
MAX_SEGMENTS_PER_TRACK = 30

# Retrieval optimization: shortlist by global score before segment rerank.
SHORTLIST_MULTIPLIER = 6
MIN_SHORTLIST = 25
SEQUENCE_RERANK_LIMIT = 12
SEGMENT_SCALER_SAMPLE_PER_TRACK = 8

# Frame-sequence matching (DTW reranking).
SEQUENCE_HOP_LENGTH = 1024
SEQUENCE_POOL_SIZE = 8
SEQUENCE_HOP_SECONDS = (SEQUENCE_HOP_LENGTH * SEQUENCE_POOL_SIZE) / SAMPLE_RATE
MAX_QUERY_SEQUENCE_SECONDS = 40.0

# Landmark fingerprinting: a Shazam-like offset-voting layer.
FINGERPRINT_N_FFT = 2048
FINGERPRINT_HOP_LENGTH = 512
FINGERPRINT_MIN_FREQ_BIN = 8
FINGERPRINT_MAX_FREQ_BIN = 512
FINGERPRINT_FREQ_QUANT = 2
FINGERPRINT_PEAK_NEIGHBORHOOD = (15, 11)
FINGERPRINT_PEAK_DB_THRESHOLD = -42.0
FINGERPRINT_MAX_PEAKS_PER_FRAME = 3
FINGERPRINT_TARGET_MIN_DELTA = 3
FINGERPRINT_TARGET_MAX_DELTA = 65
FINGERPRINT_TARGET_FANOUT = 4
FINGERPRINT_OFFSET_BUCKET_FRAMES = 3
FINGERPRINT_MAX_HASHES_PER_TRACK = 80000
FINGERPRINT_MIN_ALIGNED_MATCHES = 18
FINGERPRINT_MIN_QUERY_COVERAGE = 0.012
FINGERPRINT_PROMOTION_SCORE = 0.82
LIVE_EXHAUSTIVE_SEQUENCE_TOP_K = 10
LIVE_SEQUENCE_PROMOTION_MIN_DTW = 0.72
LIVE_SEQUENCE_PROMOTION_MIN_DTW_GAP = 0.025
LIVE_SEQUENCE_PROMOTION_BONUS = 0.06

# Snippet playback limits (innovation feature: no upload needed).
MAX_SNIPPET_DURATION_SECONDS = 20.0

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".webm", ".mp4", ".aac"}
LYRIC_EXTENSIONS = (".lrc", ".txt")
LYRICS_HTTP_TIMEOUT_SECONDS = 8
METADATA_ANALYSIS_SECONDS = 45
NOTE_NAMES = ["C", "C#/Db", "D", "D#/Eb", "E", "F", "F#/Gb", "G", "G#/Ab", "A", "A#/Bb", "B"]
LOCAL_MIN_CONFIDENCE_FOR_FINAL = 0.6
LOCAL_MIN_SCORE_FOR_FINAL = 0.58
DETECTION_REJECT_UNCERTAIN_MATCHES = True
RELIABLE_MATCH_MIN_SCORE = 0.50
RELIABLE_MATCH_MIN_DTW = 0.70
RELIABLE_MATCH_MIN_MARGIN = 0.12
STRONG_MATCH_MIN_SCORE = 0.74
STRONG_MATCH_MIN_DTW = 0.70
STRONG_MATCH_MIN_MARGIN = 0.025
LIVE_MIN_MARGIN_FOR_ACCEPT = 0.06
LIVE_MIN_DTW_FOR_ACCEPT = 0.60
LIVE_TOP_MATCH_MIN_SCORE_FOR_ACCEPT = 0.65
LIVE_TOP_MATCH_MIN_DTW_FOR_ACCEPT = 0.65
LIVE_TOP_MATCH_MIN_MARGIN_FOR_ACCEPT = 0.05
LIVE_LOW_SCORE_MIN_DTW_FOR_ACCEPT = 0.66
LIVE_MIN_CONSENSUS_FOR_ACCEPT = 1.10
LIVE_LOW_SCORE_MIN_MARGIN_FOR_ACCEPT = 0.12
SHAZAM_FALLBACK_ENABLED = True
YTMUSIC_PROVIDER_ENABLED = True
YTMUSIC_QUERY_LIMIT = 3
YTMUSIC_SEARCH_LIMIT = 6
LIVE_QUERY_OFFSET_SECONDS = 0.35
LIVE_FOCUS_WINDOW_SECONDS = 8.0
LIVE_FOCUS_MIN_SECONDS = 3.0
LIVE_VARIANT_OFFSET_SECONDS = 0.5
LIVE_VARIANT_MIN_SECONDS = 2.5
LIVE_CONSENSUS_TOP_CANDIDATES = 5
LIVE_VARIANT_TOP_K = 25
LIVE_DTW_RESCUE_MIN_ABS = 0.66
LIVE_DTW_RESCUE_MIN_GAP = 0.08
LIVE_DTW_RESCUE_MAX_SCORE_GAP = 0.18
LIVE_DTW_RESCUED_MIN_ACCEPT = 0.74
LIVE_DTW_RESCUE_STRONG_ABS = 0.80
LIVE_DTW_RESCUE_STRONG_MIN_GAP = 0.03
LIVE_DTW_RESCUE_STRONG_MAX_SCORE_GAP = 0.22
LIVE_DTW_RESCUE_BONUS = 0.05
LIVE_PROMOTION_MIN_DTW = 0.70
LIVE_PROMOTION_MIN_EVIDENCE = 0.58
LIVE_PROMOTION_MIN_EVIDENCE_GAP = 0.015
LIVE_PROMOTION_MIN_DTW_GAP = 0.055
LYRICS_MIN_TOKEN_OVERLAP_NO_ARTIST = 0.72
LYRICS_MIN_TOKEN_OVERLAP = 0.42
LYRICS_MIN_TITLE_SCORE = 0.45
LYRICS_SEARCH_CANDIDATE_LIMIT = 10
LYRICS_VARIANT_TOKENS = {
    "acoustic",
    "calmer",
    "cover",
    "epic",
    "feat",
    "featuring",
    "ft",
    "instrumental",
    "karaoke",
    "live",
    "matrimonio",
    "remix",
    "salsa",
    "slowed",
    "sped",
    "version",
}
LYRICS_NOISE_TOKENS = {
    "official",
    "music",
    "video",
    "audio",
    "lyrics",
    "lyric",
    "paroles",
    "karaoke",
    "instrumental",
    "visualizer",
    "version",
    "cover",
    "remix",
    "live",
    "feat",
    "featuring",
    "ft",
    "clip",
    "hq",
    "hd",
    "mp3",
    "m4a",
    "aac",
    "wav",
    "flac",
    "webm",
    "mp4",
    "y2mate",
    "com",
    "كلمات",
    "اغنية",
    "أغنية",
    "ترنيمة",
    "حصريا",
    "رسمي",
    "فيديو",
}


###############################################################################
# Application setup
###############################################################################

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


@dataclass
class SongRecord:
    file_path: Path
    relative_name: str
    duration_sec: float
    global_feature: np.ndarray
    segment_features: np.ndarray  # shape: (num_segments, feature_dim)
    sequence_features: np.ndarray  # shape: (num_frames, frame_feature_dim)
    lyrics: Optional[str]
    tempo_bpm: float
    key_label: str
    energy: float
    file_sha1: str
    fingerprint_hashes: np.ndarray
    fingerprint_frames: np.ndarray


# Mutable in-memory retrieval state.
song_index: Dict[str, SongRecord] = {}
song_names: List[str] = []  # order aligned with global_feature_matrix
global_feature_matrix = np.empty((0, 0), dtype=np.float32)
scoring_global_feature_matrix = np.empty((0, 0), dtype=np.float32)
global_feature_mean = np.empty((0,), dtype=np.float32)
global_feature_std = np.empty((0,), dtype=np.float32)
segment_feature_mean = np.empty((0,), dtype=np.float32)
segment_feature_std = np.empty((0,), dtype=np.float32)
segment_feature_matrix_by_song: Dict[str, np.ndarray] = {}
song_hash_lookup: Dict[str, str] = {}
fingerprint_lookup: Dict[int, List[Tuple[str, int]]] = {}
lyrics_cache: Dict[str, Dict[str, str]] = {}
ffmpeg_bootstrap_attempted = False
ytmusic_client: Optional[Any] = None
ytmusic_disabled = False

current_source_dir: Path = DEFAULT_SONGS_DIR
index_stats = {
    "source_dir": str(DEFAULT_SONGS_DIR),
    "recursive": True,
    "scanned_files": 0,
    "indexed_songs": 0,
    "failed_files": 0,
    "lyrics_found": 0,
    "cache_hits": 0,
    "feature_dim": 0,
    "duration_sec": 0.0,
    "last_error": "",
}
index_lock = threading.Lock()
index_bootstrap_attempted = False


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    """L2-normalize a vector (safe for near-zero vectors)."""
    norm = np.linalg.norm(vector)
    if norm <= 1e-12:
        return vector
    return vector / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for normalized vectors (dot product)."""
    return float(np.dot(a, b))


def is_allowed_extension(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS


def clamp_float(raw_value: str, default: float, low: float, high: float) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return default
    return float(min(max(value, low), high))


def clamp_top_k(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 5
    return max(1, min(value, 10))


def infer_audio_extension(filename: str, mimetype: str) -> str:
    """Infer robust extension for uploaded blobs (e.g., MediaRecorder blobs)."""
    suffix = Path(filename or "").suffix.lower()
    if suffix:
        return suffix

    mime = (mimetype or "").lower()
    mapping = {
        "audio/webm": ".webm",
        "audio/mp4": ".mp4",
        "audio/x-m4a": ".m4a",
        "audio/m4a": ".m4a",
        "audio/aac": ".aac",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/ogg": ".ogg",
        "audio/flac": ".flac",
    }
    for key, value in mapping.items():
        if key in mime:
            return value
    return ".wav"


def read_text_file(path: Path) -> str:
    """Read text with tolerant decoding."""
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def load_lyrics_for_audio(audio_path: Path) -> Optional[str]:
    """Load sidecar lyrics file with same basename (.lrc or .txt)."""
    for ext in LYRIC_EXTENSIONS:
        candidate = audio_path.with_suffix(ext)
        if candidate.exists() and candidate.is_file():
            content = read_text_file(candidate)
            if content:
                return content
    return None


def load_feature_cache() -> dict:
    """Load feature cache from disk if present and compatible."""
    if not FEATURE_CACHE_FILE.exists():
        return {"version": FEATURE_CACHE_VERSION, "songs": {}}
    try:
        with FEATURE_CACHE_FILE.open("rb") as fh:
            cache = pickle.load(fh)
        if not isinstance(cache, dict):
            raise ValueError("cache root is not dict")
        if cache.get("version") != FEATURE_CACHE_VERSION:
            return {"version": FEATURE_CACHE_VERSION, "songs": {}}
        songs = cache.get("songs", {})
        if not isinstance(songs, dict):
            songs = {}
        return {"version": FEATURE_CACHE_VERSION, "songs": songs}
    except Exception:
        logger.warning("Feature cache could not be read. Rebuilding from audio files.")
        return {"version": FEATURE_CACHE_VERSION, "songs": {}}


def save_feature_cache(cache: dict) -> None:
    """Persist feature cache to disk (best-effort)."""
    try:
        with FEATURE_CACHE_FILE.open("wb") as fh:
            pickle.dump(cache, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        logger.warning("Feature cache save failed: %s", exc)


def trim_lyrics(text: Optional[str], max_lines: int = 18, max_chars: int = 1800) -> str:
    """Keep lyrics preview compact for UI/plain output."""
    if not text:
        return ""

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    clipped = "\n".join(lines[:max_lines]).strip()
    if len(clipped) > max_chars:
        clipped = clipped[:max_chars].rstrip() + " ..."
    return clipped


def compact_log_text(value: str, max_chars: int = 600) -> str:
    """Keep provider debug logs readable without dumping huge responses."""
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + " ..."
    return text


def has_arabic_text(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def extract_arabic_words(text: str) -> List[str]:
    return re.findall(r"[\u0600-\u06FF]+", text or "")


def remove_arabic_text(text: str) -> str:
    return re.sub(r"[\u0600-\u06FF]+", " ", text or "")


def cleanup_query_text(text: str) -> str:
    """Normalize filename/song text for better online lookup."""
    value = Path(str(text)).name
    value = re.sub(r"(?i)\.(?:mp3|m4a|aac|wav|flac|webm|mp4|ogg)$", " ", value)
    value = Path(value).stem
    value = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", value)
    value = value.replace("_", " ").replace("|", " ").replace("/", " ")
    value = re.sub(r"[‐‑‒–—−]+", "-", value)
    value = re.sub(
        r"(?i)\b(?:mp3|m4a|aac|wav|flac|webm|mp4)\s*[-_ ]?\s*\d{2,4}k\b",
        " ",
        value,
    )
    value = re.sub(r"(?i)\b(?:\d{2,4}k|y2mate(?:\.com)?)\b", " ", value)
    value = re.sub(
        r"(?i)\b(?:official|music|video|audio|lyrics?|paroles|visualizer|clip|hq|hd)\b",
        " ",
        value,
    )
    value = re.sub(r"\s*-\s*", " - ", value)
    value = re.sub(r"(?:\s+-\s+){2,}", " - ", value)
    value = re.sub(r"\s+", " ", value).strip(" -")
    return value


def split_dash_parts(text: str) -> List[str]:
    """Split artist/title sections after filename dash normalization."""
    return [part.strip(" -") for part in re.split(r"\s+-\s+", text or "") if part.strip(" -")]


def infer_arabic_artist_title(cleaned_name: str, latin_title_hint: str = "") -> Tuple[Optional[str], Optional[str]]:
    """
    Infer Arabic title/artist from mixed filenames such as:
    "abdulrahman mohammed - khalid barzanji - kolo laha قولو لها عبدالرحمن محمد".

    The romanized title token count is used as a safe split point for the Arabic
    phrase, so "kolo laha" maps to the first two Arabic words: "قولو لها".
    """
    arabic_words = extract_arabic_words(cleaned_name)
    if len(arabic_words) < 2:
        return None, None

    latin_hint = remove_arabic_text(latin_title_hint)
    latin_title_words = re.findall(r"[0-9A-Za-z]+", latin_hint)
    if not latin_title_words:
        latin_title_words = re.findall(r"[0-9A-Za-z]+", remove_arabic_text(cleaned_name))

    title_word_count = max(1, min(len(latin_title_words), 4))
    if len(arabic_words) <= title_word_count:
        return None, " ".join(arabic_words)

    arabic_title = " ".join(arabic_words[:title_word_count]).strip()
    arabic_artist = " ".join(arabic_words[title_word_count:]).strip()
    if arabic_title and arabic_artist:
        return arabic_artist, arabic_title
    return None, arabic_title or None


def lyrics_http_get(provider: str, url: str, headers: Optional[dict] = None) -> Optional[requests.Response]:
    """GET wrapper that logs request URLs and compact response details."""
    logger.info("Lyrics API request | provider=%s url=%s", provider, url)
    try:
        response = requests.get(url, headers=headers, timeout=LYRICS_HTTP_TIMEOUT_SECONDS)
        logger.info(
            "Lyrics API response | provider=%s status=%s body=%s",
            provider,
            response.status_code,
            compact_log_text(response.text),
        )
        return response
    except Exception as exc:
        logger.warning("Lyrics API request failed | provider=%s url=%s error=%s", provider, url, exc)
        return None


def normalize_lookup_text(text: str) -> str:
    """Normalize text key for fuzzy override matching."""
    cleaned = cleanup_query_text(text).lower()
    cleaned = re.sub(r"[^0-9a-z\u0600-\u06FF\s]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def tokenize_lookup_text(text: str) -> List[str]:
    """Split normalized lookup text into simple matching tokens."""
    tokens: List[str] = []
    seen = set()
    for token in normalize_lookup_text(text).split():
        if len(token) < 2:
            continue
        if token in LYRICS_NOISE_TOKENS:
            continue
        if re.fullmatch(r"(?:\d+|mp\d+|m4a|aac|wav|flac|webm|mp4|\d{2,4}k)", token):
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def raw_lookup_tokens(text: str) -> List[str]:
    """Tokenize normalized text without dropping provider/version words."""
    tokens: List[str] = []
    seen = set()
    for token in normalize_lookup_text(text).split():
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def title_variant_penalty(expected_title: str, candidate_title: str) -> float:
    """Penalize provider variants when the detected filename requested the base title."""
    expected_raw = set(raw_lookup_tokens(expected_title))
    candidate_raw = set(raw_lookup_tokens(candidate_title))
    unexpected = (candidate_raw - expected_raw).intersection(LYRICS_VARIANT_TOKENS)
    if not unexpected:
        return 0.0
    strong = {"instrumental", "karaoke", "remix", "salsa", "live"}
    return 0.28 if unexpected.intersection(strong) else 0.18


def title_similarity_score(expected_title: str, candidate_title: str) -> float:
    expected_tokens = tokenize_lookup_text(expected_title)
    candidate_tokens = tokenize_lookup_text(candidate_title)
    if not expected_tokens or not candidate_tokens:
        return 0.0
    score = token_overlap_ratio(expected_tokens, candidate_tokens)
    if normalize_lookup_text(expected_title) == normalize_lookup_text(candidate_title):
        score = max(score, 1.0)
    return float(np.clip(score - title_variant_penalty(expected_title, candidate_title), 0.0, 1.0))


def dedupe_keep_order(values: List[str]) -> List[str]:
    """Deduplicate text values while preserving original ordering."""
    seen = set()
    output: List[str] = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(key)
    return output


def trim_title_suffixes(title: str) -> str:
    """
    Trim noisy suffixes used in filenames (e.g. duplicate language chunks).
    Keeps the primary song title while preserving useful words.
    """
    value = title.strip()
    for separator in [" - ", " _ ", " | ", " / ", " \\ "]:
        if separator in value:
            value = value.split(separator, 1)[0].strip()
    value = re.sub(r"(?i)\b(?:feat|featuring|ft)\.?\b.*$", " ", value).strip()
    return re.sub(r"\s+", " ", value).strip()


def load_lyrics_overrides() -> Dict[str, str]:
    """Load optional local lyrics URL overrides (merged with defaults)."""
    overrides: Dict[str, str] = dict(DEFAULT_SHAZAM_LYRICS_OVERRIDES)
    if not LYRICS_OVERRIDE_FILE.exists():
        return overrides
    try:
        payload = json.loads(LYRICS_OVERRIDE_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for raw_key, raw_url in payload.items():
                key = normalize_lookup_text(str(raw_key))
                url = str(raw_url).strip()
                if key and url.startswith("http"):
                    overrides[key] = url
    except Exception:
        logger.warning("lyrics_overrides.json exists but is invalid JSON.")
    return overrides


def resolve_override_lyrics_url(song_name: str) -> Optional[str]:
    """Find best override URL for a given song name."""
    query = normalize_lookup_text(song_name)
    if not query:
        return None
    overrides = load_lyrics_overrides()
    if query in overrides:
        return overrides[query]
    for key, url in overrides.items():
        if key and (key in query or query in key):
            return url
    return None


def parse_artist_and_title(song_name: str) -> Tuple[Optional[str], str]:
    """
    Parse common "artist - title" patterns from cleaned filenames.
    Returns (artist_or_none, title).
    """
    cleaned = cleanup_query_text(song_name)
    parts = split_dash_parts(cleaned)

    if len(parts) >= 2:
        artist_hint = cleanup_query_text(" ".join(parts[:-1]))
        title_hint = cleanup_query_text(trim_title_suffixes(parts[-1]))

        if has_arabic_text(cleaned):
            arabic_artist, arabic_title = infer_arabic_artist_title(cleaned, title_hint)
            if arabic_title:
                return arabic_artist, arabic_title

        if artist_hint and title_hint:
            return artist_hint, title_hint

    for sep in [" : "]:
        if sep in cleaned:
            artist, title = cleaned.split(sep, 1)
            artist = cleanup_query_text(artist)
            title = cleanup_query_text(trim_title_suffixes(title))
            if artist and title:
                return artist, title

    if has_arabic_text(cleaned):
        arabic_artist, arabic_title = infer_arabic_artist_title(cleaned, cleaned)
        if arabic_title:
            return arabic_artist, arabic_title

    return None, trim_title_suffixes(cleaned)


def build_lyrics_query_variants(song_name: str, artist: Optional[str], title: str) -> List[str]:
    """Build ordered query variants for web lyrics lookup."""
    variants: List[str] = []
    cleaned_name = cleanup_query_text(song_name)
    arabic_text = " ".join(extract_arabic_words(cleaned_name)).strip()
    latin_hint = re.sub(r"[^0-9a-zA-Z\s\-]", " ", remove_arabic_text(cleaned_name))
    latin_hint = re.sub(r"\s+", " ", latin_hint).strip(" -")
    compact_hint = " ".join(tokenize_lookup_text(cleaned_name)).strip()

    if artist and title:
        variants.append(f"{title} - {artist}")
    if latin_hint:
        variants.append(latin_hint)
    if artist and title:
        variants.append(f"{artist} - {title}")
        variants.append(f"{artist} {title}")
        variants.append(f"{title} {artist}")
    if title:
        variants.append(title)
    if arabic_text:
        variants.append(arabic_text)
    if compact_hint:
        variants.append(compact_hint)
    variants.append(cleaned_name)

    # ASCII-only fallback can help some providers match noisy Unicode filenames.
    ascii_hint = re.sub(r"[^0-9a-zA-Z\s\-]", " ", cleaned_name)
    ascii_hint = re.sub(r"\s+", " ", ascii_hint).strip(" -")
    if ascii_hint:
        variants.append(ascii_hint)

    return dedupe_keep_order(variants)


def strip_html_tags(value: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", value)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_lyrics_from_lyrics_ovh(artist: str, title: str) -> Optional[str]:
    """Try free lyrics endpoint first (fast and structured)."""
    url = f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}"
    try:
        response = lyrics_http_get("lyrics_ovh", url)
        if response is None:
            return None
        if response.status_code != 200:
            return None
        data = response.json()
        lyrics = (data.get("lyrics") or "").strip()
        return lyrics or None
    except Exception:
        return None


def fetch_lyrics_from_lrclib(
    artist: Optional[str],
    title: str,
    query: str,
    expected_duration_sec: Optional[float] = None,
    try_exact: bool = True,
) -> Optional[str]:
    """Fetch full lyrics from LRCLIB (often richer than snippets)."""
    reference_tokens = tokenize_lookup_text(f"{artist or ''} {title}".strip())
    if not reference_tokens:
        reference_tokens = tokenize_lookup_text(query)
    artist_tokens = tokenize_lookup_text(artist or "")
    title_tokens = tokenize_lookup_text(title or "")
    expected_duration = float(expected_duration_sec or 0.0)
    min_accept = LYRICS_MIN_TOKEN_OVERLAP if artist_tokens else LYRICS_MIN_TOKEN_OVERLAP_NO_ARTIST

    try:
        if try_exact and artist and title:
            url = (
                "https://lrclib.net/api/get?"
                f"artist_name={quote_plus(artist)}&track_name={quote_plus(title)}"
            )
            response = lyrics_http_get("lrclib_get", url)
            if response is not None and response.status_code == 200:
                payload = response.json()
                lyrics = (payload.get("plainLyrics") or payload.get("syncedLyrics") or "").strip()
                if lyrics:
                    candidate_text = f"{payload.get('artistName', '')} {payload.get('trackName', '')}"
                    candidate_tokens = tokenize_lookup_text(candidate_text)
                    candidate_title = str(payload.get("trackName", ""))
                    score = lyrics_candidate_score(
                        candidate_tokens=candidate_tokens,
                        reference_tokens=reference_tokens,
                        artist_tokens=artist_tokens,
                        title_tokens=title_tokens,
                    )
                    title_score = title_similarity_score(title, candidate_title)
                    if title_score >= LYRICS_MIN_TITLE_SCORE:
                        if artist_tokens:
                            score = float((0.65 * score) + (0.35 * title_score))
                        else:
                            score = title_score
                        payload_duration = parse_duration_seconds(payload.get("duration"))
                        if expected_duration > 0.0 and payload_duration > 0.0:
                            dscore = duration_similarity(expected_duration, payload_duration)
                            score = float((0.72 * score) + (0.28 * dscore))
                        if score >= min_accept:
                            return lyrics
    except Exception:
        pass

    try:
        search_url = f"https://lrclib.net/api/search?q={quote_plus(query)}"
        response = lyrics_http_get("lrclib_search", search_url)
        if response is None:
            return None
        if response.status_code != 200:
            return None
        items = response.json()
        if not isinstance(items, list) or not items:
            return None

        best_lyrics: Optional[str] = None
        best_score = 0.0
        for item in items[:LYRICS_SEARCH_CANDIDATE_LIMIT]:
            if not isinstance(item, dict):
                continue
            lyrics = (item.get("plainLyrics") or item.get("syncedLyrics") or "").strip()
            if len(lyrics) < 40:
                continue
            candidate_text = f"{item.get('artistName', '')} {item.get('trackName', '')}"
            candidate_tokens = tokenize_lookup_text(candidate_text)
            candidate_title = str(item.get("trackName", ""))
            score = lyrics_candidate_score(
                candidate_tokens=candidate_tokens,
                reference_tokens=reference_tokens,
                artist_tokens=artist_tokens,
                title_tokens=title_tokens,
            )
            query_score = token_overlap_ratio(tokenize_lookup_text(query), candidate_tokens)
            score = max(score, query_score)
            title_score = max(
                title_similarity_score(title, candidate_title),
                title_similarity_score(query, candidate_title),
            )
            if title_score < LYRICS_MIN_TITLE_SCORE:
                continue
            if artist_tokens:
                score = float((0.65 * score) + (0.35 * title_score))
            else:
                score = title_score
            candidate_duration = parse_duration_seconds(item.get("duration"))
            if expected_duration > 0.0 and candidate_duration > 0.0:
                dscore = duration_similarity(expected_duration, candidate_duration)
                score = float((0.72 * score) + (0.28 * dscore))
            if score > best_score:
                best_score = score
                best_lyrics = lyrics

        if best_lyrics and (not reference_tokens or best_score >= min_accept):
            return best_lyrics
        return None
    except Exception:
        return None


def suggest_song_from_lyrics_ovh(query: str) -> Tuple[Optional[str], Optional[str]]:
    """Get a likely (artist, title) pair for noisy filenames."""
    url = f"https://api.lyrics.ovh/suggest/{quote(query)}"
    try:
        response = lyrics_http_get("lyrics_ovh_suggest", url)
        if response is None:
            return None, None
        if response.status_code != 200:
            return None, None
        data = response.json()
        items = data.get("data") or []
        if not items:
            return None, None

        query_tokens = tokenize_lookup_text(query)
        best_artist: Optional[str] = None
        best_title: Optional[str] = None
        best_score = 0.0
        for top in items[:LYRICS_SEARCH_CANDIDATE_LIMIT]:
            if not isinstance(top, dict):
                continue
            artist = ((top.get("artist") or {}).get("name") or "").strip()
            title = (top.get("title") or "").strip()
            if not artist or not title:
                continue
            if query_tokens:
                candidate_tokens = tokenize_lookup_text(f"{artist} {title}")
                score = token_overlap_ratio(query_tokens, candidate_tokens)
            else:
                score = 1.0
            if score > best_score:
                best_score = score
                best_artist = artist
                best_title = title

        if best_artist and best_title and (not query_tokens or best_score >= LYRICS_MIN_TOKEN_OVERLAP):
            return best_artist, best_title
        return None, None
    except Exception:
        return None, None


def fetch_lyrics_from_google_snippet(query: str) -> Optional[str]:
    """
    Fallback: pull short lyrics snippet from Google search result page.
    This is best-effort and may fail if Google layout changes.
    """
    cleaned_query = cleanup_query_text(query).strip() or query.strip()
    query_tokens = tokenize_lookup_text(cleaned_query)
    url = f"https://www.google.com/search?q={quote_plus(cleaned_query + ' lyrics')}&hl=en&gl=US&gbv=1"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    try:
        response = lyrics_http_get("google_snippet", url, headers=headers)
        if response is None:
            return None
        if response.status_code != 200:
            return None
        html_text = response.text

        candidates: List[str] = []
        patterns = [
            r'(?is)<div class="BNeawe[^"]*">(.*?)</div>',
            r'(?is)<span class="aCOpRe[^"]*">(.*?)</span>',
            r'(?is)<div[^>]+data-lyricid="[^"]*"[^>]*>(.*?)</div>',
        ]
        for pattern in patterns:
            blocks = re.findall(pattern, html_text)
            for block in blocks:
                txt = strip_html_tags(block)
                if len(txt) < 60:
                    continue
                lowered = txt.lower()
                if "http" in lowered or "google" in lowered:
                    continue
                candidates.append(txt)

        meta_match = re.search(r'(?is)<meta name="description" content="([^"]+)"', html_text)
        if meta_match:
            meta_text = strip_html_tags(meta_match.group(1))
            if len(meta_text) >= 60:
                candidates.append(meta_text)

        if not candidates:
            return None

        for candidate in sorted(candidates, key=len, reverse=True):
            text = candidate.strip()
            if not text:
                continue
            if query_tokens:
                candidate_tokens = tokenize_lookup_text(text)
                if token_overlap_ratio(query_tokens, candidate_tokens) < LYRICS_MIN_TOKEN_OVERLAP:
                    continue
            return text
        return None
    except Exception:
        return None


def fetch_lyrics_from_shazam_page(url: str) -> Optional[str]:
    """
    Fetch full lyrics from a Shazam song page by reading JSON-LD metadata.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    try:
        response = lyrics_http_get("shazam_page", url, headers=headers)
        if response is None:
            return None
        if response.status_code != 200:
            return None
        html_text = response.text

        # Fast path: direct JSON payload embedded in page source.
        direct_match = re.search(
            r'(?is)"lyrics"\s*:\s*\{\s*"@type"\s*:\s*"CreativeWork"\s*,\s*"text"\s*:\s*"(.*?)"\s*\}',
            html_text,
        )
        if direct_match:
            try:
                lyrics = json.loads('"' + direct_match.group(1) + '"')
                lyrics = (lyrics or "").strip()
                if len(lyrics) >= 40:
                    return lyrics
            except Exception:
                pass

        ld_blocks = re.findall(
            r'(?is)<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html_text,
        )
        for block in ld_blocks:
            try:
                obj = json.loads(block)
            except Exception:
                continue

            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                if not isinstance(item, dict):
                    continue
                lyrics_obj = item.get("lyrics")
                if isinstance(lyrics_obj, dict):
                    lyrics = (lyrics_obj.get("text") or "").strip()
                    if len(lyrics) >= 40:
                        return lyrics
        return None
    except Exception:
        return None


def get_ytmusic_client() -> Optional[Any]:
    """Lazy-init YTMusic API client (optional dependency)."""
    global ytmusic_client, ytmusic_disabled

    if not YTMUSIC_PROVIDER_ENABLED or ytmusic_disabled:
        return None
    if ytmusic_client is not None:
        return ytmusic_client

    try:
        from ytmusicapi import YTMusic  # optional dependency
    except Exception:
        ytmusic_disabled = True
        return None

    try:
        ytmusic_client = YTMusic()
        return ytmusic_client
    except Exception:
        ytmusic_disabled = True
        return None


def token_overlap_ratio(reference_tokens: List[str], candidate_tokens: List[str]) -> float:
    if not reference_tokens or not candidate_tokens:
        return 0.0
    ref = set(reference_tokens)
    cand = set(candidate_tokens)
    overlap = len(ref.intersection(cand))
    if overlap == 0:
        return 0.0
    recall = float(overlap / max(1, len(ref)))
    precision = float(overlap / max(1, len(cand)))
    return float((0.65 * recall) + (0.35 * precision))


def parse_duration_seconds(value: Any) -> float:
    """Parse provider duration fields into seconds (best-effort)."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        val = float(value)
        if val > 10000:  # likely milliseconds
            return val / 1000.0
        return val

    text = str(value).strip()
    if not text:
        return 0.0

    if ":" in text:
        parts = [p for p in text.split(":") if p.strip()]
        try:
            parts_i = [int(p) for p in parts]
            if len(parts_i) == 2:
                return float(parts_i[0] * 60 + parts_i[1])
            if len(parts_i) == 3:
                return float(parts_i[0] * 3600 + parts_i[1] * 60 + parts_i[2])
        except Exception:
            return 0.0

    try:
        return float(text)
    except Exception:
        return 0.0


def duration_similarity(expected_seconds: float, candidate_seconds: float) -> float:
    """Map duration difference into [0,1]."""
    expected = max(0.0, float(expected_seconds))
    candidate = max(0.0, float(candidate_seconds))
    if expected <= 0.0 or candidate <= 0.0:
        return 0.0
    diff = abs(expected - candidate)
    tolerance = max(10.0, expected * 0.35)
    return float(np.clip(1.0 - (diff / tolerance), 0.0, 1.0))


def lyrics_candidate_score(
    candidate_tokens: List[str],
    reference_tokens: List[str],
    artist_tokens: Optional[List[str]] = None,
    title_tokens: Optional[List[str]] = None,
) -> float:
    """Weighted token score for validating lyrics provider candidates."""
    if not candidate_tokens:
        return 0.0

    score = token_overlap_ratio(reference_tokens, candidate_tokens) if reference_tokens else 1.0
    candidate_set = set(candidate_tokens)

    artist_tokens = artist_tokens or []
    if artist_tokens:
        artist_set = set(artist_tokens)
        artist_overlap = float(len(artist_set.intersection(candidate_set)) / max(1, len(artist_set)))
        if artist_overlap <= 0.0:
            return 0.0
        score = float((0.60 * score) + (0.40 * artist_overlap))

    title_tokens = title_tokens or []
    if title_tokens:
        title_overlap = token_overlap_ratio(title_tokens, candidate_tokens)
        score = float((0.70 * score) + (0.30 * title_overlap))

    return float(np.clip(score, 0.0, 1.0))


def fetch_lyrics_from_ytmusic(
    query_variants: List[str],
    expected_artist: Optional[str] = None,
    expected_title: str = "",
    expected_duration_sec: Optional[float] = None,
) -> Optional[str]:
    """
    Fetch full lyrics via YouTube Music metadata + lyrics endpoint.
    This improves coverage for tracks where classic lyrics APIs miss.
    """
    yt = get_ytmusic_client()
    if yt is None:
        return None

    artist_tokens = tokenize_lookup_text(expected_artist or "")
    title_tokens = tokenize_lookup_text(expected_title)
    expected_duration = float(expected_duration_sec or 0.0)
    min_accept = LYRICS_MIN_TOKEN_OVERLAP if artist_tokens else LYRICS_MIN_TOKEN_OVERLAP_NO_ARTIST

    candidates: List[Tuple[float, int, str]] = []
    seen_videos = set()
    provider_rank = 0

    for query in query_variants[:YTMUSIC_QUERY_LIMIT]:
        if not query:
            continue
        try:
            logger.info("Lyrics API request | provider=ytmusic query=%s", query)
            results = yt.search(query, filter="songs", limit=YTMUSIC_SEARCH_LIMIT) or []
            logger.info(
                "Lyrics API response | provider=ytmusic query=%s items=%d",
                query,
                len(results) if isinstance(results, list) else 0,
            )
        except Exception:
            continue

        query_tokens = tokenize_lookup_text(query)
        for item in results:
            if not isinstance(item, dict):
                continue
            provider_rank += 1
            video_id = str(item.get("videoId") or "").strip()
            if not video_id or video_id in seen_videos:
                continue

            title = str(item.get("title") or "")
            artists = " ".join(
                str(artist.get("name") or "")
                for artist in (item.get("artists") or [])
                if isinstance(artist, dict)
            )
            candidate_tokens = tokenize_lookup_text(f"{title} {artists}")
            overlap = lyrics_candidate_score(
                candidate_tokens=candidate_tokens,
                reference_tokens=query_tokens,
                artist_tokens=artist_tokens,
                title_tokens=title_tokens,
            )
            query_score = token_overlap_ratio(query_tokens, candidate_tokens)
            overlap = max(overlap, query_score)
            title_score = max(
                title_similarity_score(expected_title, title),
                title_similarity_score(query, title),
            )
            if title_score < LYRICS_MIN_TITLE_SCORE:
                continue
            if artist_tokens:
                overlap = float((0.65 * overlap) + (0.35 * title_score))
            else:
                overlap = title_score
            item_duration = parse_duration_seconds(
                item.get("duration_seconds") or item.get("duration") or item.get("lengthSeconds")
            )
            if expected_duration > 0.0 and item_duration > 0.0:
                dscore = duration_similarity(expected_duration, item_duration)
                overlap = float((0.72 * overlap) + (0.28 * dscore))

            if overlap < min_accept:
                continue

            seen_videos.add(video_id)
            candidates.append((overlap, provider_rank, video_id))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], item[1]))
    for _, _, video_id in candidates[:8]:
        try:
            watch = yt.get_watch_playlist(videoId=video_id) or {}
            lyrics_browse_id = str(watch.get("lyrics") or "").strip()
            if not lyrics_browse_id:
                continue
            payload = yt.get_lyrics(lyrics_browse_id) or {}
            lyrics = (payload.get("lyrics") or "").strip() if isinstance(payload, dict) else ""
            logger.info(
                "Lyrics API response | provider=ytmusic_lyrics video_id=%s has_lyrics=%s preview=%s",
                video_id,
                bool(lyrics),
                compact_log_text(lyrics),
            )
            if len(lyrics) >= 40:
                return lyrics
        except Exception:
            continue
    return None


def fetch_online_lyrics(song_name: str, expected_duration_sec: Optional[float] = None) -> Tuple[Optional[str], str]:
    """Fetch lyrics from web sources (cached), preferring full lyrics providers."""
    duration_key = int(round(float(expected_duration_sec or 0.0)))
    cleaned_name = cleanup_query_text(song_name)
    cache_key = f"{normalize_lookup_text(song_name)}|{duration_key}"
    if cache_key in lyrics_cache:
        cached = lyrics_cache[cache_key]
        return cached.get("text"), cached.get("source", "unknown")

    artist, title = parse_artist_and_title(song_name)
    query_variants = build_lyrics_query_variants(song_name=song_name, artist=artist, title=title)
    primary_query = query_variants[0] if query_variants else cleaned_name

    logger.info(
        "Lyrics lookup | original=%s cleaned_song_title=%s artist=%s title=%s variants=%s",
        song_name,
        cleaned_name,
        artist or "",
        title,
        query_variants[:8],
    )

    lyrics: Optional[str] = None
    source = "not_found"

    # 1) Fast deterministic override path (when available).
    override_url = resolve_override_lyrics_url(song_name)
    if override_url:
        lyrics = fetch_lyrics_from_shazam_page(override_url)
        if lyrics:
            source = "shazam_page_override"

    # 2) Full lyrics from YouTube Music metadata (good multilingual coverage).
    if not lyrics:
        lyrics = fetch_lyrics_from_ytmusic(
            query_variants=query_variants,
            expected_artist=artist,
            expected_title=title,
            expected_duration_sec=expected_duration_sec,
        )
        if lyrics:
            source = "ytmusic"

    # 3) Full lyrics providers.
    for idx, q in enumerate(query_variants):
        if lyrics:
            break
        lyrics = fetch_lyrics_from_lrclib(
            artist=artist,
            title=title,
            query=q,
            expected_duration_sec=expected_duration_sec,
            try_exact=(idx == 0),
        )
        if lyrics:
            source = "lrclib"

    if not lyrics and artist and title:
        lyrics = fetch_lyrics_from_lyrics_ovh(artist=artist, title=title)
        if lyrics:
            source = "lyrics_ovh"

    if not lyrics and artist and title:
        guessed_artist, guessed_title = suggest_song_from_lyrics_ovh(primary_query)
        if guessed_artist and guessed_title and title_similarity_score(title, guessed_title) >= LYRICS_MIN_TITLE_SCORE:
            lyrics = fetch_lyrics_from_lyrics_ovh(artist=guessed_artist, title=guessed_title)
            if lyrics:
                source = "lyrics_ovh_suggest"

    # 4) Last fallback: Google snippet (usually partial).
    if not lyrics and artist:
        for q in query_variants:
            lyrics = fetch_lyrics_from_google_snippet(q)
            if lyrics:
                source = "google_snippet"
                break

    if lyrics:
        lyrics_cache[cache_key] = {"text": lyrics, "source": source}
        return lyrics, source
    logger.info("Lyrics lookup finished | cleaned_song_title=%s result=not_found", cleaned_name)
    return None, "not_found"


def estimate_audio_metadata(waveform: np.ndarray) -> dict:
    """Estimate lightweight music metadata for innovation insights."""
    if waveform.size == 0:
        return {"tempo_bpm": 0.0, "key_label": "unknown", "energy": 0.0}

    sample_limit = int(SAMPLE_RATE * METADATA_ANALYSIS_SECONDS)
    clip = waveform[:sample_limit]

    try:
        onset_env = librosa.onset.onset_strength(y=clip, sr=SAMPLE_RATE)
        tempo_array = librosa.feature.rhythm.tempo(onset_envelope=onset_env, sr=SAMPLE_RATE)
        tempo = float(tempo_array[0]) if len(tempo_array) else 0.0
    except Exception:
        tempo = 0.0

    try:
        chroma = librosa.feature.chroma_stft(y=clip, sr=SAMPLE_RATE)
        key_idx = int(np.argmax(np.mean(chroma, axis=1)))
        key_label = NOTE_NAMES[key_idx]
    except Exception:
        key_label = "unknown"

    try:
        energy = float(np.mean(librosa.feature.rms(y=clip)))
    except Exception:
        energy = 0.0

    return {
        "tempo_bpm": round(max(0.0, tempo), 2),
        "key_label": key_label,
        "energy": round(max(0.0, energy), 6),
    }


def get_cached_or_local_song_lyrics(song_key: str) -> Tuple[str, str]:
    """Return lyrics that are already local/cached without blocking detection."""
    record = song_index.get(song_key)
    if not record:
        return "", "not_found"
    if record.lyrics:
        return trim_lyrics(record.lyrics), "local"

    duration_key = int(round(float(record.duration_sec or 0.0)))
    cache_key = f"{normalize_lookup_text(record.relative_name)}|{duration_key}"
    cached = lyrics_cache.get(cache_key)
    if cached:
        text = cached.get("text") or ""
        source = cached.get("source", "unknown")
        if text:
            return trim_lyrics(text), source
    return "", "pending"


def get_best_song_lyrics(song_key: str) -> Tuple[str, str]:
    """Get lyrics for best detected song: local sidecar first, then online."""
    record = song_index.get(song_key)
    if not record:
        return "", "not_found"

    cached_or_local, source = get_cached_or_local_song_lyrics(song_key)
    if cached_or_local:
        return cached_or_local, source

    online, source = fetch_online_lyrics(
        record.relative_name,
        expected_duration_sec=record.duration_sec,
    )
    if not online:
        return "Lyrics not found", source
    return trim_lyrics(online), source


async def _shazamio_recognize_file(file_path: Path) -> Optional[dict]:
    """Async helper for shazamio recognition."""
    try:
        from shazamio import Shazam  # optional dependency
    except Exception:
        return None

    shazam = Shazam()
    response = await shazam.recognize(str(file_path))
    if not isinstance(response, dict):
        return None
    track = response.get("track") or {}
    title = (track.get("title") or "").strip()
    artist = (track.get("subtitle") or "").strip()
    if not title:
        return None
    return {
        "title": title,
        "artist": artist,
        "url": ((track.get("share") or {}).get("href") or "").strip(),
        "raw": response,
    }


def external_shazam_fallback(query_waveform: np.ndarray) -> Optional[dict]:
    """
    Optional external fallback recognition using shazamio.
    Runs only when local match confidence is low.
    """
    if not SHAZAM_FALLBACK_ENABLED:
        return None

    sample_len = int(SAMPLE_RATE * 12)
    if query_waveform.size <= 0:
        return None

    if query_waveform.size <= sample_len:
        chunks = [query_waveform]
    else:
        mid_start = max(0, (query_waveform.size // 2) - (sample_len // 2))
        end_start = max(0, query_waveform.size - sample_len)
        chunks = [
            query_waveform[:sample_len],
            query_waveform[mid_start : mid_start + sample_len],
            query_waveform[end_start : end_start + sample_len],
        ]

    for i, chunk in enumerate(chunks):
        temp_wav: Optional[Path] = None
        try:
            with NamedTemporaryFile(delete=False, suffix=f"_fallback_{i}.wav", dir=UPLOAD_DIR) as tmp:
                temp_wav = Path(tmp.name)
            sf.write(str(temp_wav), chunk, SAMPLE_RATE, format="WAV")
            result = asyncio.run(_shazamio_recognize_file(temp_wav))
            if result:
                return result
        except Exception:
            continue
        finally:
            if temp_wav and temp_wav.exists():
                temp_wav.unlink(missing_ok=True)
    return None


def bootstrap_ffmpeg_dependency() -> bool:
    """Best-effort runtime installation of imageio-ffmpeg when missing."""
    global ffmpeg_bootstrap_attempted
    if ffmpeg_bootstrap_attempted:
        return False
    ffmpeg_bootstrap_attempted = True

    try:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--quiet",
            "imageio-ffmpeg",
        ]
        run = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
            check=False,
        )
        if run.returncode == 0:
            logger.info("Auto-installed imageio-ffmpeg runtime dependency.")
            return True
        logger.warning("imageio-ffmpeg auto-install failed: %s", run.stderr.strip())
        return False
    except Exception as exc:
        logger.warning("imageio-ffmpeg auto-install exception: %s", exc)
        return False


def get_ffmpeg_executable() -> Optional[str]:
    """Resolve FFmpeg from PATH or bundled imageio-ffmpeg package."""
    env_path = os.environ.get("FFMPEG_PATH", "").strip()
    if env_path and Path(env_path).exists():
        return env_path

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return "ffmpeg"
    except Exception:
        pass

    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        exe = get_ffmpeg_exe()
        if exe:
            return exe
    except Exception:
        if bootstrap_ffmpeg_dependency():
            try:
                from imageio_ffmpeg import get_ffmpeg_exe

                exe = get_ffmpeg_exe()
                if exe:
                    return exe
            except Exception:
                return None
        return None
    return None


def load_waveform_with_ffmpeg(
    file_path: Path,
    duration_seconds: Optional[float],
    offset_seconds: float,
) -> np.ndarray:
    """Decode audio with FFmpeg into temporary WAV, then load with librosa."""
    ffmpeg_exe = get_ffmpeg_executable()
    if not ffmpeg_exe:
        raise ValueError("Cannot decode this audio format. Install FFmpeg or use .mp3/.wav.")

    temp_wav: Optional[Path] = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".wav", dir=UPLOAD_DIR) as tmp:
            temp_wav = Path(tmp.name)

        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{offset_seconds:.3f}",
            "-i",
            str(file_path),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "wav",
            str(temp_wav),
            "-y",
        ]
        if duration_seconds is not None:
            cmd[6:6] = ["-t", f"{duration_seconds:.3f}"]
        run = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
            check=False,
        )
        if run.returncode != 0:
            raise ValueError(run.stderr.strip() or "Unknown FFmpeg decode error.")

        waveform, _ = librosa.load(str(temp_wav), sr=SAMPLE_RATE, mono=True)
        if waveform.size == 0:
            raise ValueError("Decoded WAV is empty.")
        return waveform.astype(np.float32)
    except Exception as exc:
        raise ValueError(f"FFmpeg decode failed for {file_path.name}: {exc}") from exc
    finally:
        if temp_wav and temp_wav.exists():
            temp_wav.unlink(missing_ok=True)


def load_waveform(
    file_path: Path,
    duration_seconds: Optional[float],
    offset_seconds: float = 0.0,
) -> np.ndarray:
    """Load audio as mono waveform using librosa."""
    try:
        waveform, _ = librosa.load(
            str(file_path),
            sr=SAMPLE_RATE,
            mono=True,
            duration=duration_seconds,
            offset=offset_seconds,
        )
        if waveform.size == 0:
            raise ValueError(f"Audio is empty or unreadable: {file_path}")
        return waveform.astype(np.float32)
    except Exception as exc:
        # Robust fallback for formats such as .m4a when default backend is unavailable.
        try:
            return load_waveform_with_ffmpeg(
                file_path=file_path,
                duration_seconds=duration_seconds,
                offset_seconds=offset_seconds,
            )
        except Exception as ffmpeg_exc:
            if exc.__class__.__name__ == "NoBackendError":
                raise ValueError(
                    f"Cannot decode '{file_path.suffix}' on this machine. {ffmpeg_exc}"
                ) from exc
            raise ValueError(
                f"Failed to decode {file_path.name} ({exc.__class__.__name__}: {exc})"
            ) from exc


def compute_file_sha1(file_path: Path) -> str:
    """Compute SHA1 hash for exact-file matching."""
    sha1 = hashlib.sha1()
    with file_path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            sha1.update(chunk)
    return sha1.hexdigest()


def preprocess_waveform(waveform: np.ndarray) -> np.ndarray:
    """
    Remove leading/trailing silence when possible to improve retrieval stability.
    Keeps original when trimming would leave too little audio.
    """
    if waveform.size == 0:
        return waveform
    try:
        trimmed, _ = librosa.effects.trim(waveform, top_db=28)
        if trimmed.size >= int(1.5 * SAMPLE_RATE):
            return trimmed.astype(np.float32)
    except Exception:
        pass
    return waveform.astype(np.float32)


def select_loudest_window(
    waveform: np.ndarray,
    window_seconds: float,
    hop_seconds: float = 0.5,
) -> np.ndarray:
    """
    Select the highest-energy contiguous window.
    Helps live mic queries by focusing on the part with actual music.
    """
    if waveform.size == 0:
        return waveform
    win = int(max(0.5, window_seconds) * SAMPLE_RATE)
    hop = int(max(0.1, hop_seconds) * SAMPLE_RATE)
    if win <= 0 or waveform.size <= win:
        return waveform.astype(np.float32)

    best_start = 0
    best_energy = -1.0
    for start in range(0, waveform.size - win + 1, max(1, hop)):
        segment = waveform[start : start + win]
        energy = float(np.mean(segment * segment))
        if energy > best_energy:
            best_energy = energy
            best_start = start
    return waveform[best_start : best_start + win].astype(np.float32)


def average_pool_time(feature_matrix: np.ndarray, pool_size: int) -> np.ndarray:
    """Average-pool feature frames across time."""
    if feature_matrix.size == 0 or pool_size <= 1:
        return feature_matrix
    total_frames = feature_matrix.shape[1]
    pooled: List[np.ndarray] = []
    for start in range(0, total_frames, pool_size):
        chunk = feature_matrix[:, start : start + pool_size]
        pooled.append(np.mean(chunk, axis=1))
    if not pooled:
        return feature_matrix
    return np.stack(pooled, axis=1).astype(np.float32)


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization."""
    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (matrix / norms).astype(np.float32)


def fit_whitening_stats(matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Fit per-dimension mean/std for stable cosine scoring."""
    if matrix.size == 0:
        return np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.float32)
    if matrix.shape[0] < 2:
        dim = int(matrix.shape[1])
        return np.zeros((dim,), dtype=np.float32), np.ones((dim,), dtype=np.float32)
    mean = np.mean(matrix, axis=0).astype(np.float32)
    std = np.std(matrix, axis=0).astype(np.float32)
    std = np.maximum(std, 1e-6).astype(np.float32)
    return mean, std


def whiten_and_normalize_rows(matrix: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """Apply whitening then row-wise L2 normalize."""
    if matrix.size == 0:
        return matrix
    casted = matrix.astype(np.float32)
    if mean.shape[0] != casted.shape[1] or std.shape[0] != casted.shape[1]:
        return normalize_rows(casted)
    whitened = (casted - mean) / std
    return normalize_rows(whitened.astype(np.float32))


def whiten_and_normalize_vector(vector: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """Apply whitening then L2 normalize for one vector."""
    if vector.size == 0:
        return vector
    casted = vector.astype(np.float32)
    if mean.shape[0] != casted.shape[0] or std.shape[0] != casted.shape[0]:
        return normalize_vector(casted)
    whitened = (casted - mean) / std
    return normalize_vector(whitened.astype(np.float32))


def sample_rows_for_stats(matrix: np.ndarray, max_rows: int) -> np.ndarray:
    """Take evenly-spaced row samples to keep stat fitting efficient."""
    if matrix.size == 0 or matrix.shape[0] <= max_rows:
        return matrix.astype(np.float32)
    idx = np.linspace(0, matrix.shape[0] - 1, max_rows).astype(int)
    return matrix[idx].astype(np.float32)


def extract_feature_from_waveform(waveform: np.ndarray) -> np.ndarray:
    """
    Rich global vector:
    - MFCC mean/std
    - Chroma mean/std
    - Spectral centroid/rolloff stats
    - Zero-crossing-rate and RMS stats
    """
    clean = preprocess_waveform(waveform)
    mfcc = librosa.feature.mfcc(y=clean, sr=SAMPLE_RATE, n_mfcc=N_MFCC)
    chroma = librosa.feature.chroma_stft(y=clean, sr=SAMPLE_RATE, n_chroma=N_CHROMA)
    centroid = librosa.feature.spectral_centroid(y=clean, sr=SAMPLE_RATE)
    rolloff = librosa.feature.spectral_rolloff(y=clean, sr=SAMPLE_RATE)
    zcr = librosa.feature.zero_crossing_rate(y=clean)
    rms = librosa.feature.rms(y=clean)

    feature_vector = np.concatenate(
        [
            np.mean(mfcc, axis=1),
            np.std(mfcc, axis=1),
            np.mean(chroma, axis=1),
            np.std(chroma, axis=1),
            np.array(
                [
                    float(np.mean(centroid)),
                    float(np.std(centroid)),
                    float(np.mean(rolloff)),
                    float(np.std(rolloff)),
                    float(np.mean(zcr)),
                    float(np.std(zcr)),
                    float(np.mean(rms)),
                    float(np.std(rms)),
                ],
                dtype=np.float32,
            ),
        ]
    ).astype(np.float32)

    return normalize_vector(feature_vector)


def extract_segment_features(waveform: np.ndarray) -> np.ndarray:
    """Split audio into fixed-size windows and extract a feature for each."""
    clean = preprocess_waveform(waveform)
    segment_len = int(SEGMENT_DURATION_SECONDS * SAMPLE_RATE)
    hop_len = int(SEGMENT_HOP_SECONDS * SAMPLE_RATE)

    if clean.size <= segment_len:
        return np.expand_dims(extract_feature_from_waveform(clean), axis=0)

    start_positions = list(range(0, clean.size - segment_len + 1, hop_len))
    if len(start_positions) > MAX_SEGMENTS_PER_TRACK:
        chosen_idx = np.linspace(0, len(start_positions) - 1, MAX_SEGMENTS_PER_TRACK).astype(int)
        start_positions = [start_positions[i] for i in chosen_idx]

    features: List[np.ndarray] = []
    for start in start_positions:
        segment = clean[start : start + segment_len]
        features.append(extract_feature_from_waveform(segment))

    if not features:
        features.append(extract_feature_from_waveform(clean))
    return np.vstack(features).astype(np.float32)


def extract_sequence_features(waveform: np.ndarray) -> np.ndarray:
    """
    Extract robust frame-level embeddings for subsequence DTW reranking.
    Output shape: (num_frames, feature_dim)
    """
    clean = preprocess_waveform(waveform)
    if clean.size == 0:
        return np.empty((0, SEQUENCE_N_MFCC + N_CHROMA), dtype=np.float32)

    mfcc = librosa.feature.mfcc(
        y=clean,
        sr=SAMPLE_RATE,
        n_mfcc=SEQUENCE_N_MFCC,
        n_fft=2048,
        hop_length=SEQUENCE_HOP_LENGTH,
    )
    chroma = librosa.feature.chroma_cens(
        y=clean,
        sr=SAMPLE_RATE,
        hop_length=SEQUENCE_HOP_LENGTH,
        n_chroma=N_CHROMA,
    )

    frame_count = min(mfcc.shape[1], chroma.shape[1])
    if frame_count <= 0:
        return np.empty((0, SEQUENCE_N_MFCC + N_CHROMA), dtype=np.float32)

    stacked = np.vstack([mfcc[:, :frame_count], chroma[:, :frame_count]]).astype(np.float32)
    mu = np.mean(stacked, axis=1, keepdims=True)
    sigma = np.std(stacked, axis=1, keepdims=True) + 1e-6
    normalized = (stacked - mu) / sigma
    pooled = average_pool_time(normalized, SEQUENCE_POOL_SIZE)
    return normalize_rows(pooled.T.astype(np.float32))


def extract_query_features(
    file_path: Path,
    duration_seconds: float,
    offset_seconds: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    waveform = load_waveform(file_path, duration_seconds=duration_seconds, offset_seconds=offset_seconds)
    query_global = extract_feature_from_waveform(waveform)
    query_segments = extract_segment_features(waveform)
    query_sequence = extract_sequence_features(waveform)
    max_frames = int(MAX_QUERY_SEQUENCE_SECONDS / max(SEQUENCE_HOP_SECONDS, 1e-6))
    if max_frames > 0 and query_sequence.shape[0] > max_frames:
        query_sequence = query_sequence[:max_frames]
    return query_global, query_segments, query_sequence


def extract_query_features_from_waveform(
    waveform: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute query features directly from an in-memory waveform."""
    query_global = extract_feature_from_waveform(waveform)
    query_segments = extract_segment_features(waveform)
    query_sequence = extract_sequence_features(waveform)
    max_frames = int(MAX_QUERY_SEQUENCE_SECONDS / max(SEQUENCE_HOP_SECONDS, 1e-6))
    if max_frames > 0 and query_sequence.shape[0] > max_frames:
        query_sequence = query_sequence[:max_frames]
    return query_global, query_segments, query_sequence


def extract_landmark_fingerprints(waveform: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Extract Shazam-style spectral landmark hashes and anchor frames."""
    clean = preprocess_waveform(waveform)
    if clean.size < int(1.0 * SAMPLE_RATE):
        return np.empty((0,), dtype=np.int64), np.empty((0,), dtype=np.int32)

    try:
        from scipy.ndimage import maximum_filter  # type: ignore
    except Exception:
        return np.empty((0,), dtype=np.int64), np.empty((0,), dtype=np.int32)

    try:
        spectrum = np.abs(
            librosa.stft(
                clean,
                n_fft=FINGERPRINT_N_FFT,
                hop_length=FINGERPRINT_HOP_LENGTH,
                center=True,
            )
        ).astype(np.float32)
        if spectrum.size == 0:
            return np.empty((0,), dtype=np.int64), np.empty((0,), dtype=np.int32)

        high_bin = min(FINGERPRINT_MAX_FREQ_BIN, spectrum.shape[0])
        low_bin = min(FINGERPRINT_MIN_FREQ_BIN, max(0, high_bin - 1))
        band = spectrum[low_bin:high_bin, :]
        if band.size == 0:
            return np.empty((0,), dtype=np.int64), np.empty((0,), dtype=np.int32)

        db = librosa.amplitude_to_db(band, ref=np.max).astype(np.float32)
        local_max = maximum_filter(db, size=FINGERPRINT_PEAK_NEIGHBORHOOD, mode="constant")
        peak_mask = (db == local_max) & (db >= FINGERPRINT_PEAK_DB_THRESHOLD)

        peaks: List[Tuple[int, int, float]] = []
        for frame in range(peak_mask.shape[1]):
            freq_indices = np.flatnonzero(peak_mask[:, frame])
            if freq_indices.size == 0:
                continue
            strengths = db[freq_indices, frame]
            if freq_indices.size > FINGERPRINT_MAX_PEAKS_PER_FRAME:
                keep = np.argpartition(-strengths, FINGERPRINT_MAX_PEAKS_PER_FRAME - 1)[
                    :FINGERPRINT_MAX_PEAKS_PER_FRAME
                ]
                freq_indices = freq_indices[keep]
                strengths = strengths[keep]
            for freq_idx, strength in zip(freq_indices, strengths):
                peaks.append((frame, int(freq_idx + low_bin), float(strength)))

        if len(peaks) < 2:
            return np.empty((0,), dtype=np.int64), np.empty((0,), dtype=np.int32)

        peaks.sort(key=lambda item: (item[0], item[1]))
        hashes: List[int] = []
        frames: List[int] = []
        total_peaks = len(peaks)

        for i, (anchor_frame, anchor_freq, _anchor_strength) in enumerate(peaks):
            fanout = 0
            f1 = int(anchor_freq // FINGERPRINT_FREQ_QUANT)
            for j in range(i + 1, total_peaks):
                target_frame, target_freq, _target_strength = peaks[j]
                delta = int(target_frame - anchor_frame)
                if delta < FINGERPRINT_TARGET_MIN_DELTA:
                    continue
                if delta > FINGERPRINT_TARGET_MAX_DELTA:
                    break
                f2 = int(target_freq // FINGERPRINT_FREQ_QUANT)
                hash_value = (f1 << 24) | (f2 << 12) | delta
                hashes.append(int(hash_value))
                frames.append(int(anchor_frame))
                fanout += 1
                if fanout >= FINGERPRINT_TARGET_FANOUT:
                    break

        if not hashes:
            return np.empty((0,), dtype=np.int64), np.empty((0,), dtype=np.int32)

        if len(hashes) > FINGERPRINT_MAX_HASHES_PER_TRACK:
            idx = np.linspace(0, len(hashes) - 1, FINGERPRINT_MAX_HASHES_PER_TRACK).astype(int)
            hashes = [hashes[i] for i in idx]
            frames = [frames[i] for i in idx]

        return np.asarray(hashes, dtype=np.int64), np.asarray(frames, dtype=np.int32)
    except Exception:
        logger.exception("Landmark fingerprint extraction failed.")
        return np.empty((0,), dtype=np.int64), np.empty((0,), dtype=np.int32)


def collect_audio_files(source_dir: Path, recursive: bool) -> List[Path]:
    """Collect supported audio files from source directory."""
    if recursive:
        candidates = source_dir.rglob("*")
    else:
        candidates = source_dir.glob("*")

    audio_files = [p for p in candidates if p.is_file() and is_allowed_extension(p)]
    audio_files.sort(key=lambda p: str(p).lower())
    return audio_files


def safe_get_audio_duration_seconds(file_path: Path) -> float:
    """Read audio duration with tolerant fallback."""
    try:
        dur = float(librosa.get_duration(path=str(file_path)))
        if dur > 0:
            return dur
    except Exception:
        pass
    return 0.0


def load_index_waveform(file_path: Path) -> Tuple[np.ndarray, float]:
    """
    Load waveform used for indexing.
    Full-song indexing avoids blind spots where a short live capture lands between
    sampled windows of a long track.
    """
    duration = safe_get_audio_duration_seconds(file_path)
    if duration <= 0:
        wf = load_waveform(file_path, duration_seconds=INDEX_AUDIO_DURATION_SECONDS)
        return wf, round(float(wf.size / SAMPLE_RATE), 2)

    if INDEX_AUDIO_DURATION_SECONDS is None or duration <= INDEX_AUDIO_DURATION_SECONDS:
        wf = load_waveform(file_path, duration_seconds=None)
        return wf, round(float(duration), 2)

    if duration <= INDEX_MULTI_WINDOW_THRESHOLD_SECONDS:
        wf = load_waveform(file_path, duration_seconds=min(duration, INDEX_AUDIO_DURATION_SECONDS))
        return wf, round(float(duration), 2)

    half = INDEX_WINDOW_SECONDS / 2.0
    offsets = [
        0.0,
        max(0.0, (duration / 2.0) - half),
        max(0.0, duration - INDEX_WINDOW_SECONDS),
    ]
    chunks: List[np.ndarray] = []
    for start in offsets:
        chunk = load_waveform(
            file_path,
            duration_seconds=INDEX_WINDOW_SECONDS,
            offset_seconds=start,
        )
        if chunk.size:
            chunks.append(chunk)
    if not chunks:
        wf = load_waveform(file_path, duration_seconds=INDEX_AUDIO_DURATION_SECONDS)
        return wf, round(float(duration), 2)
    return np.concatenate(chunks).astype(np.float32), round(float(duration), 2)


def build_fast_matrices(records: Dict[str, SongRecord]) -> Tuple[List[str], np.ndarray]:
    """Build fast numpy matrix for vectorized global scoring."""
    names = sorted(records.keys())
    if not names:
        return [], np.empty((0, 0), dtype=np.float32)
    matrix = np.vstack([records[name].global_feature for name in names]).astype(np.float32)
    return names, matrix


def build_scoring_state(
    records: Dict[str, SongRecord],
    names: List[str],
    global_matrix: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    """
    Build normalized matrices used by retrieval scoring.
    Whitening reduces the "all songs look too similar" effect for cosine scores.
    """
    if not names or global_matrix.size == 0:
        empty_2d = np.empty((0, 0), dtype=np.float32)
        empty_1d = np.empty((0,), dtype=np.float32)
        return empty_2d, empty_1d, empty_1d, empty_1d, empty_1d, {}

    g_mean, g_std = fit_whitening_stats(global_matrix)
    scored_global_matrix = whiten_and_normalize_rows(global_matrix, g_mean, g_std)

    segment_samples: List[np.ndarray] = []
    for name in names:
        sampled = sample_rows_for_stats(
            records[name].segment_features,
            max_rows=SEGMENT_SCALER_SAMPLE_PER_TRACK,
        )
        if sampled.size:
            segment_samples.append(sampled)

    if segment_samples:
        segment_pool = np.vstack(segment_samples).astype(np.float32)
        s_mean, s_std = fit_whitening_stats(segment_pool)
    else:
        s_mean = np.empty((0,), dtype=np.float32)
        s_std = np.empty((0,), dtype=np.float32)

    scored_segments: Dict[str, np.ndarray] = {}
    for name in names:
        scored_segments[name] = whiten_and_normalize_rows(records[name].segment_features, s_mean, s_std)

    return scored_global_matrix, g_mean, g_std, s_mean, s_std, scored_segments


def build_fingerprint_lookup(records: Dict[str, SongRecord]) -> Dict[int, List[Tuple[str, int]]]:
    """Build hash -> [(song, anchor_frame)] lookup for landmark fingerprint voting."""
    lookup: Dict[int, List[Tuple[str, int]]] = {}
    for name, record in records.items():
        hashes = getattr(record, "fingerprint_hashes", np.empty((0,), dtype=np.int64))
        frames = getattr(record, "fingerprint_frames", np.empty((0,), dtype=np.int32))
        if hashes.size == 0 or frames.size == 0:
            continue
        count = min(int(hashes.shape[0]), int(frames.shape[0]))
        for hash_value, frame in zip(hashes[:count], frames[:count]):
            lookup.setdefault(int(hash_value), []).append((name, int(frame)))
    return lookup


def apply_index_state(
    new_index: Dict[str, SongRecord],
    new_names: List[str],
    new_matrix: np.ndarray,
    new_stats: dict,
    source_dir: Path,
) -> None:
    """Apply a freshly built index to global in-memory state."""
    global song_index, song_names, global_feature_matrix, scoring_global_feature_matrix, song_hash_lookup
    global fingerprint_lookup
    global current_source_dir, index_stats, lyrics_cache
    global global_feature_mean, global_feature_std, segment_feature_mean, segment_feature_std
    global segment_feature_matrix_by_song

    song_index = new_index
    song_names = new_names
    global_feature_matrix = new_matrix
    (
        scoring_global_feature_matrix,
        global_feature_mean,
        global_feature_std,
        segment_feature_mean,
        segment_feature_std,
        segment_feature_matrix_by_song,
    ) = build_scoring_state(
        records=new_index,
        names=new_names,
        global_matrix=new_matrix,
    )
    song_hash_lookup = {}
    for key, record in new_index.items():
        if record.file_sha1 and record.file_sha1 not in song_hash_lookup:
            song_hash_lookup[record.file_sha1] = key
    fingerprint_lookup = build_fingerprint_lookup(new_index)
    current_source_dir = source_dir
    index_stats = new_stats
    index_stats["last_error"] = ""
    lyrics_cache = {}


def rebuild_index_in_place(source_dir: Path, recursive: bool) -> dict:
    """Rebuild index and atomically publish it to in-memory state."""
    new_index, new_stats = build_song_index(source_dir, recursive=recursive)
    new_names, new_matrix = build_fast_matrices(new_index)
    with index_lock:
        apply_index_state(
            new_index=new_index,
            new_names=new_names,
            new_matrix=new_matrix,
            new_stats=new_stats,
            source_dir=source_dir,
        )
    return new_stats


def ensure_index_ready() -> Tuple[bool, str]:
    """
    Try one automatic bootstrap build if index is empty.
    Returns (ready, error_message).
    """
    global index_bootstrap_attempted

    if song_index:
        return True, ""

    recursive = bool(index_stats.get("recursive", True))
    source_dir = current_source_dir
    should_build = False
    with index_lock:
        if song_index:
            return True, ""
        if not index_bootstrap_attempted:
            index_bootstrap_attempted = True
            should_build = True
        elif index_stats.get("last_error"):
            return False, str(index_stats["last_error"])
        else:
            return False, "Index is empty. Build index from source folder."

    if not should_build:
        return False, "Index is empty. Build index from source folder."

    try:
        stats = rebuild_index_in_place(source_dir=source_dir, recursive=recursive)
        if stats.get("indexed_songs", 0) > 0:
            return True, ""
        message = "Index built but no supported decodable audio files were found."
    except Exception as exc:
        message = str(exc)

    with index_lock:
        index_stats["last_error"] = message
    return False, message


def build_song_index(source_dir: Path, recursive: bool) -> Tuple[Dict[str, SongRecord], dict]:
    """Build in-memory index from chosen source path."""
    if not source_dir.exists():
        raise FileNotFoundError(f"Source folder does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"Source path is not a folder: {source_dir}")

    started = time.perf_counter()
    records: Dict[str, SongRecord] = {}

    audio_files = collect_audio_files(source_dir, recursive=recursive)
    cache = load_feature_cache()
    cache_songs = cache.get("songs", {})
    updated_cache_songs: Dict[str, dict] = dict(cache_songs)
    active_source_keys = set()

    stats = {
        "source_dir": str(source_dir),
        "recursive": recursive,
        "scanned_files": len(audio_files),
        "indexed_songs": 0,
        "failed_files": 0,
        "lyrics_found": 0,
        "cache_hits": 0,
        "feature_dim": 0,
        "duration_sec": 0.0,
    }

    logger.info(
        "Indexing %d file(s) from %s (recursive=%s) ...",
        len(audio_files),
        source_dir,
        recursive,
    )

    for path in audio_files:
        try:
            resolved = str(path.resolve())
            active_source_keys.add(resolved)
            stat = path.stat()
            cache_key = resolved
            cached = cache_songs.get(cache_key)

            global_feature: np.ndarray
            segment_features: np.ndarray
            sequence_features: np.ndarray
            fingerprint_hashes: np.ndarray
            fingerprint_frames: np.ndarray
            duration_sec: float
            tempo_bpm: float
            key_label: str
            energy: float
            file_sha1: str
            lyrics = load_lyrics_for_audio(path)

            cache_ok = (
                isinstance(cached, dict)
                and cached.get("mtime_ns") == stat.st_mtime_ns
                and cached.get("size") == stat.st_size
                and isinstance(cached.get("global_feature"), np.ndarray)
                and isinstance(cached.get("segment_features"), np.ndarray)
                and isinstance(cached.get("sequence_features"), np.ndarray)
            )

            if cache_ok:
                global_feature = cached["global_feature"].astype(np.float32)
                segment_features = cached["segment_features"].astype(np.float32)
                sequence_features = cached["sequence_features"].astype(np.float32)
                cached_hashes = cached.get("fingerprint_hashes")
                cached_frames = cached.get("fingerprint_frames")
                duration_sec = float(cached.get("duration_sec", 0.0))
                tempo_bpm = float(cached.get("tempo_bpm", 0.0))
                key_label = str(cached.get("key_label", "unknown"))
                energy = float(cached.get("energy", 0.0))
                file_sha1 = str(cached.get("file_sha1", ""))
                if not file_sha1:
                    file_sha1 = compute_file_sha1(path)
                if not lyrics:
                    lyrics = cached.get("lyrics") or None
                if (
                    isinstance(cached_hashes, np.ndarray)
                    and isinstance(cached_frames, np.ndarray)
                    and cached_hashes.size > 0
                    and cached_frames.size > 0
                ):
                    fingerprint_hashes = cached_hashes.astype(np.int64)
                    fingerprint_frames = cached_frames.astype(np.int32)
                else:
                    waveform, _ = load_index_waveform(path)
                    fingerprint_hashes, fingerprint_frames = extract_landmark_fingerprints(waveform)
                stats["cache_hits"] += 1
            else:
                waveform, duration_sec = load_index_waveform(path)
                global_feature = extract_feature_from_waveform(waveform)
                segment_features = extract_segment_features(waveform)
                sequence_features = extract_sequence_features(waveform)
                fingerprint_hashes, fingerprint_frames = extract_landmark_fingerprints(waveform)
                meta = estimate_audio_metadata(waveform)
                tempo_bpm = float(meta["tempo_bpm"])
                key_label = str(meta["key_label"])
                energy = float(meta["energy"])
                file_sha1 = compute_file_sha1(path)

            relative_name = str(path.relative_to(source_dir))
            records[relative_name] = SongRecord(
                file_path=path,
                relative_name=relative_name,
                duration_sec=duration_sec,
                global_feature=global_feature,
                segment_features=segment_features,
                sequence_features=sequence_features,
                lyrics=lyrics,
                tempo_bpm=tempo_bpm,
                key_label=key_label,
                energy=energy,
                file_sha1=file_sha1,
                fingerprint_hashes=fingerprint_hashes,
                fingerprint_frames=fingerprint_frames,
            )

            updated_cache_songs[cache_key] = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "duration_sec": duration_sec,
                "global_feature": global_feature.astype(np.float32),
                "segment_features": segment_features.astype(np.float32),
                "sequence_features": sequence_features.astype(np.float32),
                "lyrics": lyrics,
                "tempo_bpm": tempo_bpm,
                "key_label": key_label,
                "energy": energy,
                "file_sha1": file_sha1,
                "fingerprint_hashes": fingerprint_hashes.astype(np.int64),
                "fingerprint_frames": fingerprint_frames.astype(np.int32),
            }
            stats["indexed_songs"] += 1
            if lyrics:
                stats["lyrics_found"] += 1
        except Exception as exc:
            stats["failed_files"] += 1
            logger.warning("Skipped %s: %s", path, exc)

    stats["duration_sec"] = round(time.perf_counter() - started, 2)
    if records:
        stats["feature_dim"] = int(next(iter(records.values())).global_feature.shape[0])

    # Keep cache entries from other source folders; only prune removed files under current source.
    source_prefix = str(source_dir.resolve()).lower().rstrip("\\/")
    for existing_key in list(updated_cache_songs.keys()):
        lowered = str(existing_key).lower()
        in_current_source = lowered == source_prefix or lowered.startswith(source_prefix + "\\")
        if in_current_source and existing_key not in active_source_keys:
            updated_cache_songs.pop(existing_key, None)

    save_feature_cache({"version": FEATURE_CACHE_VERSION, "songs": updated_cache_songs})

    logger.info(
        "Index complete | indexed=%d failed=%d lyrics=%d cache_hits=%d duration=%.2fs",
        stats["indexed_songs"],
        stats["failed_files"],
        stats["lyrics_found"],
        stats["cache_hits"],
        stats["duration_sec"],
    )
    return records, stats


def shortlist_candidate_indices(global_scores: np.ndarray, top_k: int) -> np.ndarray:
    """Shortlist top global matches before segment reranking (optimization)."""
    n = int(global_scores.shape[0])
    if n == 0:
        return np.array([], dtype=np.int64)

    shortlist_size = min(n, max(MIN_SHORTLIST, top_k * SHORTLIST_MULTIPLIER))
    if shortlist_size == n:
        return np.arange(n, dtype=np.int64)

    # Argpartition keeps complexity near O(n) for shortlist extraction.
    return np.argpartition(-global_scores, shortlist_size - 1)[:shortlist_size]


def segment_score(
    query_segments: np.ndarray,
    db_segments: np.ndarray,
    fallback: float,
) -> Tuple[float, int, float]:
    """
    Segment-voting score + best matching DB segment index.
    Returns: (score, best_db_segment_idx, peak_similarity)
    """
    if query_segments.size == 0 or db_segments.size == 0:
        return fallback, 0, fallback

    sims = query_segments @ db_segments.T
    best_per_query = np.max(sims, axis=1)
    score = float((0.7 * np.mean(best_per_query)) + (0.3 * np.median(best_per_query)))
    score = float(np.clip(score, -1.0, 1.0))

    max_flat_idx = int(np.argmax(sims))
    _, best_db_idx = np.unravel_index(max_flat_idx, sims.shape)
    peak = float(sims.flat[max_flat_idx])
    return score, int(best_db_idx), peak


def format_mmss(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 60:02d}:{s % 60:02d}"


def dtw_subsequence_score(query_sequence: np.ndarray, db_sequence: np.ndarray) -> Tuple[float, float]:
    """
    Compute subsequence DTW similarity on frame-level embeddings.
    Returns (score_0_to_1, match_start_seconds).
    """
    if query_sequence.size == 0 or db_sequence.size == 0:
        return 0.0, 0.0

    try:
        dmat, _ = librosa.sequence.dtw(
            X=query_sequence.T,
            Y=db_sequence.T,
            metric="cosine",
            subseq=True,
        )
        if dmat.size == 0:
            return 0.0, 0.0

        last_row = dmat[-1, :]
        end_idx = int(np.argmin(last_row))
        start_idx = max(0, end_idx - query_sequence.shape[0] + 1)
        normalized_cost = float(last_row[end_idx] / max(1, query_sequence.shape[0]))
        score = float(np.exp(-normalized_cost))
        return float(np.clip(score, 0.0, 1.0)), float(start_idx * SEQUENCE_HOP_SECONDS)
    except Exception:
        # Fallback when DTW fails unexpectedly.
        sims = query_sequence @ db_sequence.T
        if sims.size == 0:
            return 0.0, 0.0
        peak_idx = int(np.argmax(sims))
        _, best_db_idx = np.unravel_index(peak_idx, sims.shape)
        peak = float(sims.flat[peak_idx])
        score = float(np.clip((peak + 1.0) / 2.0, 0.0, 1.0))
        return score, float(best_db_idx * SEQUENCE_HOP_SECONDS)


def detect_top_matches_from_features(
    query_global: np.ndarray,
    query_segments: np.ndarray,
    query_sequence: np.ndarray,
    top_k: int,
    profile: str = "default",
) -> List[dict]:
    """Vectorized retrieval + segment rerank + DTW rerank for final ordering."""
    if not song_names or scoring_global_feature_matrix.size == 0:
        return []

    query_global_scored = whiten_and_normalize_vector(
        query_global,
        global_feature_mean,
        global_feature_std,
    )
    query_segments_scored = whiten_and_normalize_rows(
        query_segments,
        segment_feature_mean,
        segment_feature_std,
    )

    global_scores = scoring_global_feature_matrix @ query_global_scored
    candidate_indices = shortlist_candidate_indices(global_scores, top_k=top_k)

    pre_results: List[dict] = []
    for idx in candidate_indices:
        song_name = song_names[int(idx)]
        record = song_index[song_name]
        scored_db_segments = segment_feature_matrix_by_song.get(song_name, record.segment_features)
        g_score = float(global_scores[int(idx)])
        s_score, best_db_idx, peak_similarity = segment_score(
            query_segments=query_segments_scored,
            db_segments=scored_db_segments,
            fallback=g_score,
        )
        base_score = float((0.45 * g_score) + (0.55 * s_score))
        match_seconds = float(best_db_idx * SEGMENT_HOP_SECONDS)
        pre_results.append(
            {
                "song": record.relative_name,
                "full_path": str(record.file_path),
                "duration_sec": record.duration_sec,
                "score": base_score,
                "global_score": g_score,
                "segment_score": s_score,
                "dtw_score": 0.0,
                "peak_similarity": peak_similarity,
                "match_seconds": match_seconds,
                "match_mmss": format_mmss(match_seconds),
                "lyrics_available": bool(record.lyrics or lyrics_cache.get(record.relative_name.lower().strip())),
            }
        )

    pre_results.sort(key=lambda item: item["score"], reverse=True)

    mode = (profile or "default").strip().lower()
    if mode == "live":
        rerank_count = len(pre_results)
        final_w_global = 0.20
        final_w_segment = 0.20
        final_w_dtw = 0.60
    else:
        rerank_count = min(SEQUENCE_RERANK_LIMIT, len(pre_results))
        final_w_global = 0.36
        final_w_segment = 0.40
        final_w_dtw = 0.24

    for item in pre_results[:rerank_count]:
        record = song_index[item["song"]]
        dtw_score, dtw_match_seconds = dtw_subsequence_score(
            query_sequence=query_sequence,
            db_sequence=record.sequence_features,
        )
        dtw_centered = (2.0 * dtw_score) - 1.0  # map to [-1, 1]
        item["dtw_score"] = dtw_score
        item["score"] = float(
            (final_w_global * item["global_score"])
            + (final_w_segment * item["segment_score"])
            + (final_w_dtw * dtw_centered)
        )
        item["match_seconds"] = dtw_match_seconds
        item["match_mmss"] = format_mmss(dtw_match_seconds)

    results = sorted(pre_results, key=lambda item: item["score"], reverse=True)
    return results[: max(1, top_k)]


def detect_top_matches_by_fingerprint(query_waveform: np.ndarray, top_k: int) -> List[dict]:
    """Return candidates from landmark fingerprint offset voting."""
    if query_waveform.size == 0 or not fingerprint_lookup:
        return []

    query_hashes, query_frames = extract_landmark_fingerprints(query_waveform)
    if query_hashes.size == 0 or query_frames.size == 0:
        return []

    offset_votes: Dict[Tuple[str, int], int] = {}
    song_totals: Dict[str, int] = {}
    count = min(int(query_hashes.shape[0]), int(query_frames.shape[0]))

    for query_hash, query_frame in zip(query_hashes[:count], query_frames[:count]):
        matches = fingerprint_lookup.get(int(query_hash))
        if not matches:
            continue
        q_frame = int(query_frame)
        for song_name, db_frame in matches:
            offset_bucket = int(round((int(db_frame) - q_frame) / max(1, FINGERPRINT_OFFSET_BUCKET_FRAMES)))
            key = (song_name, offset_bucket)
            offset_votes[key] = offset_votes.get(key, 0) + 1
            song_totals[song_name] = song_totals.get(song_name, 0) + 1

    if not offset_votes:
        return []

    best_by_song: Dict[str, Tuple[int, int]] = {}
    for (song_name, offset_bucket), votes in offset_votes.items():
        current = best_by_song.get(song_name)
        if current is None or votes > current[0]:
            best_by_song[song_name] = (int(votes), int(offset_bucket))

    results: List[dict] = []
    query_count = max(1, count)
    for song_name, (aligned_votes, offset_bucket) in best_by_song.items():
        record = song_index.get(song_name)
        if not record:
            continue
        coverage = float(aligned_votes / query_count)
        total_votes = int(song_totals.get(song_name, 0))
        score = float(np.clip((coverage / 0.08), 0.0, 1.0))
        match_seconds = float(
            max(0, offset_bucket * FINGERPRINT_OFFSET_BUCKET_FRAMES)
            * FINGERPRINT_HOP_LENGTH
            / SAMPLE_RATE
        )
        results.append(
            {
                "song": record.relative_name,
                "full_path": str(record.file_path),
                "duration_sec": record.duration_sec,
                "score": score,
                "global_score": 0.0,
                "segment_score": 0.0,
                "dtw_score": 0.0,
                "peak_similarity": 0.0,
                "match_seconds": match_seconds,
                "match_mmss": format_mmss(match_seconds),
                "lyrics_available": bool(record.lyrics or lyrics_cache.get(record.relative_name.lower().strip())),
                "fingerprint_match": True,
                "fingerprint_aligned_matches": aligned_votes,
                "fingerprint_total_matches": total_votes,
                "fingerprint_query_hashes": query_count,
                "fingerprint_coverage": coverage,
            }
        )

    results.sort(
        key=lambda item: (
            int(item.get("fingerprint_aligned_matches", 0)),
            float(item.get("fingerprint_coverage", 0.0)),
        ),
        reverse=True,
    )
    return results[: max(1, top_k)]


def is_reliable_fingerprint_match(item: dict) -> bool:
    return (
        bool(item.get("fingerprint_match"))
        and int(item.get("fingerprint_aligned_matches", 0)) >= FINGERPRINT_MIN_ALIGNED_MATCHES
        and float(item.get("fingerprint_coverage", 0.0)) >= FINGERPRINT_MIN_QUERY_COVERAGE
    )


def promote_results_with_fingerprints(
    results: List[dict],
    fingerprint_results: List[dict],
    top_k: int,
) -> List[dict]:
    """Merge fingerprint candidates and promote a reliable offset-voted match."""
    merged: Dict[str, dict] = {item["song"]: dict(item) for item in results}
    for fp_item in fingerprint_results:
        existing = merged.get(fp_item["song"])
        if existing:
            existing["fingerprint_match"] = bool(fp_item.get("fingerprint_match"))
            existing["fingerprint_aligned_matches"] = int(fp_item.get("fingerprint_aligned_matches", 0))
            existing["fingerprint_total_matches"] = int(fp_item.get("fingerprint_total_matches", 0))
            existing["fingerprint_query_hashes"] = int(fp_item.get("fingerprint_query_hashes", 0))
            existing["fingerprint_coverage"] = float(fp_item.get("fingerprint_coverage", 0.0))
            if float(fp_item.get("fingerprint_coverage", 0.0)) > 0:
                existing["match_seconds"] = float(fp_item.get("match_seconds", existing.get("match_seconds", 0.0)))
                existing["match_mmss"] = fp_item.get("match_mmss", existing.get("match_mmss", "00:00"))
        else:
            merged[fp_item["song"]] = dict(fp_item)

    merged_list = list(merged.values())
    reliable = [item for item in merged_list if is_reliable_fingerprint_match(item)]
    if reliable:
        best = max(
            reliable,
            key=lambda item: (
                int(item.get("fingerprint_aligned_matches", 0)),
                float(item.get("fingerprint_coverage", 0.0)),
            ),
        )
        promoted = dict(best)
        promoted["fingerprint_promoted"] = True
        promoted["pre_fingerprint_score"] = float(promoted.get("score", 0.0))
        promoted["score"] = float(max(float(promoted.get("score", 0.0)), FINGERPRINT_PROMOTION_SCORE))
        rest = [item for item in merged_list if item["song"] != promoted["song"]]
        rest.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return ([promoted] + rest)[: max(1, top_k)]

    merged_list.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return merged_list[: max(1, top_k)]


def detect_top_matches_exhaustive_sequence(query_waveform: np.ndarray, top_k: int) -> List[dict]:
    """DTW-check live query sequence against every indexed song."""
    if query_waveform.size == 0 or not song_index:
        return []

    variants: List[Tuple[float, np.ndarray]] = [(1.00, query_waveform.astype(np.float32))]
    focus_25 = select_loudest_window(query_waveform, window_seconds=25.0, hop_seconds=0.8)
    if focus_25.size >= int(8.0 * SAMPLE_RATE):
        variants.append((1.00, focus_25.astype(np.float32)))
    focus_12 = select_loudest_window(query_waveform, window_seconds=12.0, hop_seconds=0.5)
    if focus_12.size >= int(6.0 * SAMPLE_RATE):
        variants.append((0.92, focus_12.astype(np.float32)))

    best_by_song: Dict[str, dict] = {}
    max_frames = int(MAX_QUERY_SEQUENCE_SECONDS / max(SEQUENCE_HOP_SECONDS, 1e-6))

    for weight, waveform in variants:
        query_sequence = extract_sequence_features(waveform)
        if max_frames > 0 and query_sequence.shape[0] > max_frames:
            query_sequence = query_sequence[:max_frames]
        if query_sequence.size == 0:
            continue

        for song_name, record in song_index.items():
            dtw_score, match_seconds = dtw_subsequence_score(
                query_sequence=query_sequence,
                db_sequence=record.sequence_features,
            )
            weighted_dtw = float(weight * dtw_score)
            existing = best_by_song.get(song_name)
            if existing and weighted_dtw <= float(existing.get("weighted_sequence_score", 0.0)):
                continue
            score = float(np.clip((2.0 * dtw_score) - 1.0, -1.0, 1.0))
            best_by_song[song_name] = {
                "song": record.relative_name,
                "full_path": str(record.file_path),
                "duration_sec": record.duration_sec,
                "score": score,
                "global_score": 0.0,
                "segment_score": 0.0,
                "dtw_score": float(dtw_score),
                "peak_similarity": 0.0,
                "match_seconds": float(match_seconds),
                "match_mmss": format_mmss(match_seconds),
                "lyrics_available": bool(record.lyrics or lyrics_cache.get(record.relative_name.lower().strip())),
                "exhaustive_sequence_match": True,
                "exhaustive_sequence_score": float(dtw_score),
                "weighted_sequence_score": weighted_dtw,
            }

    results = list(best_by_song.values())
    results.sort(key=lambda item: float(item.get("weighted_sequence_score", 0.0)), reverse=True)
    return results[: max(1, top_k)]


def promote_results_with_exhaustive_sequence(
    results: List[dict],
    sequence_results: List[dict],
    top_k: int,
) -> List[dict]:
    """Merge all-song DTW candidates and promote a stronger sequence match."""
    merged: Dict[str, dict] = {item["song"]: dict(item) for item in results}
    for seq_item in sequence_results:
        existing = merged.get(seq_item["song"])
        if existing:
            seq_score = float(seq_item.get("exhaustive_sequence_score", 0.0))
            existing["exhaustive_sequence_match"] = True
            existing["exhaustive_sequence_score"] = seq_score
            if seq_score > float(existing.get("dtw_score", 0.0)):
                existing["dtw_score"] = seq_score
                existing["match_seconds"] = float(seq_item.get("match_seconds", existing.get("match_seconds", 0.0)))
                existing["match_mmss"] = seq_item.get("match_mmss", existing.get("match_mmss", "00:00"))
        else:
            merged[seq_item["song"]] = dict(seq_item)

    merged_list = list(merged.values())
    if not merged_list:
        return []

    top = max(merged_list, key=lambda item: float(item.get("score", 0.0)))
    best_seq = max(merged_list, key=lambda item: float(item.get("exhaustive_sequence_score", 0.0)))
    best_seq_score = float(best_seq.get("exhaustive_sequence_score", 0.0))
    top_seq_score = float(top.get("exhaustive_sequence_score", top.get("dtw_score", 0.0)))

    if (
        best_seq_score >= LIVE_SEQUENCE_PROMOTION_MIN_DTW
        and (
            best_seq["song"] != top["song"]
            or float(top.get("score", 0.0)) < LIVE_TOP_MATCH_MIN_SCORE_FOR_ACCEPT
        )
        and best_seq_score >= top_seq_score + LIVE_SEQUENCE_PROMOTION_MIN_DTW_GAP
    ):
        promoted = dict(best_seq)
        promoted["sequence_promoted"] = True
        promoted["pre_sequence_score"] = float(promoted.get("score", 0.0))
        promoted["score"] = float(
            np.clip(
                max(
                    float(promoted.get("score", 0.0)),
                    float(top.get("score", 0.0)) + LIVE_SEQUENCE_PROMOTION_BONUS,
                    FINGERPRINT_PROMOTION_SCORE,
                ),
                -1.0,
                1.0,
            )
        )
        rest = [item for item in merged_list if item["song"] != promoted["song"]]
        rest.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return ([promoted] + rest)[: max(1, top_k)]

    merged_list.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return merged_list[: max(1, top_k)]


def detect_top_matches_live_consensus(
    query_waveform: np.ndarray,
    top_k: int,
) -> List[dict]:
    """
    Robust live-mode retrieval: run multiple query variants and vote.
    This reduces false matches from tap noise, silence, and room coloration.
    """
    if query_waveform.size == 0:
        return []

    variants: List[Tuple[float, np.ndarray]] = [(1.00, query_waveform.astype(np.float32))]
    offset = int(LIVE_VARIANT_OFFSET_SECONDS * SAMPLE_RATE)
    min_len = int(LIVE_VARIANT_MIN_SECONDS * SAMPLE_RATE)
    if query_waveform.size > offset + min_len:
        variants.append((0.95, query_waveform[offset:].astype(np.float32)))

    focus_8 = select_loudest_window(query_waveform, window_seconds=8.0, hop_seconds=0.4)
    if focus_8.size >= min_len:
        variants.append((1.00, focus_8.astype(np.float32)))
    focus_6 = select_loudest_window(query_waveform, window_seconds=6.0, hop_seconds=0.4)
    if focus_6.size >= min_len:
        variants.append((0.90, focus_6.astype(np.float32)))

    weighted_results: List[Tuple[float, List[dict]]] = []
    per_variant_top_k = max(top_k, LIVE_CONSENSUS_TOP_CANDIDATES, LIVE_VARIANT_TOP_K)
    for weight, waveform in variants:
        qg, qs, qq = extract_query_features_from_waveform(waveform)
        res = detect_top_matches_from_features(
            query_global=qg,
            query_segments=qs,
            query_sequence=qq,
            top_k=per_variant_top_k,
            profile="live",
        )
        if res:
            weighted_results.append((weight, res))

    if not weighted_results:
        return []

    aggregate: Dict[str, float] = {}
    best_by_song: Dict[str, dict] = {}
    candidate_count = max(LIVE_CONSENSUS_TOP_CANDIDATES, top_k, per_variant_top_k)

    for weight, results in weighted_results:
        for rank, item in enumerate(results[:candidate_count], start=1):
            song_name = item["song"]
            vote = float(weight * (1.0 / rank) * item["score"])
            aggregate[song_name] = aggregate.get(song_name, 0.0) + vote
            existing = best_by_song.get(song_name)
            if existing is None or float(item["score"]) > float(existing.get("score", -2.0)):
                best_by_song[song_name] = dict(item)

    if not aggregate:
        return []

    ranked = sorted(aggregate.items(), key=lambda kv: kv[1], reverse=True)
    final: List[dict] = []
    for song_name, consensus_score in ranked[: max(1, top_k)]:
        item = dict(best_by_song[song_name])
        item["consensus_score"] = float(consensus_score)
        blended = (0.70 * float(item["score"])) + (0.30 * float(np.tanh(consensus_score)))
        item["score"] = float(np.clip(blended, -1.0, 1.0))
        final.append(item)
    final.sort(key=lambda item: item["score"], reverse=True)

    # Rescue ambiguous live matches when DTW strongly favors a lower-ranked candidate.
    if len(final) >= 2:
        top = final[0]
        best_dtw = max(final, key=lambda item: float(item.get("dtw_score", 0.0)))
        if best_dtw["song"] != top["song"]:
            best_dtw_score = float(best_dtw.get("dtw_score", 0.0))
            dtw_gap = best_dtw_score - float(top.get("dtw_score", 0.0))
            score_gap = float(top.get("score", 0.0)) - float(best_dtw.get("score", 0.0))
            standard_rescue = (
                best_dtw_score >= LIVE_DTW_RESCUE_MIN_ABS
                and dtw_gap >= LIVE_DTW_RESCUE_MIN_GAP
                and score_gap <= LIVE_DTW_RESCUE_MAX_SCORE_GAP
            )
            strong_dtw_rescue = (
                best_dtw_score >= LIVE_DTW_RESCUE_STRONG_ABS
                and dtw_gap >= LIVE_DTW_RESCUE_STRONG_MIN_GAP
                and score_gap <= LIVE_DTW_RESCUE_STRONG_MAX_SCORE_GAP
            )
            if standard_rescue or strong_dtw_rescue:
                promoted = dict(best_dtw)
                promoted["dtw_rescued"] = True
                promoted["pre_rescue_score"] = float(promoted["score"])
                promoted["score"] = float(
                    np.clip(
                        max(
                            float(promoted["score"]) + LIVE_DTW_RESCUE_BONUS,
                            float(top.get("score", 0.0)) + LIVE_DTW_RESCUE_BONUS,
                        ),
                        -1.0,
                        1.0,
                    )
                )
                remaining = [item for item in final if item["song"] != promoted["song"]]
                final = [promoted] + remaining

    final = promote_live_candidate_by_evidence(final)
    return final[: max(1, top_k)]


def detect_top_matches_from_file(query_file: Path, top_k: int) -> List[dict]:
    query_global, query_segments, query_sequence = extract_query_features(
        query_file,
        duration_seconds=QUERY_AUDIO_DURATION_SECONDS,
    )
    return detect_top_matches_from_features(
        query_global=query_global,
        query_segments=query_segments,
        query_sequence=query_sequence,
        top_k=top_k,
    )


def detect_top_matches_from_indexed_snippet(
    source_song_key: str,
    start_seconds: float,
    snippet_duration: float,
    top_k: int,
) -> List[dict]:
    if source_song_key not in song_index:
        return []

    source = song_index[source_song_key]
    query_global, query_segments, query_sequence = extract_query_features(
        source.file_path,
        duration_seconds=snippet_duration,
        offset_seconds=start_seconds,
    )
    return detect_top_matches_from_features(
        query_global=query_global,
        query_segments=query_segments,
        query_sequence=query_sequence,
        top_k=top_k,
    )


def estimate_confidence(results: List[dict]) -> Tuple[float, str]:
    """
    Confidence heuristic using top score and margin.
    This is not a calibrated probability.
    """
    if not results:
        return 0.0, "low"

    top_score = results[0]["score"]
    second_score = results[1]["score"] if len(results) > 1 else top_score - 0.15
    margin = max(0.0, top_score - second_score)

    absolute_component = np.clip((top_score + 1.0) / 2.0, 0.0, 1.0)
    margin_component = np.clip(margin * 5.0, 0.0, 1.0)
    confidence = float(np.clip((0.55 * absolute_component) + (0.45 * margin_component), 0.0, 1.0))

    if confidence >= 0.82:
        label = "high"
    elif confidence >= 0.55:
        label = "medium"
    else:
        label = "low"
    return confidence, label


def match_margin(results: List[dict]) -> float:
    if not results:
        return 0.0
    top_score = float(results[0].get("score", -1.0))
    second_score = float(results[1].get("score", top_score - 0.15)) if len(results) > 1 else (top_score - 0.15)
    return float(top_score - second_score)


def has_reliable_match(results: List[dict]) -> bool:
    """Accept clear rank-1 matches even when the confidence heuristic is conservative."""
    if not results:
        return False
    top = results[0]
    top_score = float(top.get("score", -1.0))
    top_dtw = float(top.get("dtw_score", 0.0))
    margin = match_margin(results)
    if is_reliable_fingerprint_match(top):
        return True
    if bool(top.get("sequence_promoted")) and float(top.get("exhaustive_sequence_score", 0.0)) >= LIVE_SEQUENCE_PROMOTION_MIN_DTW:
        return True
    if top_score >= STRONG_MATCH_MIN_SCORE and top_dtw >= STRONG_MATCH_MIN_DTW and margin >= STRONG_MATCH_MIN_MARGIN:
        return True
    return top_score >= RELIABLE_MATCH_MIN_SCORE and top_dtw >= RELIABLE_MATCH_MIN_DTW and margin >= RELIABLE_MATCH_MIN_MARGIN


def live_candidate_evidence_score(item: dict) -> float:
    """
    DTW-heavy live score used only for reranking noisy microphone candidates.
    Global/segment features can be inflated by room coloration, so DTW carries most weight.
    """
    dtw = float(np.clip(float(item.get("dtw_score", 0.0)), 0.0, 1.0))
    score = float(np.clip(float(item.get("score", 0.0)), 0.0, 1.0))
    consensus = float(np.clip(float(np.tanh(float(item.get("consensus_score", 0.0)))), 0.0, 1.0))
    return float((0.70 * dtw) + (0.20 * score) + (0.10 * consensus))


def is_promotable_live_candidate(item: dict) -> bool:
    return (
        float(item.get("dtw_score", 0.0)) >= LIVE_PROMOTION_MIN_DTW
        and live_candidate_evidence_score(item) >= LIVE_PROMOTION_MIN_EVIDENCE
    )


def promote_live_candidate_by_evidence(results: List[dict]) -> List[dict]:
    """Promote a lower-ranked live candidate when its DTW evidence is stronger than the current top."""
    if not results:
        return results

    enriched = [dict(item) for item in results]
    for item in enriched:
        item["live_evidence_score"] = live_candidate_evidence_score(item)

    if len(enriched) < 2:
        return enriched

    top = enriched[0]
    promotable = [item for item in enriched if is_promotable_live_candidate(item)]
    if not promotable:
        return enriched

    best = max(promotable, key=lambda item: float(item.get("live_evidence_score", 0.0)))
    if best["song"] == top["song"]:
        return enriched

    evidence_gap = float(best.get("live_evidence_score", 0.0)) - float(top.get("live_evidence_score", 0.0))
    dtw_gap = float(best.get("dtw_score", 0.0)) - float(top.get("dtw_score", 0.0))
    top_is_weak = not is_promotable_live_candidate(top)

    if top_is_weak or evidence_gap >= LIVE_PROMOTION_MIN_EVIDENCE_GAP or dtw_gap >= LIVE_PROMOTION_MIN_DTW_GAP:
        promoted = dict(best)
        promoted["evidence_promoted"] = True
        promoted["pre_promotion_score"] = float(promoted.get("score", 0.0))
        promoted["score"] = float(
            np.clip(
                max(
                    float(promoted.get("score", 0.0)),
                    float(top.get("score", 0.0)) + LIVE_DTW_RESCUE_BONUS,
                ),
                -1.0,
                1.0,
            )
        )
        remaining = [item for item in enriched if item["song"] != promoted["song"]]
        return [promoted] + remaining

    return enriched


def has_reliable_live_match(results: List[dict]) -> bool:
    """Live recordings can score lower overall; accept when sequence and consensus agree."""
    if not results:
        return False

    top = results[0]
    top_score = float(top.get("score", -1.0))
    margin = match_margin(results)
    top_dtw = float(top.get("dtw_score", 0.0))
    consensus = float(top.get("consensus_score", 0.0))

    if has_reliable_match(results):
        return True
    if top_dtw < LIVE_MIN_DTW_FOR_ACCEPT:
        return False
    if top.get("evidence_promoted") and is_promotable_live_candidate(top):
        return True
    if top.get("sequence_promoted") and float(top.get("exhaustive_sequence_score", 0.0)) >= LIVE_SEQUENCE_PROMOTION_MIN_DTW:
        return True
    if top.get("dtw_rescued") and top_dtw >= LIVE_DTW_RESCUED_MIN_ACCEPT:
        return True
    if (
        top_score >= LIVE_TOP_MATCH_MIN_SCORE_FOR_ACCEPT
        and top_dtw >= LIVE_TOP_MATCH_MIN_DTW_FOR_ACCEPT
        and margin >= LIVE_TOP_MATCH_MIN_MARGIN_FOR_ACCEPT
    ):
        return True
    if (
        top_score < LOCAL_MIN_SCORE_FOR_FINAL
        and top_dtw >= LIVE_LOW_SCORE_MIN_DTW_FOR_ACCEPT
        and consensus >= LIVE_MIN_CONSENSUS_FOR_ACCEPT
        and margin >= LIVE_LOW_SCORE_MIN_MARGIN_FOR_ACCEPT
    ):
        return True
    return (
        top_score >= LOCAL_MIN_SCORE_FOR_FINAL
        and top_dtw >= RELIABLE_MATCH_MIN_DTW
        and margin >= LIVE_MIN_MARGIN_FOR_ACCEPT
    )


def should_reject_uncertain_match(
    results: List[dict],
    confidence: float,
    is_live_capture: bool,
) -> bool:
    """
    Reject uncertain detections instead of returning a likely wrong song.
    """
    if not DETECTION_REJECT_UNCERTAIN_MATCHES:
        return False
    if not results:
        return True

    top_score = float(results[0].get("score", -1.0))
    margin = match_margin(results)

    if has_reliable_match(results):
        return False

    if is_live_capture:
        if has_reliable_live_match(results):
            return False
        return True

    # Existing low-confidence gate.
    if confidence < LOCAL_MIN_CONFIDENCE_FOR_FINAL or top_score < LOCAL_MIN_SCORE_FOR_FINAL:
        return True

    # Ambiguous top-2 ranking (small margin) should not produce a hard match.
    if margin < 0.04 and top_score < (LOCAL_MIN_SCORE_FOR_FINAL + 0.08):
        return True

    # Live mic is noisier; require either clear margin or stronger DTW support.
    if is_live_capture:
        top_dtw = float(results[0].get("dtw_score", 0.0))
        if margin < LIVE_MIN_MARGIN_FOR_ACCEPT and top_dtw < LIVE_MIN_DTW_FOR_ACCEPT:
            return True

    return False


def get_lan_urls(port: int = 5000) -> List[str]:
    """Best-effort local network URLs so phone can open the app from laptop."""
    ips = set()
    preferred_ip = None
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip = item[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    # Fallback trick: detect outbound interface without sending data.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            preferred_ip = ip
            ips.add(ip)
        sock.close()
    except Exception:
        pass

    ordered_ips = sorted(ips)
    if preferred_ip and preferred_ip in ordered_ips:
        ordered_ips.remove(preferred_ip)
        ordered_ips.insert(0, preferred_ip)
    return [f"http://{ip}:{port}" for ip in ordered_ips]


def get_primary_bind_host() -> str:
    """
    Bind to one host only (user requested one IP, not multiple host outputs).
    Priority:
    1) APP_HOST env variable
    2) First detected LAN IPv4
    3) localhost
    """
    env_host = os.environ.get("APP_HOST", "").strip()
    if env_host:
        return env_host

    lan_urls = get_lan_urls(port=5000)
    if lan_urls:
        first = lan_urls[0]
        return first.split("://", 1)[1].split(":", 1)[0]
    return "127.0.0.1"


def is_https_runtime_available() -> bool:
    """Check whether Flask dev HTTPS (adhoc cert) can be used."""
    try:
        import cryptography  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def detect_from_uploaded_stream(uploaded, top_k: int, capture_mode: str = "upload") -> dict:
    """Shared detection logic for form upload and live mic API."""
    if uploaded is None:
        raise ValueError("No file uploaded.")

    original_name = uploaded.filename or "recording"
    safe_name = secure_filename(original_name)
    suffix = infer_audio_extension(safe_name or original_name, uploaded.mimetype or "")
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise ValueError(
            "Unsupported file format. "
            f"Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"
        )

    temp_path: Optional[Path] = None
    started = time.perf_counter()
    try:
        with NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as tmp:
            temp_path = Path(tmp.name)
        uploaded.save(str(temp_path))

        uploaded_sha1 = compute_file_sha1(temp_path)
        exact_song = song_hash_lookup.get(uploaded_sha1)
        is_live_capture = (capture_mode or "").strip().lower() == "live"

        query_offset_seconds = LIVE_QUERY_OFFSET_SECONDS if is_live_capture else 0.0

        query_waveform = load_waveform(
            temp_path,
            duration_seconds=QUERY_AUDIO_DURATION_SECONDS,
            offset_seconds=query_offset_seconds,
        )
        live_query_waveform = query_waveform.astype(np.float32)
        if is_live_capture:
            meta_waveform = select_loudest_window(
                live_query_waveform,
                window_seconds=LIVE_FOCUS_WINDOW_SECONDS,
                hop_seconds=0.5,
            )
            if meta_waveform.size < int(LIVE_FOCUS_MIN_SECONDS * SAMPLE_RATE):
                meta_waveform = live_query_waveform
            query_meta = estimate_audio_metadata(meta_waveform)
        else:
            query_meta = estimate_audio_metadata(query_waveform)

        external_fallback = None
        used_external_fallback = False
        fallback_attempted = False
        low_conf_local = False
        top_local_score = 1.0

        if exact_song:
            best_record = song_index[exact_song]
            results = [
                {
                    "song": best_record.relative_name,
                    "full_path": str(best_record.file_path),
                    "duration_sec": best_record.duration_sec,
                    "score": 1.0,
                    "global_score": 1.0,
                    "segment_score": 1.0,
                    "dtw_score": 1.0,
                    "peak_similarity": 1.0,
                    "match_seconds": 0.0,
                    "match_mmss": "00:00",
                    "lyrics_available": bool(
                        best_record.lyrics or lyrics_cache.get(best_record.relative_name.lower().strip())
                    ),
                    "exact_file_match": True,
                }
            ]
            confidence = 1.0
            confidence_label = "high"
        else:
            fingerprint_results: List[dict] = []
            if is_live_capture:
                fingerprint_results = detect_top_matches_by_fingerprint(
                    live_query_waveform,
                    top_k=max(top_k, 10),
                )
                if fingerprint_results and is_reliable_fingerprint_match(fingerprint_results[0]):
                    results = promote_results_with_fingerprints(
                        results=[],
                        fingerprint_results=fingerprint_results,
                        top_k=top_k,
                    )
                else:
                    results = detect_top_matches_live_consensus(
                        query_waveform=live_query_waveform,
                        top_k=top_k,
                    )
            else:
                query_global = extract_feature_from_waveform(query_waveform)
                query_segments = extract_segment_features(query_waveform)
                query_sequence = extract_sequence_features(query_waveform)
                max_frames = int(MAX_QUERY_SEQUENCE_SECONDS / max(SEQUENCE_HOP_SECONDS, 1e-6))
                if max_frames > 0 and query_sequence.shape[0] > max_frames:
                    query_sequence = query_sequence[:max_frames]

                results = detect_top_matches_from_features(
                    query_global=query_global,
                    query_segments=query_segments,
                    query_sequence=query_sequence,
                    top_k=top_k,
                    profile="default",
                )
            if not (is_live_capture and results and is_reliable_fingerprint_match(results[0])):
                if not fingerprint_results:
                    fingerprint_results = detect_top_matches_by_fingerprint(
                        live_query_waveform if is_live_capture else query_waveform,
                        top_k=max(top_k, 10),
                    )
                results = promote_results_with_fingerprints(
                    results=results,
                    fingerprint_results=fingerprint_results,
                    top_k=top_k,
                )
            if is_live_capture and not has_reliable_match(results):
                sequence_results = detect_top_matches_exhaustive_sequence(
                    live_query_waveform,
                    top_k=max(top_k, LIVE_EXHAUSTIVE_SEQUENCE_TOP_K),
                )
                results = promote_results_with_exhaustive_sequence(
                    results=results,
                    sequence_results=sequence_results,
                    top_k=top_k,
                )
            if not results:
                raise ValueError("No match found.")
            confidence, confidence_label = estimate_confidence(results)

            # Optional external API fallback when local confidence is weak.
            top_local_score = float(results[0]["score"])
            reliable_live_match = is_live_capture and has_reliable_live_match(results)
            low_conf_local = (
                not reliable_live_match
                and (
                    confidence < LOCAL_MIN_CONFIDENCE_FOR_FINAL
                    or top_local_score < LOCAL_MIN_SCORE_FOR_FINAL
                )
            )
            if low_conf_local:
                fallback_attempted = True
                fallback_waveform = live_query_waveform if is_live_capture else query_waveform
                external_fallback = external_shazam_fallback(query_waveform=fallback_waveform)
                if external_fallback:
                    used_external_fallback = True
            if should_reject_uncertain_match(
                results=results,
                confidence=confidence,
                is_live_capture=is_live_capture,
            ):
                raise ValueError("Couldn't detect the song.")

        best = results[0]
        if is_live_capture:
            lyrics_preview, lyrics_source = get_cached_or_local_song_lyrics(best["song"])
        else:
            lyrics_preview, lyrics_source = get_best_song_lyrics(best["song"])
        best_record = song_index[best["song"]]
        start_preview = max(0.0, float(best["match_seconds"]) - 3.0)
        encoded_song = quote(best["song"], safe="")
        latency_ms = int((time.perf_counter() - started) * 1000)
        tempo_diff = round(abs(query_meta["tempo_bpm"] - best_record.tempo_bpm), 2)
        energy_diff = round(abs(query_meta["energy"] - best_record.energy), 6)

        low_conf_note = ""
        if low_conf_local:
            if used_external_fallback and external_fallback:
                low_conf_note = (
                    " | low confidence local match"
                    f" | external suggestion: {external_fallback['title']}"
                    f"{(' - ' + external_fallback['artist']) if external_fallback['artist'] else ''}"
                )
            else:
                low_conf_note = " | low confidence local match (external fallback unavailable)"

        return {
            "message": (
                (
                    f"Detected song: {best['song']} "
                    f"(score: {best['score']:.4f}, match at {best['match_mmss']}, "
                    f"confidence: {confidence:.2f} - {confidence_label})"
                )
                + (" | exact file match" if exact_song else "")
                + low_conf_note
            ),
            "best_song": best["song"],
            "top_matches": results,
            "confidence": confidence,
            "confidence_label": confidence_label,
            "lyrics_preview": lyrics_preview,
            "lyrics_source": lyrics_source,
            "detected_audio_url": f"/snippet_audio?song={encoded_song}&start={start_preview:.2f}&duration=15",
            "innovation": {
                "latency_ms": latency_ms,
                "match_at_mmss": best["match_mmss"],
                "match_at_seconds": best["match_seconds"],
                "query_meta": query_meta,
                "match_meta": {
                    "tempo_bpm": best_record.tempo_bpm,
                    "key_label": best_record.key_label,
                    "energy": best_record.energy,
                },
                "tempo_diff": tempo_diff,
                "energy_diff": energy_diff,
                "lyrics_source": lyrics_source,
                "exact_file_match": bool(exact_song),
                "top_local_score": round(float(top_local_score), 6),
                "low_confidence_local": bool(low_conf_local),
                "fallback_attempted": bool(fallback_attempted),
                "used_external_fallback": used_external_fallback,
                "external_fallback": external_fallback or {},
            },
        }
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def wants_plain_text() -> bool:
    """Return plain text when client asks for it."""
    if request.args.get("plain") == "1":
        return True
    accepts = request.accept_mimetypes
    return accepts["text/plain"] > accepts["text/html"]


def current_page_data() -> dict:
    return {
        "message": "",
        "is_error": False,
        "song_count": len(song_index),
        "source_dir": str(current_source_dir),
        "recursive": bool(index_stats.get("recursive", True)),
        "index_stats": index_stats,
        "top_matches": [],
        "confidence": None,
        "confidence_label": "",
        "lyrics_preview": "",
        "lyrics_source": "",
        "innovation": {},
        "detected_song": "",
        "detected_audio_url": "",
        "song_options": song_names,
        "allowed_extensions": ", ".join(sorted(ALLOWED_AUDIO_EXTENSIONS)),
        "snippet_defaults": {"start": 30, "duration": 8, "top_k": 5},
    }


def make_response_payload(
    message: str,
    is_error: bool,
    status_code: int,
    top_matches: Optional[List[dict]] = None,
    confidence: Optional[float] = None,
    confidence_label: str = "",
    lyrics_preview: str = "",
    lyrics_source: str = "",
    innovation: Optional[dict] = None,
    detected_song: str = "",
):
    top_matches = top_matches or []
    innovation = innovation or {}

    if wants_plain_text():
        lines = [message]
        if top_matches:
            lines.append("")
            lines.append("Top matches:")
            for i, item in enumerate(top_matches, start=1):
                lines.append(
                    (
                        f"{i}. {item['song']} | score={item['score']:.4f} "
                        f"| global={item['global_score']:.4f} | segment={item['segment_score']:.4f} "
                        f"| dtw={item.get('dtw_score', 0.0):.4f}"
                    )
                )
        if confidence is not None:
            lines.append("")
            lines.append(f"Confidence: {confidence:.2f} ({confidence_label})")
        if lyrics_preview:
            lines.append("")
            source_txt = f" ({lyrics_source})" if lyrics_source else ""
            lines.append(f"Lyrics Preview{source_txt}:")
            lines.append(lyrics_preview)
        if innovation:
            lines.append("")
            lines.append("Innovation Metrics:")
            for key, value in innovation.items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines), status_code, {"Content-Type": "text/plain; charset=utf-8"}

    page_data = current_page_data()
    page_data["message"] = message
    page_data["is_error"] = is_error
    page_data["top_matches"] = top_matches
    page_data["confidence"] = confidence
    page_data["confidence_label"] = confidence_label
    page_data["lyrics_preview"] = lyrics_preview
    page_data["lyrics_source"] = lyrics_source
    page_data["innovation"] = innovation
    page_data["detected_song"] = detected_song
    if detected_song:
        encoded_song = quote(detected_song, safe="")
        page_data["detected_audio_url"] = f"/snippet_audio?song={encoded_song}&start=0&duration=15"
    return render_template("index.html", **page_data), status_code


@app.errorhandler(413)
def file_too_large(_error):
    return make_response_payload(
        message="Error: uploaded file is too large (max 32 MB).",
        is_error=True,
        status_code=413,
    )


@app.route("/snippet_audio", methods=["GET"])
def snippet_audio():
    """Serve an audio snippet from an indexed song as WAV for browser playback."""
    song_key = request.args.get("song", "").strip()
    if not song_key or song_key not in song_index:
        return Response("Song not found in index.", status=404, mimetype="text/plain")

    start = clamp_float(request.args.get("start", "0"), default=0.0, low=0.0, high=36000.0)
    duration = clamp_float(
        request.args.get("duration", "10"),
        default=10.0,
        low=1.0,
        high=MAX_SNIPPET_DURATION_SECONDS,
    )

    try:
        waveform = load_waveform(
            song_index[song_key].file_path,
            duration_seconds=duration,
            offset_seconds=start,
        )
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, waveform, SAMPLE_RATE, format="WAV")
        return Response(
            audio_buffer.getvalue(),
            mimetype="audio/wav",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:
        return Response(f"Audio preview failed: {exc}", status=400, mimetype="text/plain")


@app.route("/api/detect", methods=["POST"])
def api_detect():
    """JSON endpoint for live microphone detection from browser."""
    if not song_index:
        ready, error_message = ensure_index_ready()
        if not ready:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            "Index is empty. Build index first. "
                            f"Source='{current_source_dir}'. Detail: {error_message}"
                        ),
                        "song_count": len(song_index),
                        "index_stats": index_stats,
                    }
                ),
                400,
            )

    if "audio_file" not in request.files:
        return jsonify({"ok": False, "error": "Missing audio_file upload."}), 400

    top_k = clamp_top_k(request.form.get("top_k", "5"))
    capture_mode = request.form.get("capture_mode", "upload")
    uploaded = request.files["audio_file"]
    try:
        payload = detect_from_uploaded_stream(
            uploaded,
            top_k=top_k,
            capture_mode=capture_mode,
        )
        return jsonify(
            {
                "ok": True,
                "message": payload["message"],
                "best_song": payload["best_song"],
                "song_count": len(song_index),
                "top_matches": payload["top_matches"],
                "confidence": payload["confidence"],
                "confidence_label": payload["confidence_label"],
                "lyrics_preview": payload["lyrics_preview"],
                "lyrics_source": payload.get("lyrics_source", ""),
                "innovation": payload.get("innovation", {}),
                "detected_audio_url": payload["detected_audio_url"],
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("API detect failed: %s", exc)
        return jsonify({"ok": False, "error": f"Detection failed: {exc}"}), 500


@app.route("/api/lyrics", methods=["GET"])
def api_lyrics():
    """Fetch lyrics for an indexed song or an arbitrary query string."""
    song_key = request.args.get("song", "").strip()
    query = request.args.get("query", "").strip()
    lookup_text = song_key or query
    if not lookup_text:
        return jsonify({"ok": False, "error": "Missing song or query parameter."}), 400

    record = song_index.get(song_key) if song_key else None
    if record and record.lyrics:
        return jsonify(
            {
                "ok": True,
                "song": song_key,
                "source": "local",
                "lyrics": record.lyrics,
                "indexed_song": True,
            }
        )

    online_lyrics, source = fetch_online_lyrics(
        lookup_text,
        expected_duration_sec=(record.duration_sec if record else None),
    )
    if not online_lyrics:
        return jsonify(
            {
                "ok": True,
                "song": song_key or lookup_text,
                "source": "not_found",
                "lyrics": "Lyrics not found",
                "indexed_song": bool(record),
            }
        )

    return jsonify(
        {
            "ok": True,
            "song": song_key or lookup_text,
            "source": source,
            "lyrics": online_lyrics,
            "indexed_song": bool(record),
        }
    )


@app.route("/", methods=["GET", "POST"])
def index():
    """Single main route: indexing + upload detection + snippet detection."""
    global index_bootstrap_attempted

    if request.method == "GET":
        if not song_index:
            ensure_index_ready()
        return render_template("index.html", **current_page_data()), 200

    action = request.form.get("action", "detect_upload").strip().lower()

    if action == "reindex":
        source_input = request.form.get("source_dir", "").strip().strip('"').strip("'")
        recursive = request.form.get("recursive") == "on"
        target_dir = Path(source_input).expanduser().resolve() if source_input else current_source_dir
        index_bootstrap_attempted = True

        try:
            new_stats = rebuild_index_in_place(target_dir, recursive=recursive)

            if new_stats["indexed_songs"] == 0:
                return make_response_payload(
                    message="Index built, but no decodable supported audio files were found.",
                    is_error=True,
                    status_code=200,
                )

            return make_response_payload(
                message=(
                    "Index refreshed successfully. "
                    f"Indexed {new_stats['indexed_songs']} song(s), "
                    f"lyrics found for {new_stats['lyrics_found']} song(s)."
                ),
                is_error=False,
                status_code=200,
            )
        except Exception as exc:
            with index_lock:
                index_stats["last_error"] = str(exc)
            logger.exception("Reindex failed: %s", exc)
            return make_response_payload(
                message=f"Error while indexing source folder: {exc}",
                is_error=True,
                status_code=400,
            )

    if action not in {"detect", "detect_upload", "detect_snippet"}:
        return make_response_payload(
            message=f"Error: unsupported action '{action}'.",
            is_error=True,
            status_code=400,
        )

    if not song_index:
        ready, error_message = ensure_index_ready()
        if ready:
            pass
        else:
            return make_response_payload(
                message=(
                    "Error: index is empty. Build the index first from a source folder. "
                    f"Source='{current_source_dir}'. Detail: {error_message}"
                ),
                is_error=True,
                status_code=400,
            )

    top_k = clamp_top_k(request.form.get("top_k", "5"))

    if action == "detect_snippet":
        snippet_song = request.form.get("snippet_song", "").strip()
        snippet_start = clamp_float(request.form.get("snippet_start", "30"), 30.0, 0.0, 36000.0)
        snippet_duration = clamp_float(
            request.form.get("snippet_duration", "8"),
            8.0,
            2.0,
            MAX_SNIPPET_DURATION_SECONDS,
        )

        if not snippet_song or snippet_song not in song_index:
            return make_response_payload(
                message="Error: choose a valid indexed song for snippet detection.",
                is_error=True,
                status_code=400,
            )

        try:
            results = detect_top_matches_from_indexed_snippet(
                source_song_key=snippet_song,
                start_seconds=snippet_start,
                snippet_duration=snippet_duration,
                top_k=top_k,
            )
            if not results:
                return make_response_payload(
                    message="No match found for snippet query.",
                    is_error=True,
                    status_code=404,
                )

            best = results[0]
            confidence, confidence_label = estimate_confidence(results)
            lyrics_preview, lyrics_source = get_best_song_lyrics(best["song"])
            best_record = song_index[best["song"]]
            innovation = {
                "match_at_mmss": best.get("match_mmss", "00:00"),
                "matched_song_tempo": best_record.tempo_bpm,
                "matched_song_key": best_record.key_label,
                "lyrics_source": lyrics_source,
            }
            return make_response_payload(
                message=(
                    f"Snippet query from '{snippet_song}' "
                    f"(start={snippet_start:.1f}s, dur={snippet_duration:.1f}s) -> "
                    f"detected: {best['song']} (score: {best['score']:.4f})"
                ),
                is_error=False,
                status_code=200,
                top_matches=results,
                confidence=confidence,
                confidence_label=confidence_label,
                lyrics_preview=lyrics_preview,
                lyrics_source=lyrics_source,
                innovation=innovation,
                detected_song=best["song"],
            )
        except Exception as exc:
            logger.exception("Snippet detection failed: %s", exc)
            return make_response_payload(
                message=f"Error while processing snippet query: {exc}",
                is_error=True,
                status_code=500,
            )

    # Upload detection path (also used by mic recording fallback forms).
    if "audio_file" not in request.files:
        return make_response_payload(
            message="Error: no file part in request.",
            is_error=True,
            status_code=400,
        )

    uploaded = request.files["audio_file"]
    try:
        payload = detect_from_uploaded_stream(uploaded, top_k=top_k)
        return make_response_payload(
            message=payload["message"],
            is_error=False,
            status_code=200,
            top_matches=payload["top_matches"],
            confidence=payload["confidence"],
            confidence_label=payload["confidence_label"],
            lyrics_preview=payload["lyrics_preview"],
            lyrics_source=payload.get("lyrics_source", ""),
            innovation=payload.get("innovation", {}),
            detected_song=payload["best_song"],
        )
    except ValueError as exc:
        err_text = str(exc).strip() or "Couldn't detect the song."
        if err_text.lower().startswith("couldn't detect the song"):
            message = err_text
        else:
            message = f"Error while processing uploaded audio: {err_text}"
        return make_response_payload(
            message=message,
            is_error=True,
            status_code=400,
        )
    except Exception as exc:
        logger.exception("Upload detection failed: %s", exc)
        return make_response_payload(
            message=f"Error while processing uploaded audio: {exc}",
            is_error=True,
            status_code=500,
        )


if __name__ == "__main__":
    ready, error_message = ensure_index_ready()
    if ready:
        logger.info(
            "Startup index ready | source=%s indexed=%d scanned=%d failed=%d",
            current_source_dir,
            index_stats.get("indexed_songs", 0),
            index_stats.get("scanned_files", 0),
            index_stats.get("failed_files", 0),
        )
    else:
        logger.warning(
            "Startup index not ready | source=%s detail=%s",
            current_source_dir,
            error_message,
        )

    bind_host = get_primary_bind_host()
    try:
        app_port = int(os.environ.get("APP_PORT", "5001").strip())
    except Exception:
        app_port = 5001

    https_flag = os.environ.get("APP_USE_HTTPS", "1").strip().lower()
    enable_https = https_flag not in {"0", "false", "no", "off"}

    if enable_https and is_https_runtime_available():
        logger.info("Open app on this single URL: https://%s:%d", bind_host, app_port)
        app.run(host=bind_host, port=app_port, debug=False, ssl_context="adhoc")
    else:
        if enable_https:
            logger.warning(
                "APP_USE_HTTPS is enabled but dependency 'cryptography' is missing. "
                "Falling back to HTTP (microphone may be blocked by browser security)."
            )
        logger.info("Open app on this single URL: http://%s:%d", bind_host, app_port)
        app.run(host=bind_host, port=app_port, debug=False)
