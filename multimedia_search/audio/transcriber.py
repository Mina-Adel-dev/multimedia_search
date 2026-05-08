"""Audio transcription and transcript analysis.

Runtime behavior:
- If OPENAI_API_KEY exists, try OpenAI transcription first.
- If no API key exists, use local faster-whisper.
- If transcript analysis API is unavailable, use a safe local fallback summary.

Tests should patch transcribe_audio_file() and analyze_audio_transcript()
so no real API/local model is used during unit tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from multimedia_search import config


def _has_openai_api_key() -> bool:
    """Return True when an OpenAI API key is available."""
    return bool(os.getenv("OPENAI_API_KEY"))


def _get_openai_client():
    """Create an OpenAI client only when needed."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The openai package is not installed. Run: py -3.12 -m pip install openai"
        ) from exc

    return OpenAI(api_key=api_key)


def _response_text(response: Any) -> str:
    """Extract text from common OpenAI SDK response shapes."""
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text.strip()

    if isinstance(response, dict):
        value = response.get("text")
        if isinstance(value, str):
            return value.strip()

    return str(response).strip()


def _transcribe_with_openai(audio_path: Path) -> str:
    """Transcribe an audio file using OpenAI audio transcription."""
    client = _get_openai_client()

    with audio_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=config.AUDIO_TRANSCRIPTION_MODEL,
            file=audio_file,
        )

    transcript = _response_text(response)

    if not transcript:
        raise RuntimeError("OpenAI audio transcription returned empty text.")

    return transcript


def _transcribe_with_faster_whisper(audio_path: Path) -> str:
    """Transcribe an audio file locally using faster-whisper."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Run: py -3.12 -m pip install faster-whisper"
        ) from exc

    model_size = os.getenv("LOCAL_WHISPER_MODEL", "base")
    device = os.getenv("LOCAL_WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("LOCAL_WHISPER_COMPUTE_TYPE", "int8")

    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
    )

    segments, _info = model.transcribe(str(audio_path))
    transcript_parts: List[str] = []

    for segment in segments:
        text = str(getattr(segment, "text", "") or "").strip()
        if text:
            transcript_parts.append(text)

    transcript = " ".join(transcript_parts).strip()

    if not transcript:
        raise RuntimeError("Local faster-whisper transcription returned empty text.")

    return transcript


def transcribe_audio_file(file_path: Path) -> str:
    """Transcribe an audio file to text.

    Uses OpenAI API when OPENAI_API_KEY exists.
    Falls back to local faster-whisper when no key exists.
    """
    audio_path = Path(file_path)

    if not audio_path.exists() or not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if _has_openai_api_key():
        try:
            return _transcribe_with_openai(audio_path)
        except Exception as openai_error:
            try:
                return _transcribe_with_faster_whisper(audio_path)
            except Exception as local_error:
                raise RuntimeError(
                    "Audio transcription failed with OpenAI API and local faster-whisper. "
                    f"OpenAI error: {openai_error}. Local error: {local_error}"
                ) from local_error

    return _transcribe_with_faster_whisper(audio_path)


def _default_analysis(transcript: str) -> Dict[str, object]:
    """Local fallback analysis when no API key is available.

    This is not as strong as an LLM summary, but it avoids showing
    a raw transcript dump as the summary.
    """
    cleaned = " ".join(str(transcript or "").split())

    if not cleaned:
        return {
            "summary": "",
            "conclusion": "",
            "action_items": [],
            "keywords": [],
            "mentioned_people": [],
            "mentioned_places": [],
            "mentioned_organizations": [],
        }

    sentence_parts = []
    current = []

    for char in cleaned:
        current.append(char)
        if char in ".!?":
            sentence = "".join(current).strip()
            if sentence:
                sentence_parts.append(sentence)
            current = []

    if current:
        leftover = "".join(current).strip()
        if leftover:
            sentence_parts.append(leftover)

    meaningful_sentences = [
        sentence
        for sentence in sentence_parts
        if len(sentence.split()) >= 5
    ]

    if meaningful_sentences:
        content_source = " ".join(meaningful_sentences[:2])
    else:
        content_source = cleaned

    if len(content_source) > 260:
        content_source = content_source[:260].rsplit(" ", 1)[0] + "..."

    words = []
    for word in cleaned.replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ").split():
        normalized = word.strip("'\"()[]{}").lower()
        if len(normalized) < 4:
            continue
        if normalized in {
            "this", "that", "with", "from", "your", "there", "their",
            "they", "them", "then", "than", "have", "what", "when",
            "where", "will", "just", "like", "yeah",
        }:
            continue
        if normalized not in words:
            words.append(normalized)
        if len(words) >= 8:
            break

    keyword_text = ", ".join(words[:5]) if words else "the audio transcript"

    return {
        "summary": f"The audio content is mainly about: {keyword_text}.",
        "conclusion": "The transcript was indexed successfully. Use search results and the audio player to review the full context.",
        "action_items": [],
        "keywords": words,
        "mentioned_people": [],
        "mentioned_places": [],
        "mentioned_organizations": [],
    }

def _safe_json_loads(text: str) -> Dict[str, object]:
    """Parse JSON object from model output safely."""
    raw = str(text or "").strip()

    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    start = raw.find("{")
    end = raw.rfind("}")

    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]

    data = json.loads(raw)

    if not isinstance(data, dict):
        raise ValueError("Analysis output is not a JSON object.")

    return data


def analyze_audio_transcript(transcript: str) -> Dict[str, object]:
    """Generate summary, conclusion, action items, and mentioned entities.

    If no OpenAI API key exists, use a simple local fallback.
    """
    cleaned = str(transcript or "").strip()
    if not cleaned:
        return _default_analysis(cleaned)

    if not config.AUDIO_ANALYSIS_ENABLED:
        return _default_analysis(cleaned)

    if not _has_openai_api_key():
        return _default_analysis(cleaned)

    try:
        client = _get_openai_client()

        prompt = f"""
Analyze this audio transcript for a multimedia search engine.

Return ONLY a JSON object with these keys:
summary: string, 1-3 sentences
conclusion: string, main takeaway
action_items: array of strings
keywords: array of strings
mentioned_people: array of strings
mentioned_places: array of strings
mentioned_organizations: array of strings

Do not identify the speaker by voice.
Only list people who are mentioned in the transcript text.

Transcript:
{cleaned}
""".strip()

        response = client.responses.create(
            model=config.AUDIO_ANALYSIS_MODEL,
            input=prompt,
        )

        output_text = getattr(response, "output_text", "")
        data = _safe_json_loads(output_text)
    except Exception:
        return _default_analysis(cleaned)

    fallback = _default_analysis(cleaned)

    return {
        "summary": str(data.get("summary") or fallback["summary"]),
        "conclusion": str(data.get("conclusion") or fallback["conclusion"]),
        "action_items": list(data.get("action_items") or []),
        "keywords": list(data.get("keywords") or fallback["keywords"]),
        "mentioned_people": list(data.get("mentioned_people") or []),
        "mentioned_places": list(data.get("mentioned_places") or []),
        "mentioned_organizations": list(data.get("mentioned_organizations") or []),
    }