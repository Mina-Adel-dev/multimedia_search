"""Fetch HTML from a URL, handling compression and encoding."""

import gzip
import urllib.request
import urllib.error
import socket
import zlib
from email.message import EmailMessage
from typing import Optional


def _get_encoding_from_headers(headers) -> str:
    """Extract encoding from Content-Type header, default to utf-8."""
    content_type = headers.get('Content-Type', '')
    msg = EmailMessage()
    msg['content-type'] = content_type
    charset = msg.get_content_charset()
    return charset or 'utf-8'


def _decompress_content(content: bytes, content_encoding: str) -> bytes:
    """Decompress content if gzip or deflate encoded."""
    if content_encoding == 'gzip':
        return gzip.decompress(content)
    elif content_encoding == 'deflate':
        return zlib.decompress(content)
    return content


def fetch(url: str, timeout: int = 10) -> Optional[str]:
    """
    Fetch HTML content from a URL.
    Handles gzip/deflate compression and encoding detection.
    Returns None if fetch fails.
    """
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; MultimediaSearch/1.0)'
        })
        with urllib.request.urlopen(req, timeout=timeout) as response:
            # Read raw bytes
            raw_data = response.read()
            
            # Decompress if needed
            content_encoding = response.headers.get('Content-Encoding', '')
            raw_data = _decompress_content(raw_data, content_encoding)
            
            # Determine encoding
            encoding = _get_encoding_from_headers(response.headers)
            
            # Decode, replacing errors
            html = raw_data.decode(encoding, errors='replace')
            return html
            
    except (urllib.error.URLError, socket.timeout, ValueError, 
            gzip.BadGzipFile, zlib.error) as e:
        print(f"Error fetching {url}: {e}")
        return None