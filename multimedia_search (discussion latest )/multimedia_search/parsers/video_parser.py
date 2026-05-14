"""Video parser that turns videos into searchable metadata and optional transcript text."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import multimedia_search.audio.transcriber as transcriber
from multimedia_search import config
from multimedia_search.parsers.base import BaseParser
from multimedia_search.video.metadata import VIDEO_EXTENSIONS


class VideoParser(BaseParser):
    """Parse video files safely.

    Default behavior:
    - index filename, folder names, extension, and metadata quickly
    - use a sidecar transcript if available
    - only transcribe the video if VIDEO_TRANSCRIPTION_ENABLED=True
    """

    def parse(self, file_path: Path) -> str:
        """Return searchable raw text for a video file."""
        video_path = Path(file_path)
        extension = video_path.suffix.lower().lstrip(".")

        if extension not in VIDEO_EXTENSIONS:
            raise ValueError(f"Unsupported video extension: {video_path.suffix}")

        payload = self._load_or_create_payload(video_path)
        return self._build_searchable_text(video_path, payload)

    def _cache_path(self, file_path: Path) -> Path:
        """Return cache path that is not indexed by FileScanner."""
        return Path(str(file_path) + ".ms_video_cache")

    def _load_or_create_payload(self, video_path: Path) -> Dict[str, object]:
        """Load transcript cache if fresh, otherwise build a safe payload."""
        cache_path = self._cache_path(video_path)

        if getattr(config, "VIDEO_CACHE_ENABLED", True):
            cached = self._load_cache(video_path, cache_path)
            if cached is not None:
                return cached

        transcript = self._read_sidecar_transcript(video_path)
        analysis = self._empty_analysis()

        if not transcript and getattr(config, "VIDEO_TRANSCRIPTION_ENABLED", False):
            try:
                transcript = transcriber.transcribe_audio_file(video_path)
                analysis = transcriber.analyze_audio_transcript(transcript)
            except Exception as exc:
                transcript = ""
                analysis = self._empty_analysis()
                analysis["summary"] = f"Video transcription failed: {exc}"

        elif transcript:
            try:
                analysis = transcriber.analyze_audio_transcript(transcript)
            except Exception:
                analysis = self._empty_analysis()
                analysis["summary"] = "Video transcript was loaded from a sidecar file."

        payload: Dict[str, object] = {
            "source_path": str(video_path),
            "source_mtime": video_path.stat().st_mtime,
            "transcript": transcript,
            "analysis": analysis,
        }

        if getattr(config, "VIDEO_CACHE_ENABLED", True):
            self._write_cache(cache_path, payload)

        return payload

    def _load_cache(self, video_path: Path, cache_path: Path):
        """Load cache only if it belongs to the current file version."""
        if not cache_path.exists():
            return None

        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(data, dict):
            return None

        cached_mtime = float(data.get("source_mtime", -1))
        current_mtime = video_path.stat().st_mtime

        if cached_mtime < current_mtime:
            return None

        return data

    def _write_cache(self, cache_path: Path, payload: Dict[str, object]) -> None:
        """Write transcript cache safely."""
        try:
            cache_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _read_sidecar_transcript(self, video_path: Path) -> str:
        """Read a nearby transcript file if one exists."""
        candidates = [
            Path(str(video_path) + ".txt"),
            Path(str(video_path) + ".md"),
            Path(str(video_path) + ".srt"),
            Path(str(video_path) + ".vtt"),
            video_path.with_suffix(".txt"),
            video_path.with_suffix(".md"),
            video_path.with_suffix(".srt"),
            video_path.with_suffix(".vtt"),
        ]

        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                continue

            try:
                return candidate.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                continue

        return ""

    def _empty_analysis(self) -> Dict[str, object]:
        """Return empty audio-style analysis fields."""
        return {
            "summary": "",
            "conclusion": "",
            "action_items": [],
            "keywords": [],
            "mentioned_people": [],
            "mentioned_places": [],
            "mentioned_organizations": [],
        }

    def _folder_terms(self, video_path: Path) -> List[str]:
        """Use nearby folders as searchable metadata."""
        return [
            part.replace("_", " ").replace("-", " ")
            for part in video_path.parent.parts[-3:]
            if part
        ]

    def _list_to_text(self, value) -> str:
        """Convert list-like analysis fields into text."""
        if isinstance(value, list):
            return ", ".join(str(item) for item in value if str(item).strip())
        return str(value or "").strip()

    def _build_searchable_text(self, video_path: Path, payload: Dict[str, object]) -> str:
        """Build searchable text with audio-style markers for UI reuse."""
        transcript = str(payload.get("transcript", "") or "").strip()
        analysis = payload.get("analysis", {}) or {}

        if not isinstance(analysis, dict):
            analysis = self._empty_analysis()

        filename_text = video_path.stem.replace("_", " ").replace("-", " ")
        folder_text = " ".join(self._folder_terms(video_path))
        extension = video_path.suffix.lower().lstrip(".")

        summary = str(analysis.get("summary", "") or "").strip()
        conclusion = str(analysis.get("conclusion", "") or "").strip()
        action_items = self._list_to_text(analysis.get("action_items", []))
        keywords = self._list_to_text(analysis.get("keywords", []))
        mentioned_people = self._list_to_text(analysis.get("mentioned_people", []))
        mentioned_places = self._list_to_text(analysis.get("mentioned_places", []))
        mentioned_orgs = self._list_to_text(analysis.get("mentioned_organizations", []))

        if not transcript:
            transcript = "No transcript available yet. Video indexed using filename, folder, and metadata."

        return f"""
Video file: {video_path.name}
Video filename terms: {filename_text}
Video folder terms: {folder_text}
Video extension: {extension}
Video metadata terms: video clip movie recording mp4 webm mov mkv avi visual media local video transcript

AUDIO_TRANSCRIPT:
{transcript}

AUDIO_SUMMARY:
{summary}

AUDIO_CONCLUSION:
{conclusion}

AUDIO_ACTION_ITEMS:
{action_items}

AUDIO_KEYWORDS:
{keywords}

AUDIO_MENTIONED_PEOPLE:
{mentioned_people}

AUDIO_MENTIONED_PLACES:
{mentioned_places}

AUDIO_MENTIONED_ORGANIZATIONS:
{mentioned_orgs}
""".strip()