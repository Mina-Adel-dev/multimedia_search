"""GDELT news connector.

Fetches news article metadata by topic using GDELT DOC API.
No paywall bypassing and no article scraping.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Dict, List
from urllib.request import Request, urlopen

from multimedia_search.sources.source_document import SourceDocument


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "MultimediaSearchEngineStudentProject/0.1"


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def fetch_gdelt_news_documents(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch topic-based news article metadata from GDELT."""
    clean_query = _safe_text(query)

    if not clean_query:
        return []

    safe_limit = max(1, min(int(limit), 100))

    params = {
        "query": clean_query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(safe_limit),
        "sort": "HybridRel",
    }

    url = f"{GDELT_DOC_API_URL}?{urllib.parse.urlencode(params)}"

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))

    articles = data.get("articles", [])
    documents: List[Dict[str, Any]] = []

    if not isinstance(articles, list):
        return []

    for article in articles:
        if not isinstance(article, dict):
            continue

        title = _safe_text(article.get("title"))
        article_url = _safe_text(article.get("url"))
        source_name = _safe_text(
            article.get("domain")
            or article.get("sourceCommonName")
            or article.get("source")
            or "GDELT"
        )
        published_at = _safe_text(article.get("seendate") or article.get("date"))
        language = _safe_text(article.get("language"))
        country = _safe_text(article.get("sourcecountry"))

        if not title and not article_url:
            continue

        raw_text = f"""
Source: GDELT news article
Media type: news_article
Query topic: {clean_query}
Article title: {title}
News source: {source_name}
Published/seen date: {published_at}
Language: {language}
Source country: {country}
Article URL: {article_url}
News metadata terms: news article headline report story current events topic media press
""".strip()

        document = SourceDocument(
            path=article_url or f"gdelt://news/{clean_query}/{len(documents)}",
            file_type="news_article",
            raw_text=raw_text,
            source_name=source_name,
            media_type="news_article",
            title=title,
            url=article_url,
            published_at=published_at,
            metadata={
                "source_name": source_name,
                "media_type": "news_article",
                "title": title,
                "url": article_url,
                "published_at": published_at,
                "query": clean_query,
                "language": language,
                "source_country": country,
                "provider": "gdelt",
            },
        )

        documents.append(document.to_dict())

    return documents