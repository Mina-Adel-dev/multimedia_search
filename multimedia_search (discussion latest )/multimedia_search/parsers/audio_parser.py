"""Audio parser that turns voice notes into searchable text."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import multimedia_search.audio.transcriber as transcriber
from multimedia_search import config
from multimedia_search.audio.metadata import AUDIO_EXTENSIONS
from multimedia_search.parsers.base import BaseParser


class AudioParser(BaseParser):
    """Parse audio/video-with-audio files by transcribing speech to text."""

    def parse(self, file_path: Path) -> str:
        """Return searchable raw text for an audio file."""
        audio_path = Path(file_path)

        if audio_path.suffix.lower().lstrip(".") not in AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio extension: {audio_path.suffix}")

        payload = self._load_or_create_payload(audio_path)
        return self._build_searchable_text(audio_path, payload)

    def _cache_path(self, file_path: Path) -> Path:
        """Return cache path that is not itself indexed by FileScanner."""
        return Path(str(file_path) + ".ms_audio_cache")

    def _load_or_create_payload(self, audio_path: Path) -> Dict[str, object]:
        """Load transcript cache if fresh, otherwise call the API."""
        cache_path = self._cache_path(audio_path)

        if config.AUDIO_CACHE_ENABLED:
            cached = self._load_cache(audio_path, cache_path)
            if cached is not None:
                return cached

        transcript = transcriber.transcribe_audio_file(audio_path)
        analysis = transcriber.analyze_audio_transcript(transcript)

        payload: Dict[str, object] = {
            "source_path": str(audio_path),
            "source_mtime": audio_path.stat().st_mtime,
            "transcript": transcript,
            "analysis": analysis,
        }

        if config.AUDIO_CACHE_ENABLED:
            self._write_cache(cache_path, payload)

        return payload

    def _load_cache(self, audio_path: Path, cache_path: Path):
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
        current_mtime = audio_path.stat().st_mtime

        if cached_mtime < current_mtime:
            return None

        if not str(data.get("transcript", "")).strip():
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
            # Cache failure should not block indexing.
            pass

    def _folder_terms(self, audio_path: Path) -> List[str]:
        """Use nearby folders as searchable metadata."""
        return [
            part.replace("_", " ").replace("-", " ")
            for part in audio_path.parent.parts[-3:]
            if part
        ]

    def _list_to_text(self, value) -> str:
        """Convert list-like analysis fields into text."""
        if isinstance(value, list):
            return ", ".join(str(item) for item in value if str(item).strip())
        return str(value or "").strip()

    def _build_searchable_text(self, audio_path: Path, payload: Dict[str, object]) -> str:
        """Build raw_text with stable markers for UI extraction."""
        transcript = str(payload.get("transcript", "") or "").strip()
        analysis = payload.get("analysis", {}) or {}

        if not isinstance(analysis, dict):
            analysis = {}

        filename_text = audio_path.stem.replace("_", " ").replace("-", " ")
        folder_text = " ".join(self._folder_terms(audio_path))
        extension = audio_path.suffix.lower().lstrip(".")

        summary = str(analysis.get("summary", "") or "").strip()
        conclusion = str(analysis.get("conclusion", "") or "").strip()
        action_items = self._list_to_text(analysis.get("action_items", []))
        keywords = self._list_to_text(analysis.get("keywords", []))
        mentioned_people = self._list_to_text(analysis.get("mentioned_people", []))
        mentioned_places = self._list_to_text(analysis.get("mentioned_places", []))
        mentioned_orgs = self._list_to_text(analysis.get("mentioned_organizations", []))

        return f"""
Audio file: {audio_path.name}
Audio filename terms: {filename_text}
Audio folder terms: {folder_text}
Audio extension: {extension}
Audio metadata terms: audio voice note speech recording transcript summary conclusion keywords people places organizations

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