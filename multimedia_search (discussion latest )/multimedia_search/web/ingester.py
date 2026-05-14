"""Ingest web pages as documents."""

from typing import List

from multimedia_search.core.document import Document
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.web.extractor import extract
from multimedia_search.web.fetcher import fetch
from multimedia_search.web.url_utils import normalize_url


def ingest_urls(urls: List[str], preprocessor: Preprocessor) -> List[Document]:
    """
    Fetch each URL, extract text, and return a list of Document objects.

    URLs are normalized before fetch/storage to reduce duplicates.
    Documents have path set to the normalized URL, file_type 'html',
    raw_text set to extracted text, and tokens preprocessed.
    """
    docs = []
    seen_urls = set()

    for raw_url in urls:
        normalized_url = normalize_url(raw_url)

        if not normalized_url:
            continue

        if normalized_url in seen_urls:
            print(f"Skipping duplicate input URL: {normalized_url}")
            continue

        seen_urls.add(normalized_url)

        print(f"Fetching {normalized_url}...")
        html = fetch(normalized_url)
        if html is None:
            continue

        extracted = extract(html)
        full_text = f"{extracted['title']} {extracted['text']}".strip()
        tokens = preprocessor.process(full_text)

        doc = Document(
            doc_id=-1,  # placeholder, assigned later
            path=normalized_url,
            file_type="html",
            raw_text=full_text,
            tokens=tokens,
        )
        docs.append(doc)

    return docs
