"""URL normalization utilities."""

from urllib.parse import urlparse, urlunparse

def normalize_url(url: str) -> str:
    """
    Normalize a URL to a canonical form.

    Rules applied:
    - Lowercase scheme and netloc.
    - Remove default ports (80 for http, 443 for https).
    - Remove fragment (everything after #).
    - Remove trailing slash from path unless path is empty (root becomes "").
    """
    if not url:
        return url

    # Parse
    parsed = urlparse(url)

    # Lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Normalize path: remove trailing slash unless it's the root path "/"
    path = parsed.path
    if path == "/":
        path = ""
    elif path.endswith("/"):
        path = path.rstrip("/")

    # Rebuild without fragment
    normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
    return normalized