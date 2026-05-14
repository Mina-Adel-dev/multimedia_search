"""Wikipedia data importer for filling the local search index."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "MultimediaSearchEngineStudentProject/0.1"


def _get_json(params: Dict[str, Any]) -> Dict[str, Any]:
    """Call the Wikipedia API and return JSON."""
    url = f"{WIKIPEDIA_API_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def search_wikipedia_pages(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search Wikipedia pages and return page records."""
    safe_limit = max(1, min(int(limit), 50))

    data = _get_json(
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": safe_limit,
            "format": "json",
        }
    )

    return data.get("query", {}).get("search", [])


def get_wikipedia_extract(page_id: int) -> str:
    """Fetch plain text extract for one Wikipedia page."""
    data = _get_json(
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "pageids": int(page_id),
            "format": "json",
        }
    )

    pages = data.get("query", {}).get("pages", {})
    page = pages.get(str(page_id), {})
    return str(page.get("extract", "") or "")


def fetch_wikipedia_documents(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """Return Wikipedia pages as source documents."""
    records = search_wikipedia_pages(query, limit=limit)
    documents: List[Dict[str, str]] = []

    for record in records:
        page_id = int(record.get("pageid", 0) or 0)
        title = str(record.get("title", "") or "").strip()

        if not page_id or not title:
            continue

        try:
            extract = get_wikipedia_extract(page_id)
        except Exception:
            extract = ""

        snippet = str(record.get("snippet", "") or "")
        raw_text = f"{title}\n\n{snippet}\n\n{extract}".strip()

        if not raw_text:
            continue

        documents.append(
            {
                "path": f"wikipedia://{page_id}",
                "file_type": "txt",
                "raw_text": raw_text,
                "source_url": f"https://en.wikipedia.org/?curid={page_id}",
                "title": title,
            }
        )

    return documents