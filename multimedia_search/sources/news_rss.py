"""RSS/Atom news connector.

Imports article metadata and summaries from public feeds.
Does not bypass paywalls or scrape protected pages.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List
from urllib.request import Request, urlopen

from multimedia_search.sources.source_document import SourceDocument


USER_AGENT = "MultimediaSearchEngineStudentProject/0.1"
_TAG_RE = re.compile(r"<[^>]+>")


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _strip_html(value: str) -> str:
    return _TAG_RE.sub(" ", _safe_text(value)).replace("  ", " ").strip()


def _local_name(tag: str) -> str:
    return str(tag).split("}")[-1].lower()


def _first_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}

    for child in list(node):
        if _local_name(child.tag) in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return text

    return ""


def _rss_link(item: ET.Element) -> str:
    for child in list(item):
        if _local_name(child.tag) != "link":
            continue

        href = child.attrib.get("href", "").strip()
        if href:
            return href

        text = "".join(child.itertext()).strip()
        if text:
            return text

    return ""


def _source_from_feed(root: ET.Element, feed_url: str) -> str:
    channel = next((node for node in root.iter() if _local_name(node.tag) == "channel"), None)

    if channel is not None:
        title = _first_text(channel, "title")
        if title:
            return title

    title = _first_text(root, "title")
    return title or feed_url


def _entry_nodes(root: ET.Element) -> List[ET.Element]:
    items = [node for node in root.iter() if _local_name(node.tag) == "item"]
    if items:
        return items

    return [node for node in root.iter() if _local_name(node.tag) == "entry"]


def _fallback_news_path(feed_url: str, title: str, published_at: str) -> str:
    basis = f"{feed_url}|{title}|{published_at}".encode("utf-8", errors="ignore")
    digest = hashlib.sha256(basis).hexdigest()[:16]
    return f"news://rss/{digest}"


def parse_news_rss(xml_text: str, feed_url: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 100))
    root = ET.fromstring(xml_text)
    source_name = _source_from_feed(root, feed_url)
    documents: List[Dict[str, Any]] = []

    for item in _entry_nodes(root):
        title = _first_text(item, "title")
        url = _rss_link(item)
        summary = _strip_html(_first_text(item, "description", "summary", "content"))
        published_at = _first_text(item, "pubDate", "published", "updated", "date")

        if not title and not summary:
            continue

        path = url or _fallback_news_path(feed_url, title, published_at)

        raw_text = f"""
Source: RSS news article
Media type: news_article
News source: {source_name}
Article title: {title}
Article summary: {summary}
Published date: {published_at}
Article URL: {url}
Feed URL: {feed_url}
News metadata terms: news article rss feed external source current events report story headline publisher
""".strip()

        document = SourceDocument(
            path=path,
            file_type="news_article",
            raw_text=raw_text,
            source_name=source_name,
            media_type="news_article",
            title=title,
            url=url,
            published_at=published_at,
            metadata={
                "source_name": source_name,
                "summary": summary,
                "published_at": published_at,
                "url": url,
                "feed_url": feed_url,
            },
        )

        documents.append(document.to_dict())

        if len(documents) >= safe_limit:
            break

    return documents


def fetch_news_rss_documents(feed_url: str, limit: int = 20) -> List[Dict[str, Any]]:
    clean_url = _safe_text(feed_url)
    if not clean_url:
        return []

    request = Request(
        clean_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )

    with urlopen(request, timeout=20) as response:
        xml_text = response.read().decode("utf-8", errors="replace")

    return parse_news_rss(xml_text, feed_url=clean_url, limit=limit)