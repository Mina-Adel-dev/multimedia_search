"""Command-line interface for indexing and search."""

import argparse
import sys
from os.path import normcase
from pathlib import Path

import multimedia_search.config as config
from multimedia_search.core.analytics import get_document_info, get_term_info
from multimedia_search.core.boolean import BooleanQueryError, BooleanRetriever
from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder
from multimedia_search.core.persistence import IndexPersistence
from multimedia_search.core.phrase import PhraseSearcher
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.core.retrieval import RankedRetriever
from multimedia_search.parsers.parser_factory import ParserFactory
from multimedia_search.scanner.file_scanner import FileScanner
from multimedia_search.utils.exceptions import IndexNotFoundError
from multimedia_search.utils.file_utils import is_sidecar_txt
from multimedia_search.vision.enrichment import enrich_image_raw_text
from multimedia_search.web.ingester import ingest_urls
from multimedia_search.web.url_utils import normalize_url


from multimedia_search.utils.query_assist import (
    build_did_you_mean,
    expand_ranked_query,
)

_IMAGE_TYPES = {"jpg", "jpeg", "png", "webp"}


def _resolved_local_path(path_value) -> str:
    """Return the resolved local path to store/display."""
    return str(Path(path_value).expanduser().resolve())


def _normalize_local_path(path_value) -> str:
    """Return a canonical local path key for dedup/merge checks."""
    return normcase(_resolved_local_path(path_value))


def _augment_raw_text_for_indexing(path: Path, raw_text: str) -> str:
    """Apply extra enrichment for image files only."""
    suffix = path.suffix.lower().lstrip(".")
    if suffix in _IMAGE_TYPES:
        return enrich_image_raw_text(path, raw_text)
    return raw_text


def rebuild_document_list_from_reader(reader, preprocessor: Preprocessor):
    """Rebuild documents from persisted index metadata."""
    docs = []
    for doc_id in range(reader.get_doc_count()):
        meta = reader.get_doc_metadata(doc_id)
        raw_text = meta.get("raw_text", "") or ""
        path = meta.get("path", "")
        file_type = meta.get("file_type", "")

        if isinstance(path, str) and path.startswith(("http://", "https://")):
            stored_path = path
        else:
            stored_path = _resolved_local_path(path)

        docs.append(
            Document(
                doc_id=doc_id,
                path=stored_path,
                file_type=file_type,
                raw_text=raw_text,
                tokens=preprocessor.process(raw_text),
            )
        )
    return docs


def handle_index(args):
    """Index local files from a directory, merging with existing index."""
    scanner = FileScanner()
    factory = ParserFactory()
    preproc = Preprocessor()

    directory_path = Path(args.directory).expanduser()
    if not directory_path.exists() or not directory_path.is_dir():
        print("Directory not found or not a directory.")
        return

    # Scan for new documents
    new_docs_raw = []  # (stored_path, compare_key, raw_text, tokens, file_type)
    print(f"Scanning {directory_path}...")

    for path in scanner.scan(directory_path):
        if is_sidecar_txt(path):
            print(f"  Skipping sidecar .txt: {path}")
            continue

        try:
            print(f"  Processing {path}")
            parser = factory.get_parser(path.suffix.lower())
            raw = parser.parse(path)
            raw = _augment_raw_text_for_indexing(path, raw)
            tokens = preproc.process(raw)
            stored_path = _resolved_local_path(path)
            compare_key = _normalize_local_path(path)
            file_type = path.suffix.lower().lstrip(".")
            new_docs_raw.append((stored_path, compare_key, raw, tokens, file_type))
        except Exception as exc:
            print(f"  Warning: failed to parse {path}: {exc}")

    if not new_docs_raw:
        print("No documents indexed.")
        return

    # Load existing index if present
    existing_docs = []

    if config.INDEX_FILE.exists():
        try:
            reader = IndexPersistence.load(config.INDEX_FILE)
            existing_docs = rebuild_document_list_from_reader(reader, preproc)
        except (IndexNotFoundError, Exception) as exc:
            print(f"Warning: Could not load existing index, starting fresh: {exc}")
            existing_docs = []

    # Keep existing documents whose local paths are not being overwritten
    new_local_compare_keys = {compare_key for _, compare_key, _, _, _ in new_docs_raw}

    kept_existing = []
    for doc in existing_docs:
        doc_path = str(doc.path)
        is_web = doc_path.startswith(("http://", "https://"))

        if is_web:
            kept_existing.append(doc)
            continue

        existing_compare_key = _normalize_local_path(doc_path)
        if existing_compare_key not in new_local_compare_keys:
            kept_existing.append(doc)

    # Recompute next_id after keeping
    if kept_existing:
        next_id = max(doc.doc_id for doc in kept_existing) + 1
    else:
        next_id = 0

    # Create new Document objects with sequential ids
    new_docs = []
    for i, (stored_path, _compare_key, raw, tokens, file_type) in enumerate(new_docs_raw):
        doc = Document(
            doc_id=next_id + i,
            path=stored_path,
            file_type=file_type,
            raw_text=raw,
            tokens=tokens,
        )
        new_docs.append(doc)

    # Final merged list
    final_docs = kept_existing + new_docs

    # Rebuild index
    builder = IndexBuilder()
    builder.build(final_docs)
    IndexPersistence.save(builder, config.INDEX_FILE)
    print(f"Indexed/updated {len(new_docs)} document(s). Total documents: {len(final_docs)}")


