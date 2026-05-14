"""SQLite setup and metadata helpers for the JSON API layer.

The SQLite database is a control-plane store. It records sources, indexing
runs, and search logs. It does not replace the saved inverted index used by
retrieval.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List

from multimedia_search.config import DATABASE_FILE


def _database_path() -> Path:
    """Return the configured SQLite database path."""
    return Path(DATABASE_FILE)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with project defaults."""
    db_path = _database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database() -> Path:
    """Create the API metadata schema if it does not exist."""
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS indexed_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_value TEXT NOT NULL,
                normalized_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_type, normalized_key)
            );

            CREATE TABLE IF NOT EXISTS indexing_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_value TEXT NOT NULL,
                status TEXT NOT NULL,
                documents_count INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS search_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                mode TEXT NOT NULL,
                top_k INTEGER NOT NULL DEFAULT 10,
                image_only INTEGER NOT NULL DEFAULT 0,
                media_type TEXT NOT NULL DEFAULT 'all',
                results_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    return _database_path()


def get_database_status() -> dict:
    """Return a safe status object for API health checks."""
    try:
        db_path = init_database()
    except Exception as exc:
        return {
            "ok": False,
            "path": str(_database_path()),
            "error": str(exc),
        }

    return {
        "ok": True,
        "path": str(db_path),
    }


def upsert_indexed_source(
    source_type: str,
    source_value: str,
    normalized_key: str,
    status: str = "active",
    notes: str = "",
) -> None:
    """Insert or update one source record."""
    init_database()

    with connect() as connection:
        connection.execute(
            """
            INSERT INTO indexed_sources (
                source_type,
                source_value,
                normalized_key,
                status,
                notes
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_type, normalized_key) DO UPDATE SET
                source_value = excluded.source_value,
                status = excluded.status,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (source_type, source_value, normalized_key, status, notes),
        )


def record_indexing_run(
    source_type: str,
    source_value: str,
    status: str,
    documents_count: int = 0,
    message: str = "",
) -> None:
    """Record one indexing attempt."""
    init_database()

    with connect() as connection:
        connection.execute(
            """
            INSERT INTO indexing_runs (
                source_type,
                source_value,
                status,
                documents_count,
                message
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (source_type, source_value, status, int(documents_count), message),
        )


def log_search(
    query: str,
    mode: str,
    top_k: int,
    image_only: bool,
    results_count: int,
    media_type: str = "all",
) -> None:
    """Record one API search request."""
    init_database()

    with connect() as connection:
        connection.execute(
            """
            INSERT INTO search_logs (
                query,
                mode,
                top_k,
                image_only,
                media_type,
                results_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                query,
                mode,
                int(top_k),
                1 if image_only else 0,
                media_type,
                int(results_count),
            ),
        )


def list_indexed_sources() -> List[Dict[str, object]]:
    """Return all indexed source records."""
    init_database()

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                source_type,
                source_value,
                normalized_key,
                status,
                notes,
                created_at,
                updated_at
            FROM indexed_sources
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def list_indexing_runs(limit: int = 50) -> List[Dict[str, object]]:
    """Return recent indexing run records."""
    init_database()
    safe_limit = max(1, min(int(limit), 200))

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                source_type,
                source_value,
                status,
                documents_count,
                message,
                created_at
            FROM indexing_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def clear_api_records() -> None:
    """Clear API metadata tables without deleting source files."""
    init_database()

    with connect() as connection:
        connection.execute("DELETE FROM search_logs")
        connection.execute("DELETE FROM indexing_runs")
        connection.execute("DELETE FROM indexed_sources")