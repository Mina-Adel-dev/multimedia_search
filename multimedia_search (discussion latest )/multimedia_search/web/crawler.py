"""Small, polite web crawler for discovering pages to index.

The crawler only discovers HTML page URLs. It does not replace the existing
web ingester; callers should pass discovered URLs to services.index_web_urls().
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from multimedia_search.web.fetcher import fetch
from multimedia_search.web.url_utils import normalize_url


_SKIP_EXTENSIONS = {
    ".7z",
    ".avi",
    ".bmp",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".exe",
    ".flac",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogg",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".svg",
    ".tar",
    ".wav",
    ".webm",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}


class _LinkExtractor(HTMLParser):
    """Extract normal hyperlink targets from one HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return

        for name, value in attrs:
            if name.lower() == "href" and value:
                self.links.append(str(value).strip())


def _canonical_for_crawl(url: str) -> str:
    """Return a normalized crawl URL without fragments."""
    normalized = normalize_url(url)
    if not normalized:
        return ""

    parsed = urlparse(normalized)
    parsed = parsed._replace(fragment="")
    return urlunparse(parsed)


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _host_key(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower()


def _looks_like_html_page(url: str) -> bool:
    path = urlparse(url).path.lower()
    return not any(path.endswith(extension) for extension in _SKIP_EXTENSIONS)


def extract_links(html: str, base_url: str) -> List[str]:
    """Extract normalized absolute links from HTML."""
    parser = _LinkExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        return []

    links: List[str] = []
    seen: Set[str] = set()

    for raw_link in parser.links:
        if not raw_link or raw_link.startswith(("mailto:", "tel:", "javascript:")):
            continue

        absolute = urljoin(base_url, raw_link)
        normalized = _canonical_for_crawl(absolute)

        if not normalized or not _is_http_url(normalized):
            continue

        if not _looks_like_html_page(normalized):
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        links.append(normalized)

    return links


@dataclass(frozen=True)
class CrawlResult:
    """Result of one crawl operation."""

    urls: List[str]
    visited_count: int
    failed_count: int
    skipped_count: int
    errors: List[str]


class _RobotsCache:
    """Small robots.txt cache used by the crawler."""

    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._cache: Dict[str, Optional[RobotFileParser]] = {}

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"

        if root not in self._cache:
            robots = RobotFileParser()
            robots.set_url(f"{root}/robots.txt")
            try:
                robots.read()
                self._cache[root] = robots
            except Exception:
                self._cache[root] = None

        robots = self._cache[root]
        if robots is None:
            return True

        try:
            return robots.can_fetch(self.user_agent, url)
        except Exception:
            return True


def crawl_urls(
    seed_urls: Iterable[str],
    max_pages: int = 25,
    max_depth: int = 1,
    same_domain: bool = True,
    respect_robots: bool = True,
    user_agent: str = "MultimediaSearchBot/0.1",
    fetcher: Callable[[str], Optional[str]] = fetch,
) -> CrawlResult:
    """Discover web page URLs starting from seed URLs."""
    safe_max_pages = max(1, min(int(max_pages), 500))
    safe_max_depth = max(0, min(int(max_depth), 5))

    normalized_seeds: List[str] = []
    seed_hosts: Dict[str, str] = {}

    for seed in seed_urls:
        normalized = _canonical_for_crawl(str(seed).strip())
        if not normalized or not _is_http_url(normalized):
            continue
        if not _looks_like_html_page(normalized):
            continue
        if normalized in normalized_seeds:
            continue
        normalized_seeds.append(normalized)
        seed_hosts[normalized] = _host_key(normalized)

    queue: deque[Tuple[str, int, str]] = deque(
        (seed, 0, seed_hosts[seed]) for seed in normalized_seeds
    )
    queued: Set[str] = set(normalized_seeds)
    visited: Set[str] = set()
    discovered: List[str] = []
    errors: List[str] = []
    failed_count = 0
    skipped_count = 0
    robots_cache = _RobotsCache(user_agent)

    while queue and len(discovered) < safe_max_pages:
        url, depth, seed_host = queue.popleft()

        if url in visited:
            continue

        if same_domain and _host_key(url) != seed_host:
            skipped_count += 1
            continue

        if respect_robots and not robots_cache.can_fetch(url):
            skipped_count += 1
            continue

        visited.add(url)
        discovered.append(url)

        if depth >= safe_max_depth or len(discovered) >= safe_max_pages:
            continue

        html = fetcher(url)
        if html is None:
            failed_count += 1
            errors.append(f"Failed to fetch {url}")
            continue

        for link in extract_links(html, url):
            if len(discovered) + len(queue) >= safe_max_pages * 3:
                break

            if link in visited or link in queued:
                continue

            if same_domain and _host_key(link) != seed_host:
                skipped_count += 1
                continue

            queued.add(link)
            queue.append((link, depth + 1, seed_host))

    return CrawlResult(
        urls=discovered[:safe_max_pages],
        visited_count=len(visited),
        failed_count=failed_count,
        skipped_count=skipped_count,
        errors=errors[:20],
    )