def handle_web_index(args):
    """Fetch and index web pages from URLs."""
    index_path = config.INDEX_FILE
    existing_urls = set()

    if index_path.exists():
        try:
            reader = IndexPersistence.load(index_path)
            for _, meta in reader.doc_metadata.items():
                stored_path = meta.get("path", "")
                if isinstance(stored_path, str) and stored_path.startswith(("http://", "https://")):
                    existing_urls.add(normalize_url(stored_path))
        except IndexNotFoundError:
            pass

    preprocessor = Preprocessor()
    all_docs = ingest_urls(args.urls, preprocessor)

    new_docs = []
    for doc in all_docs:
        normalized_path = normalize_url(str(doc.path))
        if normalized_path in existing_urls:
            print(f"Skipping already indexed URL: {normalized_path}")
            continue

        doc.path = normalized_path
        new_docs.append(doc)
        existing_urls.add(normalized_path)

    if index_path.exists():
        try:
            reader = IndexPersistence.load(index_path)
            builder = IndexBuilder.from_existing(reader.get_data())
            next_id = max(builder.doc_metadata.keys(), default=-1) + 1
        except IndexNotFoundError:
            builder = IndexBuilder()
            next_id = 0
    else:
        builder = IndexBuilder()
        next_id = 0

    if not new_docs:
        print("No new documents to add.")
        return

    for i, doc in enumerate(new_docs):
        doc.doc_id = next_id + i

    builder.add_documents(new_docs)
    IndexPersistence.save(builder, index_path)
    print(f"Added {len(new_docs)} new web pages. Total documents: {builder.doc_count}")


def load_reader():
    try:
        return IndexPersistence.load(config.INDEX_FILE)
    except IndexNotFoundError:
        print("No index found. Please run index first.")
        return None


def handle_search(args):
    reader = load_reader()
    if not reader:
        return

    query = args.query.strip()
    if not query:
        print("Search query cannot be empty.")
        return

    preprocessor = Preprocessor()
    retriever = RankedRetriever(reader, preprocessor)

    expanded_query = expand_ranked_query(query, reader, preprocessor)
    results = retriever.search(expanded_query, top_k=args.top_k)

    if not results:
        suggestion = build_did_you_mean(reader, query, preprocessor)
        if suggestion:
            print(f"No results. Did you mean: {suggestion}")
        else:
            print("No results.")
        return

    print(f"\nFound {len(results)} results for '{query}':\n")
    for doc_id, score, path, snippet, matched_terms in results:
        meta = reader.get_doc_metadata(doc_id)
        file_type = meta.get("file_type", "unknown")

        if file_type in {"jpg", "jpeg", "png", "webp"}:
            type_label = f"Image ({file_type})"
        elif file_type == "html":
            type_label = "Web page"
        elif file_type:
            type_label = file_type.upper()
        else:
            type_label = "Document"

        print(f"Score: {score:.4f}  |  Type: {type_label}  |  {path}")
        print(f"Snippet: {snippet}")
        print(f"Matched terms: {', '.join(matched_terms)}")
        print()

def handle_boolean(args):
    reader = load_reader()
    if not reader:
        return

    retriever = BooleanRetriever(reader, Preprocessor())

    try:
        results = retriever.evaluate(args.query)
    except BooleanQueryError as exc:
        print(f"Invalid Boolean query: {exc}")
        return

    if not results:
        print("No results.")
        return

    print(f"\nFound {len(results)} results:\n")
    for doc_id in sorted(results):
        meta = reader.get_doc_metadata(doc_id)
        print(meta.get("path", ""))


def handle_phrase(args):
    reader = load_reader()
    if not reader:
        return

    query = args.query.strip()
    if not query:
        print("Phrase query cannot be empty.")
        return

    searcher = PhraseSearcher(reader, Preprocessor())
    results = searcher.search(query)

    if not results:
        print("No results.")
        return

    print(f"\nFound {len(results)} results:\n")
    for doc_id in sorted(results):
        meta = reader.get_doc_metadata(doc_id)
        print(meta.get("path", ""))


def build_parser():
    parser = argparse.ArgumentParser(description="Multimedia Search Engine (Phase 1)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_index = subparsers.add_parser("index", help="Index a directory")
    p_index.add_argument("directory")
    p_index.set_defaults(func=handle_index)

    p_web = subparsers.add_parser("web-index", help="Index one or more web pages")
    p_web.add_argument("urls", nargs="+")
    p_web.add_argument("--debug", action="store_true")
    p_web.set_defaults(func=handle_web_index)

    p_search = subparsers.add_parser("search", help="Ranked keyword search")
    p_search.add_argument("query")
    p_search.add_argument("--top-k", type=int, default=10)
    p_search.set_defaults(func=handle_search)

    p_boolean = subparsers.add_parser("boolean", help="Boolean search (AND, OR, NOT, parentheses)")
    p_boolean.add_argument("query")
    p_boolean.set_defaults(func=handle_boolean)

    p_phrase = subparsers.add_parser("phrase", help="Exact phrase search")
    p_phrase.add_argument("query")
    p_phrase.set_defaults(func=handle_phrase)

    p_docinfo = subparsers.add_parser("doc-info", help="Show document analytics")
    p_docinfo.add_argument("doc_id", help="Document ID (integer)")
    p_docinfo.add_argument("--top-n", type=int, default=10, help="Number of top terms to show")
    p_docinfo.set_defaults(func=handle_doc_info)

    p_terminfo = subparsers.add_parser("term-info", help="Show term statistics")
    p_terminfo.add_argument("term", help="Term to analyze")
    p_terminfo.set_defaults(func=handle_term_info)

    return parser


def handle_doc_info(args):
    """Show analytics for a document by ID."""
    reader = load_reader()
    if not reader:
        return

    try:
        doc_id = int(args.doc_id)
    except ValueError:
        print("Document ID must be an integer.")
        return

    preprocessor = Preprocessor()
    try:
        info = get_document_info(doc_id, reader, preprocessor, top_n=args.top_n)
    except ValueError as exc:
        print(exc)
        return

    print(f"\nDocument {info['doc_id']}:")
    print(f"  Path: {info['path']}")
    print(f"  Source type: {info['source_type']}")
    print(f"  Raw word count: {info['raw_word_count']}")
    print(f"  Processed token count: {info['processed_token_count']}")
    print(f"  Unique terms: {info['unique_term_count']}")
    print("  Top terms:")
    for term, count in info["top_terms"]:
        print(f"    {term}: {count}")
    print(f"  Focus summary: {info['focus_summary']}")
    print()


def handle_term_info(args):
    """Show statistics for a term."""
    reader = load_reader()
    if not reader:
        return

    preprocessor = Preprocessor()
    try:
        info = get_term_info(args.term, reader, preprocessor)
    except ValueError as exc:
        print(exc)
        return

    print(f"\nTerm: '{args.term}' -> normalized: '{info['normalized_term']}'")
    print(f"  Document frequency: {info['document_frequency']}")
    print(f"  Total occurrences: {info['total_occurrences']}")
    print("  Per-document:")
    for path, count in info["per_document"]:
        print(f"    {path}: {count}")
    print()


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()